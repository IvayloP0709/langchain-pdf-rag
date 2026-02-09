from langchain_core.tools import tool
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document 
from typing import List 

# store the vectorstore as a module variable 
_vectorstore: Chroma = None

def set_vectorstore(vectorstore: Chroma):
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
    if _vectorstore is None:
        return "Error: vectorstore not initialized"
    
    # Retrieve documents 
    docs = _vectorstore.similarity_search(query, k=5)

    # Format results 
    if not docs:
        return "No relevant docs found."
    
    result = f"Found {len(docs)} relevant documents:\n\n"
    for i, doc in enumerate(docs, 1):
        result += f"Document {i}:\n{doc.page_content}\n\n"
    
    return result

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