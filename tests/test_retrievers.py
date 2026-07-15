import src.retrieval.retrievers as retrievers
from src.retrieval.retrievers import create_retriever


class FakeVectorstore:
    def __init__(self, retriever):
        self._retriever = retriever
        self.calls = []

    def as_retriever(self, search_type, search_kwargs):
        self.calls.append({"search_type": search_type, "search_kwargs": search_kwargs})
        return self._retriever


def test_create_retriever_similarity_mode_matches_prior_behavior():
    sentinel_retriever = object()
    vectorstore = FakeVectorstore(sentinel_retriever)

    result = create_retriever(vectorstore, search_type="similarity", k=5)

    assert result is sentinel_retriever
    assert vectorstore.calls == [{"search_type": "similarity", "search_kwargs": {"k": 5}}]


def test_create_retriever_mmr_mode_matches_prior_behavior():
    sentinel_retriever = object()
    vectorstore = FakeVectorstore(sentinel_retriever)

    result = create_retriever(vectorstore, search_type="mmr", k=4)

    assert result is sentinel_retriever
    assert vectorstore.calls == [{"search_type": "mmr", "search_kwargs": {"k": 4, "fetch_k": 12}}]


def test_create_retriever_explicit_none_reranker_mode_is_unchanged():
    sentinel_retriever = object()
    vectorstore = FakeVectorstore(sentinel_retriever)

    result = create_retriever(vectorstore, k=3, reranker_mode="none", candidate_k=15)

    assert result is sentinel_retriever
    assert vectorstore.calls == [{"search_type": "similarity", "search_kwargs": {"k": 3}}]


class FakeDoc:
    def __init__(self, doc_id):
        self.doc_id = doc_id

    def __eq__(self, other):
        return isinstance(other, FakeDoc) and self.doc_id == other.doc_id

    def __repr__(self):
        return f"FakeDoc({self.doc_id})"


class FakeBaseRetriever:
    def __init__(self, docs):
        self.docs = docs
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        return self.docs


class FakeReranker:
    """Deterministically reverses the candidate list, to prove rerank output is used."""

    def rerank(self, query, docs):
        return list(reversed(docs))


def test_create_retriever_pretrained_mode_fetches_candidate_k_reranks_and_truncates(monkeypatch):
    candidates = [FakeDoc(i) for i in range(5)]
    base_retriever = FakeBaseRetriever(candidates)
    vectorstore = FakeVectorstore(base_retriever)

    captured_create_reranker_args = {}

    def fake_create_reranker(mode, model_path=None):
        captured_create_reranker_args["mode"] = mode
        captured_create_reranker_args["model_path"] = model_path
        return FakeReranker()

    monkeypatch.setattr(retrievers, "create_reranker", fake_create_reranker)

    retriever = create_retriever(vectorstore, k=2, reranker_mode="pretrained", candidate_k=5)
    result = retriever.invoke("my query")

    assert vectorstore.calls == [{"search_type": "similarity", "search_kwargs": {"k": 5}}]
    assert base_retriever.queries == ["my query"]
    assert result == list(reversed(candidates))[:2]
    assert captured_create_reranker_args["mode"] == "pretrained"


def test_create_retriever_finetuned_mode_fetches_candidate_k_reranks_and_truncates(monkeypatch):
    candidates = [FakeDoc(i) for i in range(5)]
    base_retriever = FakeBaseRetriever(candidates)
    vectorstore = FakeVectorstore(base_retriever)

    captured_create_reranker_args = {}

    def fake_create_reranker(mode, model_path=None):
        captured_create_reranker_args["mode"] = mode
        captured_create_reranker_args["model_path"] = model_path
        return FakeReranker()

    monkeypatch.setattr(retrievers, "create_reranker", fake_create_reranker)

    retriever = create_retriever(vectorstore, k=2, reranker_mode="finetuned", candidate_k=5)
    result = retriever.invoke("my query")

    assert vectorstore.calls == [{"search_type": "similarity", "search_kwargs": {"k": 5}}]
    assert base_retriever.queries == ["my query"]
    assert result == list(reversed(candidates))[:2]
    assert captured_create_reranker_args["mode"] == "finetuned"
