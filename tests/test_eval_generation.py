import pytest

import src.eval.generation as generation
from src.eval.generation import GeneratedQA, _sample_chunks, generate_eval_set


class FakeVectorstore:
    def __init__(self, ids, documents, metadatas):
        self._ids = ids
        self._documents = documents
        self._metadatas = metadatas

    def get(self, include=None):
        return {"ids": self._ids, "documents": self._documents, "metadatas": self._metadatas}


class FakeGenerationLLM:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.results.pop(0)


def test_sample_chunks_groups_by_source_and_filters_short():
    vectorstore = FakeVectorstore(
        ids=["1", "2", "3", "4"],
        documents=["short", "a" * 500, "b" * 500, "c" * 500],
        metadatas=[
            {"source": "a.pdf", "page": 0},
            {"source": "a.pdf", "page": 1},
            {"source": "a.pdf", "page": 2},
            {"source": "b.pdf", "page": 0},
        ],
    )

    sampled = _sample_chunks(vectorstore, questions_per_doc=2, min_chunk_chars=300, seed=1)

    sources = [c["metadata"]["source"] for c in sampled]
    assert sources.count("a.pdf") == 2
    assert sources.count("b.pdf") == 1


def test_sample_chunks_empty_vectorstore():
    vectorstore = FakeVectorstore(ids=[], documents=[], metadatas=[])
    assert _sample_chunks(vectorstore, questions_per_doc=2, min_chunk_chars=300, seed=1) == []


def test_generate_eval_set_skips_unanswerable_and_writes_file(tmp_path, monkeypatch):
    vectorstore = FakeVectorstore(
        ids=["1", "2"],
        documents=["x" * 500, "y" * 500],
        metadatas=[{"source": "a.pdf", "page": 0}, {"source": "b.pdf", "page": 3}],
    )

    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)

    fake_llm = FakeGenerationLLM(
        [
            GeneratedQA(answerable=True, question="What is X?", reference_answer="X is a thing."),
            GeneratedQA(answerable=False),
        ]
    )
    monkeypatch.setattr(generation, "_get_generation_llm", lambda model: fake_llm)

    output_path = tmp_path / "eval_set.jsonl"
    examples = generate_eval_set(
        persist_directory="unused",
        output_path=str(output_path),
        questions_per_doc=2,
        min_chunk_chars=300,
        model="gpt-4o-mini",
        seed=1,
    )

    assert len(examples) == 1
    assert examples[0].question == "What is X?"
    assert examples[0].expected_source in {"a.pdf", "b.pdf"}
    assert output_path.exists()


def test_generate_eval_set_raises_when_no_chunks(monkeypatch):
    vectorstore = FakeVectorstore(ids=[], documents=[], metadatas=[])
    monkeypatch.setattr("src.ingestion.embedders.get_embedding_model", lambda: object())
    monkeypatch.setattr("src.retrieval.vectorstore.load_vectorstore", lambda emb, p: vectorstore)

    with pytest.raises(ValueError):
        generate_eval_set(persist_directory="unused", output_path="unused.jsonl")
