from langchain_community.document_loaders import PyPDFLoader, UnstructuredMarkdownLoader
from pathlib import Path
from typing import List
from langchain_core.documents import Document

def load_pdfs(directory:str) -> List[Document]:
    """Load all PDF files from a directory."""
    pdf_path = Path(directory)
    documents = []

    for  pdf_file in pdf_path.glob("*.pdf"):
        try:
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()
            # Add source metadata
            for doc in docs:
                doc.metadata['source'] = str(pdf_file)
            documents.extend(docs)
        except Exception as e:
            print(f"Error loading {pdf_file}: {e}")
    
    return documents


def load_markdown(directory:str) -> List[Document]:
    """Load all Markdown files from a directory."""
    md_path = Path(directory)
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

