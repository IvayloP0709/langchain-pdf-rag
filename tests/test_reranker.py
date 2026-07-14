import pytest

from src.retrieval.reranker import CrossEncoderReranker, create_reranker


class FakeDoc:
    def __init__(self, doc_id, content):
        self.id = doc_id
        self.page_content = content


class StubScoringModel:
    def __init__(self, scores_by_content):
        self._scores_by_content = scores_by_content

    def predict(self, pairs):
        return [self._scores_by_content[doc_text] for _, doc_text in pairs]


def test_rerank_orders_by_descending_score():
    docs = [
        FakeDoc(1, "low relevance"),
        FakeDoc(2, "high relevance"),
        FakeDoc(3, "medium relevance"),
    ]
    scores = {"low relevance": 0.1, "high relevance": 0.9, "medium relevance": 0.5}
    reranker = CrossEncoderReranker(StubScoringModel(scores))

    result = reranker.rerank("query", docs)

    assert [doc.id for doc in result] == [2, 3, 1]


def test_rerank_passes_query_doc_pairs_to_model():
    docs = [FakeDoc(1, "alpha"), FakeDoc(2, "beta")]
    captured_pairs = {}

    class CapturingModel:
        def predict(self, pairs):
            captured_pairs["pairs"] = pairs
            return [0.0 for _ in pairs]

    CrossEncoderReranker(CapturingModel()).rerank("my query", docs)

    assert captured_pairs["pairs"] == [("my query", "alpha"), ("my query", "beta")]


def test_rerank_empty_docs_returns_empty_list():
    reranker = CrossEncoderReranker(StubScoringModel({}))

    assert reranker.rerank("query", []) == []


def test_create_reranker_none_mode_returns_none():
    assert create_reranker("none") is None


def test_create_reranker_finetuned_mode_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        create_reranker("finetuned")


def test_create_reranker_invalid_mode_raises_value_error():
    with pytest.raises(ValueError):
        create_reranker("bogus")
