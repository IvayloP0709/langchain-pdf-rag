from pathlib import Path
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


def create_vectorstore(
    documents: List[Document], embeddings: Embeddings, persist_directory: str = "./chroma_db"
) -> Chroma:
    """
    Create a ChromaDB vector store from documents.

    Args:
        documents: List of Document objects (chunked)
        embeddings: Embedding model instance
        persist_directory: Where to save the db

    Returns:
        Chroma vector store instance
    """
    vectorstore = Chroma.from_documents(
        documents=documents, embedding=embeddings, persist_directory=persist_directory
    )

    print(f"Created vectorstore with {len(documents)} documents")
    return vectorstore


def load_vectorstore(embeddings: Embeddings, persist_directory: str = "./chroma_db") -> Chroma:
    """Loads an existing vectorstore from disk."""
    p = Path(persist_directory)
    if not p.exists() or not any(p.iterdir()):
        raise FileNotFoundError(
            f"Vectorstore not found at '{persist_directory}'. Please create it first."
        )

    return Chroma(persist_directory=persist_directory, embedding_function=embeddings)
