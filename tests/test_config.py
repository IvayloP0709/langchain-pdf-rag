import pytest

from src.config import build_connection_string, validate_runtime_config


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


class TestBuildConnectionString:
    def test_returns_database_url_as_is(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@host:5432/db")

        assert build_connection_string() == "postgresql+psycopg://user:pass@host:5432/db"

    def test_database_url_preserves_sqlite_escape_hatch(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "sqlite:///chat_history.db")

        assert build_connection_string() == "sqlite:///chat_history.db"

    def test_assembles_from_discrete_vars(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "chat_memory")
        monkeypatch.setenv("DB_USER", "app")
        monkeypatch.setenv("DB_PASSWORD", "s3cr3t")

        result = build_connection_string()

        assert result == "postgresql+psycopg://app:s3cr3t@localhost:5432/chat_memory"

    def test_url_encodes_special_characters_in_credentials(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "chat_memory")
        monkeypatch.setenv("DB_USER", "app")
        monkeypatch.setenv("DB_PASSWORD", "p@ss/word!")

        result = build_connection_string()

        assert result == "postgresql+psycopg://app:p%40ss%2Fword%21@localhost:5432/chat_memory"

    def test_database_url_takes_precedence_over_discrete_vars(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://a:b@c:5432/d")
        monkeypatch.setenv("DB_HOST", "other-host")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "other-db")
        monkeypatch.setenv("DB_USER", "other-user")
        monkeypatch.setenv("DB_PASSWORD", "other-pass")

        assert build_connection_string() == "postgresql+psycopg://a:b@c:5432/d"

    def test_returns_none_when_nothing_configured(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)

        assert build_connection_string() is None

    def test_returns_none_when_discrete_vars_incomplete(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.delenv("DB_NAME", raising=False)
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.delenv("DB_PASSWORD", raising=False)

        assert build_connection_string() is None

    def test_raises_when_port_is_not_numeric(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "abc")
        monkeypatch.setenv("DB_NAME", "chat_memory")
        monkeypatch.setenv("DB_USER", "app")
        monkeypatch.setenv("DB_PASSWORD", "secret")

        with pytest.raises(ValueError, match="DB_PORT"):
            build_connection_string()

    def test_url_encodes_special_characters_in_host_and_database(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DB_HOST", "db@internal")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("DB_NAME", "chat/memory")
        monkeypatch.setenv("DB_USER", "app")
        monkeypatch.setenv("DB_PASSWORD", "secret")

        result = build_connection_string()

        from sqlalchemy.engine import make_url

        url = make_url(result)
        assert url.host == "db@internal"
        assert url.database == "chat/memory"
