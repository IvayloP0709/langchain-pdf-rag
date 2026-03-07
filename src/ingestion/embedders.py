from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
import os
from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings

# Load environment variables from .env file
load_dotenv() 

def get_embedding_model() -> Embeddings:
    """
    Create an embedding model instance.

    Uses HuggingFaceEmbeddings by default, but can switch to OpenAIEmbeddings if EMBEDDING_PROVIDER=OpenAI in environment variables.
    """
    provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set in environment variables. Please set it to use OpenAI embeddings."
            )
        return OpenAIEmbeddings(
            model='text-embedding-3-small',
            openai_api_key=api_key
        )

    # default - local embeddings
    model_name = os.getenv(
        "LOCAL_EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    return HuggingFaceEmbeddings(model_name=model_name)

# Example - test embeddings 
if __name__ == "__main__":
    embeddings = get_embedding_model()

    # embed a sentence 
    s = "This is a test sentence to test the embeddings model."
    vector = embeddings.embed_query(s)
    print(f"Provider: {os.getenv('EMBEDDING_PROVIDER', 'local')}")
    print(f"Vector dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")

