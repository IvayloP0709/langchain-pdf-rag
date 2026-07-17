import pytest

import src.retrieval.reranker as reranker_module
from src.retrieval.reranker import PRETRAINED_MODEL_NAME, CrossEncoderReranker, create_reranker


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


def test_create_reranker_pretrained_mode_loads_expected_model_name(monkeypatch):
    captured = {}

    def fake_load(model_name_or_path):
        captured["path"] = model_name_or_path
        return StubScoringModel({})

    monkeypatch.setattr(reranker_module, "_load_cross_encoder", fake_load)

    result = create_reranker("pretrained")

    assert isinstance(result, CrossEncoderReranker)
    assert captured["path"] == PRETRAINED_MODEL_NAME


def test_create_reranker_finetuned_mode_loads_default_path(monkeypatch):
    monkeypatch.delenv("RERANKER_MODEL_PATH", raising=False)
    captured = {}

    def fake_load(model_name_or_path):
        captured["path"] = model_name_or_path
        return StubScoringModel({})

    monkeypatch.setattr(reranker_module, "_load_cross_encoder", fake_load)

    result = create_reranker("finetuned")

    assert isinstance(result, CrossEncoderReranker)
    assert captured["path"] == "models/reranker/finetuned"


def test_create_reranker_finetuned_mode_respects_env_var(monkeypatch):
    monkeypatch.setenv("RERANKER_MODEL_PATH", "/custom/checkpoint")
    captured = {}

    def fake_load(model_name_or_path):
        captured["path"] = model_name_or_path
        return StubScoringModel({})

    monkeypatch.setattr(reranker_module, "_load_cross_encoder", fake_load)

    create_reranker("finetuned")

    assert captured["path"] == "/custom/checkpoint"


def test_create_reranker_finetuned_mode_explicit_model_path_wins_over_env_var(monkeypatch):
    monkeypatch.setenv("RERANKER_MODEL_PATH", "/env/checkpoint")
    captured = {}

    def fake_load(model_name_or_path):
        captured["path"] = model_name_or_path
        return StubScoringModel({})

    monkeypatch.setattr(reranker_module, "_load_cross_encoder", fake_load)

    create_reranker("finetuned", model_path="/explicit/checkpoint")

    assert captured["path"] == "/explicit/checkpoint"


def test_create_reranker_invalid_mode_raises_value_error():
    with pytest.raises(ValueError):
        create_reranker("bogus")
