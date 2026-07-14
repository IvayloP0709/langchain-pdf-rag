from typing import Any, List

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.retrieval.reranker import create_reranker


class _RerankingRetriever:
    """Wraps a base retriever: over-fetches from it, reranks, then truncates to k."""

    def __init__(self, base_retriever: Any, reranker: Any, k: int):
        self._base_retriever = base_retriever
        self._reranker = reranker
        self._k = k

    def invoke(self, query: str) -> List[Document]:
        candidates = self._base_retriever.invoke(query)
        reranked = self._reranker.rerank(query, candidates)
        return reranked[: self._k]


def _base_retriever(vectorstore: Chroma, search_type: str, k: int) -> Any:
    if search_type == "mmr":
        return vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": k * 3})
    return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})


def create_retriever(
    vectorstore: Chroma,
    search_type: str = "similarity",
    k: int = 5,
    reranker_mode: str = "none",
    candidate_k: int = 15,
) -> Any:
    """
    Create a retriever from a vectorstore.

    Args:
        vectorstore: Chroma vectorstore instance
        search_type: similarity or mmr (maximal marginal relevance)
        k: number of docs to retrieve
        reranker_mode: none / pretrained / finetuned. "none" returns the base
            vectorstore retriever unchanged. "pretrained"/"finetuned" fetch
            `candidate_k` candidates from the base retriever, rerank them via
            `create_reranker`, and truncate to the final `k`.
        candidate_k: candidate pool size fetched before reranking, independent of `k`

    Returns:
        Retriever instance exposing `.invoke(query) -> List[Document]`
    """
    if reranker_mode == "none":
        return _base_retriever(vectorstore, search_type, k)

    reranker = create_reranker(reranker_mode)
    base = _base_retriever(vectorstore, search_type, candidate_k)
    return _RerankingRetriever(base, reranker, k)


# Example usage
if __name__ == "__main__":
    from src.ingestion.embedders import get_embedding_model
    from src.retrieval.vectorstore import load_vectorstore

    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings)
    retriever = create_retriever(vectorstore, search_type="mmr", k=5)

    # test retrieval
    results = retriever.invoke("Is it dog")
    print(f"Retrieved {len(results)} documents")
    for i, doc in enumerate(results):
        print(f"\n--- Document {i + 1} ---")
        print(doc.page_content[:200] + "...")
