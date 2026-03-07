# populate_vectorstore.py
from dotenv import load_dotenv
from src.ingestion.loaders import load_pdfs, load_markdown
from src.ingestion.chunkers import chunk_documents
from src.ingestion.embedders import get_embedding_model
from src.retrieval.vectorstore import create_vectorstore
from pathlib import Path

# Load environment variables (.env file with OPENAI_API_KEY)
load_dotenv()

def populate_vectorstore(
    pdf_directory: str = "data/papers",
    md_directory: str = None,
    persist_directory: str = "./chroma_db"
):
    """
    Load documents, chunk them, and create a vectorstore.
    
    Args:
        pdf_directory: Path to directory containing PDF files
        md_directory: Optional path to directory containing Markdown files
        persist_directory: Where to save the vectorstore
    """

    pdf_path = Path(pdf_directory)
    md_path = Path(md_directory) if md_directory else None

    # check if input paths exist 
    if not pdf_path.exists() and not (md_path and md_path.exists()):
        print("ERROR: No valid input directories found.")
        print(f" Missing {pdf_path}")
        if md_path:
            print(f" Missing {md_path}")
        print("Create data/papers and add PDFs first")
        return None
    
    print("Step 1: Loading documents...")
    documents = []
    
    # Load PDFs
    if pdf_path.exists():
        pdfs = load_pdfs(pdf_directory)
        documents.extend(pdfs)
        print(f"Loaded {len(pdfs)} PDF documents")
    else:
        print(f"PDF directory not found: {pdf_path}")
    
    # Load Markdown files if directory provided
    if md_path:
        if md_path.exists():
            mds = load_markdown(md_directory)
            documents.extend(mds)
            print(f"Loaded {len(mds)} Markdown documents")
        else:
            print(f"Markdown directory not found: {md_path}")
    
    # check if no docs were loaded
    if not documents:
        print("ERROR: No documents found after loading.")
        print("Add files to data/papers and rerun python populate_vectorstore.py")
        return None
    
    print(f"\nStep 2: Chunking {len(documents)} documents...")
    chunks = chunk_documents(documents)
    if not chunks:
        print("ERROR: No chunks created from documents.")
        print("Check your chunking configuration and document formats.")
        return None
    
    print(f"  Created {len(chunks)} chunks")
    
    print("\nStep 3: Creating embeddings and vectorstore...")
    embeddings = get_embedding_model()
    vectorstore = create_vectorstore(chunks, embeddings, persist_directory)
    
    print(f"\nDone! Vectorstore created with {len(chunks)} chunks")
    print(f"Saved to: {persist_directory}")
    return vectorstore

if __name__ == "__main__":
    # Adjust paths to match your document locations
    populate_vectorstore(
        pdf_directory="data/papers",  # Change to your PDF directory
        # md_directory="data/docs",   # Uncomment if you have Markdown files
    )
