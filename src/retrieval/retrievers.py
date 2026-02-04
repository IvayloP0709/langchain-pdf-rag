from langchain_chroma import Chroma
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document 
from typing import List


def create_retriever(
    vectorstore: Chroma,
    search_type: str = "similarity",
    k: int = 5
) -> BaseRetriever:
    """
    Create a retriever from a vectorstore.

    Args:
        vectorstore: Chroma vectorstore instance
        search_type: similarity or mmr (maximal marginal relevance)
        k: number of docs to retrieve
    
    Returns:
        Retriever instance
    """
    if search_type == "mmr":
        return vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": k * 3}
        )
    else:
        return vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k}
        )

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
        print(f"\n--- Document {i+1} ---")
        print(doc.page_content[:200] + "...")