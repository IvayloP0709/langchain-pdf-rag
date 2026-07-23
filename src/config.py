import os
from typing import Optional, Tuple
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def str_to_bool(s: str) -> bool:
    return s.strip().lower() in {"1", "true", "yes", "on"}


def build_connection_string() -> Optional[str]:
    """
    Build a SQLAlchemy connection string for chat memory.

    Prefers DATABASE_URL as-is if set (this also preserves
    "sqlite:///chat_history.db" as a valid escape hatch for quick local
    iteration, since nothing here requires the URL to be Postgres).
    Otherwise assembles a psycopg-dialect Postgres URL from the discrete
    DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD env vars, matching the
    connection string already stored in SSM for the provisioned RDS instance
    (see docs/decisions.md, issue #39).

    Returns None if neither DATABASE_URL nor the full set of discrete vars
    is configured.
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        return database_url

    host = os.getenv("DB_HOST", "").strip()
    port = os.getenv("DB_PORT", "").strip()
    name = os.getenv("DB_NAME", "").strip()
    user = os.getenv("DB_USER", "").strip()
    password = os.getenv("DB_PASSWORD", "").strip()

    if not all([host, port, name, user, password]):
        return None

    return f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{name}"


def validate_runtime_config() -> Tuple[bool, str]:
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()

    if provider not in {"openai", "local"}:
        return False, (
            f"Invalid EMBEDDING_PROVIDER: '{provider}'. Supported values are 'openai' and 'local'."
        )

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return False, (
            "OPENAI_API_KEY not set in environment variables. "
            "Please set it to use OpenAI embeddings."
        )

    k_raw = os.getenv("RETRIEVAL_K", "3")
    chars_raw = os.getenv("DOC_PREVIEW_CHARS", "800")

    try:
        k = int(k_raw)
        chars = int(chars_raw)
    except ValueError:
        return False, "RETRIEVAL_K and DOC_PREVIEW_CHARS must be integers."

    if k <= 0:
        return False, "RETRIEVAL_K must be a positive integer."
    if chars < 100:
        return False, "DOC_PREVIEW_CHARS should be at least 100 to provide meaningful previews."

    reranker_mode = os.getenv("RERANKER_MODE", "none").strip().lower()
    if reranker_mode not in {"none", "pretrained", "finetuned"}:
        return False, (
            f"Invalid RERANKER_MODE: '{reranker_mode}'. "
            "Supported values are 'none', 'pretrained', and 'finetuned'."
        )

    candidate_k_raw = os.getenv("RERANK_CANDIDATE_K", "15")
    try:
        candidate_k = int(candidate_k_raw)
    except ValueError:
        return False, "RERANK_CANDIDATE_K must be an integer."

    if candidate_k <= 0:
        return False, "RERANK_CANDIDATE_K must be a positive integer."

    if build_connection_string() is None:
        return False, (
            "Postgres connection details not set in environment variables. "
            "Set DATABASE_URL, or all of DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD."
        )

    return True, "OK"
