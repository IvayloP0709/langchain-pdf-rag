from langchain_chroma import Chroma
from langchain_core.retrievers import BaseRetriever


def create_retriever(
    vectorstore: Chroma,
    search_type: str = "similarity",
    k: int = 5,
    reranker_mode: str = "none",
    candidate_k: int = 15,
) -> BaseRetriever:
    """
    Create a retriever from a vectorstore.

    Args:
        vectorstore: Chroma vectorstore instance
        search_type: similarity or mmr (maximal marginal relevance)
        k: number of docs to retrieve
        reranker_mode: none / pretrained / finetuned. Only "none" is implemented
            today; "pretrained"/"finetuned" over-fetch `candidate_k` candidates and
            rerank them before truncating to `k`.
        candidate_k: candidate pool size fetched before reranking, independent of `k`

    Returns:
        Retriever instance
    """
    if reranker_mode != "none":
        raise NotImplementedError(
            f"reranker_mode={reranker_mode!r} is not implemented yet; only 'none' is supported."
        )

    if search_type == "mmr":
        return vectorstore.as_retriever(search_type="mmr", search_kwargs={"k": k, "fetch_k": k * 3})
    else:
        return vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": k})


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
