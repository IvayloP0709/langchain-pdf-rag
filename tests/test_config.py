import pytest

from src.config import validate_runtime_config


@pytest.fixture(autouse=True)
def _valid_base_env(monkeypatch):
    """Baseline env that passes every check except the one under test."""
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("RETRIEVAL_K", "3")
    monkeypatch.setenv("DOC_PREVIEW_CHARS", "800")
    monkeypatch.delenv("RERANKER_MODE", raising=False)
    monkeypatch.delenv("RERANK_CANDIDATE_K", raising=False)


def test_default_reranker_env_is_valid():
    ok, message = validate_runtime_config()

    assert ok is True
    assert message == "OK"


@pytest.mark.parametrize("mode", ["none", "pretrained", "finetuned"])
def test_valid_reranker_modes(monkeypatch, mode):
    monkeypatch.setenv("RERANKER_MODE", mode)

    ok, message = validate_runtime_config()

    assert ok is True
    assert message == "OK"


def test_invalid_reranker_mode(monkeypatch):
    monkeypatch.setenv("RERANKER_MODE", "bogus")

    ok, message = validate_runtime_config()

    assert ok is False
    assert "RERANKER_MODE" in message


def test_valid_rerank_candidate_k(monkeypatch):
    monkeypatch.setenv("RERANK_CANDIDATE_K", "15")

    ok, message = validate_runtime_config()

    assert ok is True
    assert message == "OK"


def test_rerank_candidate_k_not_an_integer(monkeypatch):
    monkeypatch.setenv("RERANK_CANDIDATE_K", "not-a-number")

    ok, message = validate_runtime_config()

    assert ok is False
    assert "RERANK_CANDIDATE_K" in message


def test_rerank_candidate_k_not_positive(monkeypatch):
    monkeypatch.setenv("RERANK_CANDIDATE_K", "0")

    ok, message = validate_runtime_config()

    assert ok is False
    assert "RERANK_CANDIDATE_K" in message
