from typing import List

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI


def format_docs(docs: List[Document]) -> str:
    """Format retrieved documents into a string for the prompt."""
    return "\n\n".join(f"Document {i + 1}: \n{doc.page_content}" for i, doc in enumerate(docs))


def create_rag_chain(retriever: BaseRetriever, llm: ChatOpenAI):
    """
    Create a RAG chain that retrieves documents and generates answers.

    Args:
        retriever: Retriever instance
        llm: ChatOpenAI instance

    Returns:
        Runnable chain
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """You are a helpful research assistance. Answer question
        only based on the provided content.

    If the content doesn't contain enough information to answer the question,
    say "I don't have enough information in my docs to answer this question."

    Context:
    {context}""",
            ),
            ("human", "{question}"),
        ]
    )

    # Chain - question -> retrieve -> format -> prompt -> llm -> parse
    chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    return chain


# Example usage

if __name__ == "__main__":
    from src.ingestion.embedders import get_embedding_model
    from src.retrieval.retrievers import create_retriever
    from src.retrieval.vectorstore import load_vectorstore

    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings)
    retriever = create_retriever(vectorstore)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    chain = create_rag_chain(retriever, llm)

    response = chain.invoke("What are traces in chat agents?")
    print(response)
