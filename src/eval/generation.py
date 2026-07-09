import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel

from src.eval.schema import EvalExample, write_eval_set

_GENERATION_SYSTEM_PROMPT = """You write evaluation questions for a RAG (retrieval-augmented \
generation) system, from a single excerpt of a research paper.

Given the excerpt below, decide if it contains enough substantive content to write a good \
question from (set answerable=false for reference lists, tables of contents, acknowledgments, \
author affiliations, or other boilerplate with no real content).

If answerable, write:
- question: a natural question a user might ask, answerable using ONLY this excerpt. Do not \
reference "the passage" or "the excerpt" in the question - ask it as a standalone question.
- reference_answer: a concise (1-3 sentence) correct answer to that question, grounded only \
in this excerpt."""

_GENERATION_USER_TEMPLATE = """Excerpt from "{source}" (page {page}):

{text}"""


class GeneratedQA(BaseModel):
    answerable: bool
    question: str = ""
    reference_answer: str = ""


_generation_llm = None


def _get_generation_llm(model: str):
    """Create and cache the structured-output generation LLM on first use."""
    global _generation_llm
    if _generation_llm is not None:
        return _generation_llm

    from langchain_openai import ChatOpenAI

    _generation_llm = ChatOpenAI(model=model, temperature=0.3).with_structured_output(GeneratedQA)
    return _generation_llm


def _sample_chunks(
    vectorstore: Any,
    questions_per_doc: int,
    min_chunk_chars: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """Pull all chunks from the persisted vectorstore, group by source document,
    and sample up to `questions_per_doc` chunks per document."""
    raw = vectorstore.get(include=["documents", "metadatas"])

    by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chunk_id, text, metadata in zip(raw["ids"], raw["documents"], raw["metadatas"]):
        if not text or len(text) < min_chunk_chars:
            continue
        source = (metadata or {}).get("source", "unknown")
        by_source[source].append({"id": chunk_id, "text": text, "metadata": metadata or {}})

    rng = random.Random(seed)
    sampled: List[Dict[str, Any]] = []
    for chunks in by_source.values():
        rng.shuffle(chunks)
        sampled.extend(chunks[:questions_per_doc])

    return sampled


def generate_eval_set(
    persist_directory: str = "./chroma_db",
    output_path: str = "data/eval/eval_set.jsonl",
    questions_per_doc: int = 2,
    min_chunk_chars: int = 300,
    model: str = "gpt-4o-mini",
    seed: int = 42,
) -> List[EvalExample]:
    """Generate an LLM-authored eval set from the documents already ingested into
    the vectorstore at `persist_directory`, and write it to `output_path`."""
    from src.ingestion.embedders import get_embedding_model
    from src.retrieval.vectorstore import load_vectorstore

    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings, persist_directory)

    chunks = _sample_chunks(vectorstore, questions_per_doc, min_chunk_chars, seed)
    if not chunks:
        raise ValueError(
            "No chunks available to generate eval questions from. Run ingestion first."
        )

    llm = _get_generation_llm(model)
    created_at = datetime.now(timezone.utc).isoformat()
    examples: List[EvalExample] = []

    for chunk in chunks:
        source = chunk["metadata"].get("source", "unknown")
        page = chunk["metadata"].get("page")

        try:
            result: GeneratedQA = llm.invoke(
                [
                    {"role": "system", "content": _GENERATION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _GENERATION_USER_TEMPLATE.format(
                            source=source, page=page, text=chunk["text"]
                        ),
                    },
                ]
            )
        except Exception as exc:
            print(f"  Skipped chunk {chunk['id']} ({source}): {exc}")
            continue

        if not result.answerable or not result.question.strip():
            continue

        examples.append(
            EvalExample(
                id=f"eval_{len(examples) + 1:04d}",
                question=result.question.strip(),
                reference_answer=result.reference_answer.strip(),
                expected_source=source,
                expected_page=page,
                source_chunk_id=str(chunk["id"]),
                generation_model=model,
                created_at=created_at,
            )
        )

    write_eval_set(output_path, examples)
    print(
        f"Generated {len(examples)} eval examples from {len(chunks)} sampled chunks "
        f"-> {output_path}"
    )
    return examples
