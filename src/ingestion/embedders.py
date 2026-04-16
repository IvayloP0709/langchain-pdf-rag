import logging
import os
import warnings

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

# Load environment variables from .env file
load_dotenv()


def _configure_hf_runtime() -> None:
    """Reduce noisy HF/transformers output for normal CLI usage."""
    quiet = os.getenv("HF_QUIET", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not quiet:
        return

    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    logging.getLogger("transformers").setLevel(logging.ERROR)
    warnings.filterwarnings(
        "ignore",
        message=".*unauthenticated requests to the HF Hub.*",
        category=UserWarning,
    )


def get_embedding_model() -> Embeddings:
    """
    Create an embedding model instance.

    Uses OpenAIEmbeddings by default. Local Hugging Face embeddings are
    available when EMBEDDING_PROVIDER=local and the optional dependency group
    is installed.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set in environment variables. "
                "Please set it to use OpenAI embeddings."
            )
        model_name = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddings(model=model_name, openai_api_key=api_key)

    # default - local embeddings
    _configure_hf_runtime()

    model_name = os.getenv(
        "LOCAL_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2",
    )

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACEHUB_API_TOKEN")
    model_kwargs = {"token": token} if token else {}

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError as exc:
        raise ImportError(
            "Local embeddings require the optional 'local' dependencies. "
            "Install them with: pip install -r requirements-optional.txt"
        ) from exc

    return HuggingFaceEmbeddings(model_name=model_name, model_kwargs=model_kwargs)


# Example - test embeddings
if __name__ == "__main__":
    embeddings = get_embedding_model()

    # embed a sentence
    s = "This is a test sentence to test the embeddings model."
    vector = embeddings.embed_query(s)
    print(f"Provider: {os.getenv('EMBEDDING_PROVIDER', 'local')}")
    print(f"Vector dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")
