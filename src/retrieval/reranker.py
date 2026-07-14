from typing import Any, List, Optional, Protocol

from langchain_core.documents import Document

PRETRAINED_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class Reranker(Protocol):
    def rerank(self, query: str, docs: List[Document]) -> List[Document]: ...


class CrossEncoderReranker:
    """
    Reranker backed by a sentence-transformers CrossEncoder-compatible scoring model
    (anything exposing `.predict(pairs) -> scores`).
    """

    def __init__(self, model: Any):
        self._model = model

    def rerank(self, query: str, docs: List[Document]) -> List[Document]:
        if not docs:
            return []

        pairs = [(query, doc.page_content) for doc in docs]
        scores = self._model.predict(pairs)
        scored = sorted(zip(scores, docs), key=lambda pair: pair[0], reverse=True)
        return [doc for _, doc in scored]


def _load_cross_encoder(model_name_or_path: str) -> Any:
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name_or_path)


def create_reranker(mode: str, model_path: Optional[str] = None) -> Optional[Reranker]:
    """
    Create a Reranker, mirroring the create_retriever factory pattern.

    Args:
        mode: none / pretrained / finetuned
        model_path: local checkpoint path; only consulted for mode="finetuned"

    Returns:
        None for mode="none", otherwise a Reranker instance.
    """
    if mode == "none":
        return None
    if mode == "pretrained":
        return CrossEncoderReranker(_load_cross_encoder(PRETRAINED_MODEL_NAME))
    if mode == "finetuned":
        raise NotImplementedError(
            "reranker_mode='finetuned' is not implemented yet; "
            "see https://github.com/IvayloP0709/langchain-pdf-rag/issues/4."
        )
    raise ValueError(f"Unknown reranker_mode: {mode!r}")
