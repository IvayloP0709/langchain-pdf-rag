from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List

def chunk_documents(
    documents: List[Document],
    chunks_size: int = 1000,
    chunk_overlap: int = 200
) -> List[Document]:
    """
    Split documents into chunks with overlap.
    
    Args:
        documents: list of document objects to chunk
        chunks_size: target size for each chunk
        chunk_overlap: target size of overlap between chunks
        
    Returns:
        List of chunked Document objects
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunks_size=chunks_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        # try to split on these separators in order 
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    chunks = text_splitter.split_documents(documents)

    # add chunk index to metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = i
    
    return chunks 
    