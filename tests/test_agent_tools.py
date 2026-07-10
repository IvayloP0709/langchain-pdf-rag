import src.agent.tools as tools_module
from src.agent.tools import search_documents, set_vectorstore


class FakeDoc:
    def __init__(self, source, page, content):
        self.metadata = {"source": source, "page": page}
        self.page_content = content


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        return self.docs


class ExplodingVectorstore:
    """A vectorstore whose similarity_search must never be called directly."""

    def similarity_search(self, *args, **kwargs):
        raise AssertionError(
            "similarity_search should not be called directly; use create_retriever"
        )


def test_search_documents_uses_create_retriever(monkeypatch):
    fake_docs = [FakeDoc("data/papers/a.pdf", 0, "hello world")]
    fake_retriever = FakeRetriever(fake_docs)
    captured = {}

    def fake_create_retriever(vectorstore, **kwargs):
        captured["vectorstore"] = vectorstore
        captured["kwargs"] = kwargs
        return fake_retriever

    monkeypatch.setattr(tools_module, "create_retriever", fake_create_retriever)

    vectorstore = ExplodingVectorstore()
    set_vectorstore(vectorstore)
    try:
        result = search_documents.invoke({"query": "hello"})
    finally:
        set_vectorstore(None)

    assert captured["vectorstore"] is vectorstore
    assert fake_retriever.queries == ["hello"]
    assert "data/papers/a.pdf" in result
    assert "hello world" in result


def test_search_documents_passes_reranker_env_vars(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_K", "7")
    monkeypatch.setenv("RERANKER_MODE", "none")
    monkeypatch.setenv("RERANK_CANDIDATE_K", "21")

    captured = {}

    def fake_create_retriever(vectorstore, **kwargs):
        captured["kwargs"] = kwargs
        return FakeRetriever([])

    monkeypatch.setattr(tools_module, "create_retriever", fake_create_retriever)
    set_vectorstore(ExplodingVectorstore())
    try:
        search_documents.invoke({"query": "hello"})
    finally:
        set_vectorstore(None)

    assert captured["kwargs"]["k"] == 7
    assert captured["kwargs"]["reranker_mode"] == "none"
    assert captured["kwargs"]["candidate_k"] == 21
