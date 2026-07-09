from statistics import mean
from typing import Any, Dict, List, Optional, Sequence


def _basename(path: str) -> str:
    """Path.name won't split on backslashes on POSIX, so normalize separators
    manually to stay robust to Windows-style source paths in metadata."""
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _get_source_filename(item: Any) -> Optional[str]:
    """Extract a bare filename from either a langchain Document or a source dict
    (as returned by src.agent.sources.extract_sources_from_messages)."""
    if hasattr(item, "metadata"):
        source = item.metadata.get("source")
    else:
        source = item.get("source")

    if not source:
        return None
    return _basename(str(source))


def _get_page(item: Any) -> Optional[str]:
    if hasattr(item, "metadata"):
        page = item.metadata.get("page")
    else:
        page = item.get("page")

    if page is None:
        return None
    return str(page).strip()


def _pages_equal(actual: Optional[str], expected: Optional[int]) -> Optional[bool]:
    if actual is None or expected is None:
        return None
    try:
        return int(actual) == int(expected)
    except (TypeError, ValueError):
        return actual == str(expected)


def compute_retrieval_metrics(
    retrieved: Sequence[Any],
    expected_source: str,
    expected_page: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Compute retrieval quality metrics for a single eval example.

    retrieved: ranked list of langchain Document objects OR source dicts
        (rank 1 = first/best).
    expected_source: path/filename of the gold document; matched on basename.
    expected_page: optional gold page number for a stricter page-level check.

    Returns {"hit": bool, "mrr": float, "precision": float, "page_hit": bool|None}.
    """
    expected_name = _basename(expected_source)
    k = len(retrieved)

    hit = False
    mrr = 0.0
    matches = 0
    page_hit: Optional[bool] = None

    for idx, item in enumerate(retrieved, start=1):
        name = _get_source_filename(item)
        if name != expected_name:
            continue

        matches += 1
        if not hit:
            hit = True
            mrr = 1.0 / idx
            page_hit = _pages_equal(_get_page(item), expected_page)

    precision = matches / k if k else 0.0

    return {"hit": hit, "mrr": mrr, "precision": precision, "page_hit": page_hit}


def aggregate_retrieval_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a list of compute_retrieval_metrics() outputs into run-level stats."""
    if not results:
        return {
            "hit_rate": 0.0,
            "mrr": 0.0,
            "precision": 0.0,
            "page_hit_rate": None,
            "num_examples": 0,
        }

    page_hits = [r["page_hit"] for r in results if r["page_hit"] is not None]

    return {
        "hit_rate": mean(1.0 if r["hit"] else 0.0 for r in results),
        "mrr": mean(r["mrr"] for r in results),
        "precision": mean(r["precision"] for r in results),
        "page_hit_rate": mean(1.0 if p else 0.0 for p in page_hits) if page_hits else None,
        "num_examples": len(results),
    }
