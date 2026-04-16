from pathlib import Path
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document


def load_pdfs(directory: str) -> List[Document]:
    """Load all PDF files from a directory."""
    pdf_path = Path(directory)
    if not pdf_path.exists():
        print(f"Warning: PDF directory {pdf_path} does not exist.")
        return []

    documents = []

    for pdf_file in pdf_path.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()

            # Add source metadata
            for doc in docs:
                doc.metadata["source"] = str(pdf_file)
            documents.extend(docs)
        except Exception as e:
            print(f"Error loading {pdf_file}: {e}")

    return documents


def load_markdown(directory: str) -> List[Document]:
    """Load all Markdown files from a directory."""
    try:
        from langchain_community.document_loaders import UnstructuredMarkdownLoader
    except ImportError as exc:
        raise ImportError(
            "Markdown ingestion requires the optional 'markdown' dependencies. "
            "Install them with: pip install -r requirements-optional.txt"
        ) from exc

    md_path = Path(directory)
    if not md_path.exists():
        print(f"Warning: Markdown directory {md_path} does not exist.")
        return []

    documents = []

    for md_file in md_path.glob("*.md"):
        try:
            loader = UnstructuredMarkdownLoader((md_file))
            docs = loader.load()
            # add source metadata
            for doc in docs:
                doc.metadata["source"] = str(md_file)
            documents.extend(docs)
        except Exception as e:
            print(f"Error handling {md_file} : {e}")

    return documents
