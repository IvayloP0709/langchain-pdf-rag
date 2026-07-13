import json

import pytest
from langchain_core.documents import Document

from scripts.generate_reranker_training_set import (
    GeneratedQuestion,
    generate_training_set,
    mine_hard_negatives,
    verify_disjoint_from_eval_set,
)


def _doc(text, source):
    return Document(page_content=text, metadata={"source": source})


def test_mine_hard_negatives_excludes_same_source_document():
    candidates = [
        _doc("chunk from same doc as positive", "paper_a.pdf"),
        _doc("chunk from doc b, negative 1", "paper_b.pdf"),
        _doc("another chunk from same doc as positive", "paper_a.pdf"),
        _doc("chunk from doc c, negative 2", "paper_c.pdf"),
        _doc("chunk from doc b, negative 3", "paper_b.pdf"),
        _doc("chunk from doc c, would be truncated", "paper_c.pdf"),
    ]

    negatives = mine_hard_negatives(candidates, positive_source="paper_a.pdf", num_negatives=3)

    assert len(negatives) == 3
    assert all(doc.metadata["source"] != "paper_a.pdf" for doc in negatives)
    assert [doc.page_content for doc in negatives] == [
        "chunk from doc b, negative 1",
        "chunk from doc c, negative 2",
        "chunk from doc b, negative 3",
    ]


def test_mine_hard_negatives_returns_fewer_when_pool_too_small():
    candidates = [
        _doc("same doc as positive", "paper_a.pdf"),
        _doc("only other-doc candidate", "paper_b.pdf"),
    ]

    negatives = mine_hard_negatives(candidates, positive_source="paper_a.pdf", num_negatives=3)

    assert len(negatives) == 1
    assert negatives[0].metadata["source"] == "paper_b.pdf"


def test_mine_hard_negatives_all_same_source_returns_empty():
    candidates = [_doc("x", "paper_a.pdf"), _doc("y", "paper_a.pdf")]

    negatives = mine_hard_negatives(candidates, positive_source="paper_a.pdf", num_negatives=3)

    assert negatives == []


def _write_eval_set(path, questions, chunk_ids=None):
    chunk_ids = chunk_ids or [None] * len(questions)
    with open(path, "w", encoding="utf-8") as f:
        for i, (question, chunk_id) in enumerate(zip(questions, chunk_ids), start=1):
            f.write(
                json.dumps(
                    {
                        "id": f"eval_{i:04d}",
                        "question": question,
                        "reference_answer": "answer",
                        "expected_source": "a.pdf",
                        "expected_page": 0,
                        "source_chunk_id": chunk_id,
                    }
                )
                + "\n"
            )


def test_verify_disjoint_from_eval_set_passes_when_disjoint(tmp_path):
    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["What is X?"])

    verify_disjoint_from_eval_set(["What is Y?", "How does Z work?"], str(eval_path))


def test_verify_disjoint_from_eval_set_raises_on_overlap(tmp_path):
    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["What is X?"])

    with pytest.raises(ValueError, match="overlap"):
        verify_disjoint_from_eval_set(["  what IS x?  ", "How does Z work?"], str(eval_path))


def test_eval_set_chunk_ids_returns_only_populated_ids(tmp_path):
    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["Q1?", "Q2?", "Q3?"], chunk_ids=["chunk-1", None, "chunk-3"])

    from scripts.generate_reranker_training_set import eval_set_chunk_ids

    assert eval_set_chunk_ids(str(eval_path)) == {"chunk-1", "chunk-3"}


class FakeVectorstore:
    def __init__(self, ids, documents, metadatas):
        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas

    def get(self, include=None):
        return {"ids": self._ids, "documents": self._documents, "metadatas": self._metadatas}


class FakeMiningRetriever:
    def __init__(self, candidates_by_query):
        self._candidates_by_query = candidates_by_query

    def invoke(self, query):
        return self._candidates_by_query[query]

    def batch_as_completed(self, queries, config=None, return_exceptions=False):
        for index, query in enumerate(queries):
            yield index, self._candidates_by_query[query]


class FakeGenerationLLM:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.results.pop(0)

    def batch_as_completed(self, inputs, config=None, return_exceptions=False):
        self.calls.extend(inputs)
        for index in range(len(inputs)):
            yield index, self.results[index]


def test_generate_training_set_writes_disjoint_train_val_split(tmp_path, monkeypatch):
    import scripts.generate_reranker_training_set as gen_mod

    vectorstore = FakeVectorstore(
        ids=["1", "2", "3", "4"],
        documents=["a" * 500, "b" * 500, "c" * 500, "d" * 500],
        metadatas=[
            {"source": "paper_a.pdf", "page": 0},
            {"source": "paper_a.pdf", "page": 1},
            {"source": "paper_b.pdf", "page": 0},
            {"source": "paper_b.pdf", "page": 1},
        ],
    )

    questions = ["Question 1?", "Question 2?", "Question 3?", "Question 4?"]
    fake_llm = FakeGenerationLLM(
        [GeneratedQuestion(answerable=True, question=q) for q in questions]
    )

    all_docs = [
        _doc(vectorstore._documents[i], vectorstore._metadatas[i]["source"]) for i in range(4)
    ]
    candidates_by_query = {q: all_docs for q in questions}

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)
    monkeypatch.setattr(
        "src.retrieval.retrievers.create_retriever",
        lambda vs, k: FakeMiningRetriever(candidates_by_query),
    )
    monkeypatch.setattr(gen_mod, "_get_generation_llm", lambda model: fake_llm)

    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["An unrelated eval question?"])

    output_dir = tmp_path / "reranker"
    stats = generate_training_set(
        persist_directory="unused",
        output_dir=str(output_dir),
        eval_set_path=str(eval_path),
        min_chunk_chars=300,
        num_negatives=2,
        val_fraction=0.5,
        seed=1,
    )

    assert stats["num_questions"] == 4

    train_path = output_dir / "train.jsonl"
    val_path = output_dir / "val.jsonl"
    assert train_path.exists()
    assert val_path.exists()

    def load(path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    train_records = load(train_path)
    val_records = load(val_path)

    # each question contributes 1 positive + 2 negatives (candidates include 2 same-source
    # and 2 other-source docs per positive, so both other-source docs are mined as negatives)
    assert stats["num_train_examples"] == len(train_records)
    assert stats["num_val_examples"] == len(val_records)
    assert len(train_records) + len(val_records) == 4 * 3  # 4 questions x (1 pos + 2 neg)

    train_queries = {r["query"] for r in train_records}
    val_queries = {r["query"] for r in val_records}
    assert train_queries.isdisjoint(val_queries)  # no query leaks across the split

    for record in train_records + val_records:
        assert record["label"] in (0, 1)


def test_generate_training_set_raises_on_invalid_val_fraction(tmp_path):
    with pytest.raises(ValueError, match="val_fraction"):
        generate_training_set(
            persist_directory="unused",
            output_dir=str(tmp_path / "reranker"),
            eval_set_path=str(tmp_path / "eval_set.jsonl"),
            val_fraction=1.5,
        )


def test_generate_training_set_skips_positives_with_too_few_negatives(tmp_path, monkeypatch):
    import scripts.generate_reranker_training_set as gen_mod

    # Both chunks are from the same source document, so mining will find zero
    # cross-document negatives for either one - both should be skipped entirely
    # rather than written out with fewer than num_negatives negatives.
    vectorstore = FakeVectorstore(
        ids=["1", "2"],
        documents=["a" * 500, "b" * 500],
        metadatas=[
            {"source": "paper_a.pdf", "page": 0},
            {"source": "paper_a.pdf", "page": 1},
        ],
    )

    questions = ["Question 1?", "Question 2?"]
    fake_llm = FakeGenerationLLM(
        [GeneratedQuestion(answerable=True, question=q) for q in questions]
    )

    same_source_docs = [_doc("a" * 500, "paper_a.pdf"), _doc("b" * 500, "paper_a.pdf")]
    candidates_by_query = {q: same_source_docs for q in questions}

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)
    monkeypatch.setattr(
        "src.retrieval.retrievers.create_retriever",
        lambda vs, k: FakeMiningRetriever(candidates_by_query),
    )
    monkeypatch.setattr(gen_mod, "_get_generation_llm", lambda model: fake_llm)

    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["An unrelated eval question?"])

    with pytest.raises(ValueError, match="No training pairs"):
        generate_training_set(
            persist_directory="unused",
            output_dir=str(tmp_path / "reranker"),
            eval_set_path=str(eval_path),
            min_chunk_chars=300,
            num_negatives=3,
        )


def test_generate_training_set_keeps_duplicate_questions_in_same_split(tmp_path, monkeypatch):
    import scripts.generate_reranker_training_set as gen_mod

    # Two chunks from different documents that the LLM happens to phrase identically -
    # both groups share a normalized query and must land in the same split.
    vectorstore = FakeVectorstore(
        ids=["1", "2", "3", "4"],
        documents=["a" * 500, "b" * 500, "c" * 500, "d" * 500],
        metadatas=[
            {"source": "paper_a.pdf", "page": 0},
            {"source": "paper_b.pdf", "page": 0},
            {"source": "paper_c.pdf", "page": 0},
            {"source": "paper_d.pdf", "page": 0},
        ],
    )

    # Chunks 1 and 2 get the exact same generated question wording (case/whitespace vary).
    fake_llm = FakeGenerationLLM(
        [
            GeneratedQuestion(answerable=True, question="What is X?"),
            GeneratedQuestion(answerable=True, question="  what IS x?  "),
            GeneratedQuestion(answerable=True, question="What is Y?"),
            GeneratedQuestion(answerable=True, question="What is Z?"),
        ]
    )

    all_docs = [
        _doc(vectorstore._documents[i], vectorstore._metadatas[i]["source"]) for i in range(4)
    ]
    candidates_by_query = {
        "What is X?": all_docs,
        "what IS x?": all_docs,  # mining looks up the .strip()'d question, not the raw form
        "What is Y?": all_docs,
        "What is Z?": all_docs,
    }

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)
    monkeypatch.setattr(
        "src.retrieval.retrievers.create_retriever",
        lambda vs, k: FakeMiningRetriever(candidates_by_query),
    )
    monkeypatch.setattr(gen_mod, "_get_generation_llm", lambda model: fake_llm)

    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["An unrelated eval question?"])

    output_dir = tmp_path / "reranker"
    generate_training_set(
        persist_directory="unused",
        output_dir=str(output_dir),
        eval_set_path=str(eval_path),
        min_chunk_chars=300,
        num_negatives=1,
        val_fraction=0.5,
        seed=7,
    )

    def load(path):
        return [json.loads(line) for line in path.read_text().splitlines()]

    train_records = load(output_dir / "train.jsonl")
    val_records = load(output_dir / "val.jsonl")

    train_queries = {r["query"].strip().lower() for r in train_records}
    val_queries = {r["query"].strip().lower() for r in val_records}
    assert train_queries.isdisjoint(val_queries)


def test_generate_training_set_raises_on_eval_set_overlap(tmp_path, monkeypatch):
    import scripts.generate_reranker_training_set as gen_mod

    vectorstore = FakeVectorstore(
        ids=["1", "2"],
        documents=["a" * 500, "b" * 500],
        metadatas=[
            {"source": "paper_a.pdf", "page": 0},
            {"source": "paper_b.pdf", "page": 0},
        ],
    )

    fake_llm = FakeGenerationLLM(
        [
            GeneratedQuestion(answerable=True, question="What is X?"),
            GeneratedQuestion(answerable=True, question="What is Y?"),
        ]
    )

    all_docs = [_doc("a" * 500, "paper_a.pdf"), _doc("b" * 500, "paper_b.pdf")]
    candidates_by_query = {"What is X?": all_docs, "What is Y?": all_docs}

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)
    monkeypatch.setattr(
        "src.retrieval.retrievers.create_retriever",
        lambda vs, k: FakeMiningRetriever(candidates_by_query),
    )
    monkeypatch.setattr(gen_mod, "_get_generation_llm", lambda model: fake_llm)

    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["what is x?"])  # overlaps "What is X?" after normalization

    with pytest.raises(ValueError, match="overlap"):
        generate_training_set(
            persist_directory="unused",
            output_dir=str(tmp_path / "reranker"),
            eval_set_path=str(eval_path),
            min_chunk_chars=300,
            num_negatives=1,
        )


def test_generate_training_set_skips_chunks_already_used_by_eval_set(tmp_path, monkeypatch):
    import scripts.generate_reranker_training_set as gen_mod

    # Chunk "1" was already used to generate an eval-set question - it must never be sent to
    # the generation LLM at all, regardless of what question the LLM would produce for it.
    vectorstore = FakeVectorstore(
        ids=["1", "2", "3"],
        documents=["a" * 500, "b" * 500, "c" * 500],
        metadatas=[
            {"source": "paper_a.pdf", "page": 0},
            {"source": "paper_b.pdf", "page": 0},
            {"source": "paper_c.pdf", "page": 0},
        ],
    )

    fake_llm = FakeGenerationLLM(
        [
            GeneratedQuestion(answerable=True, question="What is Y?"),
            GeneratedQuestion(answerable=True, question="What is Z?"),
        ]
    )

    all_docs = [
        _doc("a" * 500, "paper_a.pdf"),
        _doc("b" * 500, "paper_b.pdf"),
        _doc("c" * 500, "paper_c.pdf"),
    ]
    candidates_by_query = {"What is Y?": all_docs, "What is Z?": all_docs}

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)
    monkeypatch.setattr(
        "src.retrieval.retrievers.create_retriever",
        lambda vs, k: FakeMiningRetriever(candidates_by_query),
    )
    monkeypatch.setattr(gen_mod, "_get_generation_llm", lambda model: fake_llm)

    eval_path = tmp_path / "eval_set.jsonl"
    _write_eval_set(eval_path, ["An unrelated eval question?"], chunk_ids=["1"])

    stats = generate_training_set(
        persist_directory="unused",
        output_dir=str(tmp_path / "reranker"),
        eval_set_path=str(eval_path),
        min_chunk_chars=300,
        num_negatives=1,
    )

    # Only chunks 2 and 3 were ever sent to the LLM - chunk 1 was excluded before generation.
    assert len(fake_llm.calls) == 2
    assert stats["num_questions"] == 2
