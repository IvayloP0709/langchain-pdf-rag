from src.eval.metrics import aggregate_retrieval_metrics, compute_retrieval_metrics


def _doc(source, page):
    class FakeDoc:
        def __init__(self, source, page):
            self.metadata = {"source": source, "page": page}

    return FakeDoc(source, page)


def test_hit_at_rank_one():
    retrieved = [
        _doc("data/papers/target.pdf", 2),
        _doc("data/papers/other.pdf", 0),
    ]
    metrics = compute_retrieval_metrics(retrieved, "data/papers/target.pdf", expected_page=2)

    assert metrics["hit"] is True
    assert metrics["mrr"] == 1.0
    assert metrics["precision"] == 0.5
    assert metrics["page_hit"] is True


def test_hit_at_lower_rank_reduces_mrr():
    retrieved = [
        _doc("data/papers/other.pdf", 0),
        _doc("data/papers/other2.pdf", 0),
        _doc("data/papers/target.pdf", 5),
    ]
    metrics = compute_retrieval_metrics(retrieved, "data/papers/target.pdf")

    assert metrics["hit"] is True
    assert metrics["mrr"] == 1.0 / 3
    assert metrics["precision"] == 1 / 3


def test_no_hit():
    retrieved = [_doc("data/papers/other.pdf", 0)]
    metrics = compute_retrieval_metrics(retrieved, "data/papers/target.pdf")

    assert metrics["hit"] is False
    assert metrics["mrr"] == 0.0
    assert metrics["precision"] == 0.0
    assert metrics["page_hit"] is None


def test_matches_on_basename_not_full_path():
    retrieved = [{"source": "data\\papers\\target.pdf", "page": "3"}]
    metrics = compute_retrieval_metrics(retrieved, "data/papers/target.pdf", expected_page=3)

    assert metrics["hit"] is True
    assert metrics["page_hit"] is True


def test_source_dict_input_page_mismatch():
    retrieved = [{"source": "data/papers/target.pdf", "page": "1"}]
    metrics = compute_retrieval_metrics(retrieved, "data/papers/target.pdf", expected_page=4)

    assert metrics["hit"] is True
    assert metrics["page_hit"] is False


def test_empty_retrieved_list():
    metrics = compute_retrieval_metrics([], "data/papers/target.pdf")

    assert metrics == {"hit": False, "mrr": 0.0, "precision": 0.0, "page_hit": None}


def test_aggregate_retrieval_metrics():
    results = [
        {"hit": True, "mrr": 1.0, "precision": 0.5, "page_hit": True},
        {"hit": False, "mrr": 0.0, "precision": 0.0, "page_hit": None},
        {"hit": True, "mrr": 0.5, "precision": 0.25, "page_hit": False},
    ]
    agg = aggregate_retrieval_metrics(results)

    assert agg["hit_rate"] == 2 / 3
    assert agg["mrr"] == (1.0 + 0.0 + 0.5) / 3
    assert agg["precision"] == (0.5 + 0.0 + 0.25) / 3
    assert agg["page_hit_rate"] == 0.5
    assert agg["num_examples"] == 3


def test_aggregate_empty():
    agg = aggregate_retrieval_metrics([])

    assert agg["num_examples"] == 0
    assert agg["page_hit_rate"] is None
