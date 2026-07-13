#!/usr/bin/env python3
"""Generate synthetic reranker training data from the ingested corpus.

For each ingested chunk, prompts gpt-4o-mini for a question the chunk answers (a positive
pair), then mines hard negatives from the current (un-fine-tuned) retriever's top results for
that question, excluding any chunk from the same source document as the positive. Question
generation and hard-negative mining are each run as a concurrent batch (see --max-concurrency)
rather than one chunk at a time, since the dominant cost is network round-trips. Verifies the
generated questions are disjoint from the existing eval set (so the later before/after eval
comparison isn't contaminated by training-on-the-test-set), then writes an 85/15 train/val
JSONL split of `{query, doc_text, label}` records.

Usage example:
python scripts/generate_reranker_training_set.py \
    --persist-directory ./chroma_db \
    --output-dir data/reranker \
    --eval-set data/eval/eval_set.jsonl
"""

import argparse
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TRAINING_SYSTEM_PROMPT = """You write training questions for fine-tuning a retrieval reranker, \
from a single excerpt of a research paper.

Given the excerpt below, decide if it contains enough substantive content to write a good \
question from (set answerable=false for reference lists, tables of contents, acknowledgments, \
author affiliations, or other boilerplate with no real content).

If answerable, write a natural question a user might ask that is answerable using ONLY this \
excerpt. Do not reference "the passage" or "the excerpt" in the question - ask it as a \
standalone question."""

_TRAINING_USER_TEMPLATE = """Excerpt from "{source}" (page {page}):

{text}"""


class GeneratedQuestion(BaseModel):
    answerable: bool
    question: str = ""


class RerankExample(BaseModel):
    query: str
    doc_text: str
    label: int


_generation_llm = None


def _get_generation_llm(model: str):
    """Create and cache the structured-output generation LLM on first use."""
    global _generation_llm
    if _generation_llm is not None:
        return _generation_llm

    from langchain_openai import ChatOpenAI

    _generation_llm = ChatOpenAI(model=model, temperature=0.3).with_structured_output(
        GeneratedQuestion
    )
    return _generation_llm


def _load_all_chunks(vectorstore: Any, min_chunk_chars: int) -> List[Dict[str, Any]]:
    """Pull every chunk from the persisted vectorstore, skipping short/boilerplate ones."""
    raw = vectorstore.get(include=["documents", "metadatas"])

    chunks: List[Dict[str, Any]] = []
    for chunk_id, text, metadata in zip(raw["ids"], raw["documents"], raw["metadatas"]):
        if not text or len(text) < min_chunk_chars:
            continue
        metadata = metadata or {}
        chunks.append(
            {
                "id": chunk_id,
                "text": text,
                "source": metadata.get("source", "unknown"),
                "page": metadata.get("page"),
            }
        )
    return chunks


def mine_hard_negatives(
    candidates: List[Document],
    positive_source: str,
    num_negatives: int = 3,
) -> List[Document]:
    """From a ranked candidate list (nearest-first), pick up to `num_negatives` docs whose
    source document differs from the positive's - same-paper subtopic overlap risks mislabeling
    a genuinely relevant chunk as a negative, so same-source candidates are excluded outright."""
    return [doc for doc in candidates if (doc.metadata or {}).get("source") != positive_source][
        :num_negatives
    ]


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def verify_disjoint_from_eval_set(questions: List[str], eval_set_path: str) -> None:
    """Fail loudly if any generated question overlaps the frozen eval set - training on a
    test-set question would contaminate the before/after eval comparison."""
    from src.eval.schema import load_eval_set

    eval_questions = {_normalize_question(e.question) for e in load_eval_set(eval_set_path)}
    overlap = sorted({q for q in questions if _normalize_question(q) in eval_questions})
    if overlap:
        raise ValueError(
            f"{len(overlap)} generated question(s) overlap with the eval set at "
            f"{eval_set_path}; training on these would contaminate the before/after eval "
            f"comparison. Overlapping questions: {overlap}"
        )


def write_jsonl(path: str, examples: List[RerankExample]) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(example.model_dump_json())
            f.write("\n")


def generate_training_set(
    persist_directory: str = "./chroma_db",
    output_dir: str = "data/reranker",
    eval_set_path: str = "data/eval/eval_set.jsonl",
    min_chunk_chars: int = 300,
    model: str = "gpt-4o-mini",
    num_negatives: int = 3,
    candidate_k: int = 15,
    val_fraction: float = 0.15,
    seed: int = 42,
    limit: Optional[int] = None,
    max_concurrency: int = 10,
) -> Dict[str, int]:
    """Generate synthetic (query, positive chunk, hard negatives) training data from the
    documents already ingested into the vectorstore at `persist_directory`, and write an
    85/15 train/val JSONL split to `output_dir`."""
    if not 0 <= val_fraction <= 1:
        raise ValueError(f"val_fraction must be between 0 and 1, got {val_fraction}.")

    from src.ingestion.embedders import get_embedding_model
    from src.retrieval.retrievers import create_retriever
    from src.retrieval.vectorstore import load_vectorstore

    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings, persist_directory)

    chunks = _load_all_chunks(vectorstore, min_chunk_chars)
    if not chunks:
        raise ValueError(
            "No chunks available to generate training pairs from. Run ingestion first."
        )
    if limit is not None:
        chunks = chunks[:limit]

    # Un-fine-tuned retriever used purely to mine hard negatives - no reranking involved.
    mining_retriever = create_retriever(vectorstore, k=candidate_k)
    llm = _get_generation_llm(model)

    # Phase 1: batch the question-generation LLM calls concurrently - this is the dominant
    # cost (one OpenAI round-trip per chunk) and the main reason a ~1800-chunk corpus would
    # otherwise take the better part of an hour running fully sequentially.
    print(f"Generating questions for {len(chunks)} chunks (max_concurrency={max_concurrency})...")
    generation_inputs = [
        [
            {"role": "system", "content": _TRAINING_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _TRAINING_USER_TEMPLATE.format(
                    source=chunk["source"], page=chunk["page"], text=chunk["text"]
                ),
            },
        ]
        for chunk in chunks
    ]
    generation_results = llm.batch(
        generation_inputs, config={"max_concurrency": max_concurrency}, return_exceptions=True
    )

    positives: List[Dict[str, Any]] = []
    for chunk, result in zip(chunks, generation_results):
        if isinstance(result, Exception):
            print(f"  Skipped chunk {chunk['id']} ({chunk['source']}): {result}")
            continue

        if not result.answerable or not result.question.strip():
            continue

        positives.append({**chunk, "question": result.question.strip()})

    if not positives:
        raise ValueError("No answerable questions were generated from the ingested corpus.")

    # Phase 2: batch the hard-negative mining retriever calls the same way.
    print(
        f"Mining hard negatives for {len(positives)} questions "
        f"(max_concurrency={max_concurrency})..."
    )
    mining_results = mining_retriever.batch(
        [positive["question"] for positive in positives],
        config={"max_concurrency": max_concurrency},
        return_exceptions=True,
    )

    groups: List[List[RerankExample]] = []
    questions: List[str] = []

    for positive, candidates in zip(positives, mining_results):
        if isinstance(candidates, Exception):
            print(
                f"  Skipped mining for chunk {positive['id']} ({positive['source']}): {candidates}"
            )
            continue

        negatives = mine_hard_negatives(candidates, positive["source"], num_negatives)
        if len(negatives) < num_negatives:
            print(
                f"  Skipped chunk {positive['id']} ({positive['source']}): only found "
                f"{len(negatives)}/{num_negatives} hard negatives from other source documents"
            )
            continue

        question = positive["question"]
        group = [RerankExample(query=question, doc_text=positive["text"], label=1)]
        group.extend(
            RerankExample(query=question, doc_text=doc.page_content, label=0) for doc in negatives
        )

        groups.append(group)
        questions.append(question)

    if not groups:
        raise ValueError("No training pairs were generated from the ingested corpus.")

    verify_disjoint_from_eval_set(questions, eval_set_path)

    # Split whole groups (a question with its mined negatives), not individual records, so the
    # same query never appears in both train and val - including when two different chunks
    # happen to generate the same (normalized) question, which is why duplicates are pinned to
    # whichever split their first occurrence landed in rather than shuffled independently.
    rng = random.Random(seed)
    rng.shuffle(groups)
    val_target = round(len(groups) * val_fraction)

    split_by_question: Dict[str, str] = {}
    val_groups: List[List[RerankExample]] = []
    train_groups: List[List[RerankExample]] = []
    for group in groups:
        norm_question = _normalize_question(group[0].query)
        split = split_by_question.get(norm_question)
        if split is None:
            split = "val" if len(val_groups) < val_target else "train"
            split_by_question[norm_question] = split
        (val_groups if split == "val" else train_groups).append(group)

    train_examples = [example for group in train_groups for example in group]
    val_examples = [example for group in val_groups for example in group]

    train_path = str(Path(output_dir) / "train.jsonl")
    val_path = str(Path(output_dir) / "val.jsonl")
    write_jsonl(train_path, train_examples)
    write_jsonl(val_path, val_examples)

    print(
        f"Generated {len(groups)} positive questions from {len(chunks)} chunks "
        f"({len(train_groups)} train / {len(val_groups)} val) -> "
        f"{len(train_examples)} train examples -> {train_path}, "
        f"{len(val_examples)} val examples -> {val_path}"
    )

    return {
        "num_questions": len(groups),
        "num_train_examples": len(train_examples),
        "num_val_examples": len(val_examples),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate synthetic reranker training data (query/doc_text/label triples) from "
            "the ingested corpus, with hard negatives mined from the current retriever."
        )
    )
    parser.add_argument(
        "--persist-directory", default="./chroma_db", help="Vectorstore persistence directory."
    )
    parser.add_argument(
        "--output-dir",
        default="data/reranker",
        help="Directory to write train.jsonl/val.jsonl into.",
    )
    parser.add_argument(
        "--eval-set",
        default="data/eval/eval_set.jsonl",
        help="Path to the frozen eval set JSONL, checked for question overlap.",
    )
    parser.add_argument(
        "--min-chunk-chars",
        type=int,
        default=300,
        help="Skip chunks shorter than this many characters.",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini", help="OpenAI chat model used for question generation."
    )
    parser.add_argument(
        "--num-negatives",
        type=int,
        default=3,
        help="Number of hard negatives to mine per positive pair.",
    )
    parser.add_argument(
        "--candidate-k",
        type=int,
        default=15,
        help="Size of the retriever candidate pool hard negatives are mined from.",
    )
    parser.add_argument(
        "--val-fraction", type=float, default=0.15, help="Fraction of questions held out for val."
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for the train/val split.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N chunks (useful for a quick smoke run).",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=10,
        help="Max concurrent OpenAI/retriever calls during question generation and mining.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from src.config import validate_runtime_config

    ok, message = validate_runtime_config()
    if not ok:
        print(f"ERROR: {message}")
        return 1

    try:
        generate_training_set(
            persist_directory=args.persist_directory,
            output_dir=args.output_dir,
            eval_set_path=args.eval_set,
            min_chunk_chars=args.min_chunk_chars,
            model=args.model,
            num_negatives=args.num_negatives,
            candidate_k=args.candidate_k,
            val_fraction=args.val_fraction,
            seed=args.seed,
            limit=args.limit,
            max_concurrency=args.max_concurrency,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
