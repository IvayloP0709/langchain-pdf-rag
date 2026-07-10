import os
from typing import Any

from langchain_core.tools import tool

from src.retrieval.retrievers import create_retriever

# store the vectorstore as a module variable
_vectorstore: Any = None


def set_vectorstore(vectorstore: Any):
    """Set the vectorstore for tools to use."""
    global _vectorstore
    _vectorstore = vectorstore


@tool
def search_documents(query: str) -> str:
    """
    Search the research paper database for relevant information.

    Use this when you need to find specific information from papers.

    Args:
        query: the search query to find relevant documents

    Returns:
        A string containing the retrieved document content
    """
    if not query or not query.strip():
        return "Error: query is empty. Please provide a valid search query."

    if _vectorstore is None:
        return (
            "Error: vectorstore not initialized. "
            "Run 'python populate_vectorstore.py', then set_vectorstore(load_vectorstore(...))."
        )

    k = int(os.getenv("RETRIEVAL_K", "3"))
    max_chars = int(os.getenv("DOC_PREVIEW_CHARS", "800"))
    reranker_mode = os.getenv("RERANKER_MODE", "none")
    candidate_k = int(os.getenv("RERANK_CANDIDATE_K", "15"))

    try:
        retriever = create_retriever(
            _vectorstore, k=k, reranker_mode=reranker_mode, candidate_k=candidate_k
        )
        docs = retriever.invoke(query)
    except Exception as e:
        return f"Error during document search: {e}"

    # Format results
    if not docs:
        return "No relevant docs found."

    lines = [f"Found {len(docs)} relevant documents:"]

    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "unknown")

        text = (doc.page_content or "").strip().replace("\n", " ")
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        lines.append(f"\nDocument {i}: \nSource: {source}\nPage: {page}\nSnippet: {text}")

    return "\n".join(lines)


@tool
def ask_clarification(question: str) -> str:
    """
    Ask the user for clarification about their question.

    Use this when the user's question is ambiguous or you need more information
    to provide a good answer.

    Args:
        question: The clarification question to ask the user

    Returns:
        A message asking the user for clarification
    """
    return f"CLARIFICATION_NEEDED: {question}"
