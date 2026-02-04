from langchain_openai import OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv() 

def get_embedding_model() -> Embeddings:
    """
    Create an embedding model instance.

    Uses OpenAI by default, but can be swapped for local embeddings:
    from langchain_community.embeddings import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="...")
    """
    return OpenAIEmbeddings(
        model='text-embedding-3-small',
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

# Example - test embeddings 
if __name__ == "__main__":
    embeddings = get_embedding_model()

    # embed a sentence 
    s = "This is a test sentence to test the embeddings model."
    vector = embeddings.embed_query(s)
    print(f"Vector dimension: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")

