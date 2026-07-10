import pytest

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


@pytest.mark.parametrize("mode", ["pretrained", "finetuned"])
def test_create_retriever_unimplemented_reranker_modes_raise(mode):
    vectorstore = FakeVectorstore(object())

    with pytest.raises(NotImplementedError):
        create_retriever(vectorstore, k=3, reranker_mode=mode)
