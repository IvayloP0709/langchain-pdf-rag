# populate_vectorstore.py
from dotenv import load_dotenv
from src.ingestion.loaders import load_pdfs, load_markdown
from src.ingestion.chunkers import chunk_documents
from src.ingestion.embedders import get_embedding_model
from src.retrieval.vectorstore import create_vectorstore

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
    print("Step 1: Loading documents...")
    documents = []
    
    # Load PDFs
    pdfs = load_pdfs(pdf_directory)
    documents.extend(pdfs)
    print(f"  Loaded {len(pdfs)} PDF documents")
    
    # Load Markdown files if directory provided
    if md_directory:
        mds = load_markdown(md_directory)
        documents.extend(mds)
        print(f"  Loaded {len(mds)} Markdown documents")
    
    if not documents:
        print("ERROR: No documents found! Check your directory paths.")
        return
    
    print(f"\nStep 2: Chunking {len(documents)} documents...")
    chunks = chunk_documents(documents)
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
