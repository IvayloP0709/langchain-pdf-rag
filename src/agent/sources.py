import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import ToolMessage

_DOCUMENT_BLOCK_PATTERN = re.compile(
    r"Document\s+(\d+):\n?(.*?)\s*(?=\nDocument\s+\d+:|\Z)", re.DOTALL
)


def extract_sources_from_messages(messages: Any) -> List[Dict[str, Optional[str]]]:
    """
    Extract source information from a LangGraph agent's message trace.

    Expected ToolMessage content format:
    Document 1:
    Source: <path>
    Page: <page>
    Snippet: <text>

    Returns a list of dicts with keys: rank, source, page, snippet.
    """
    sources: List[Dict[str, Optional[str]]] = []

    for msg in messages or []:
        if not isinstance(msg, ToolMessage):
            continue

        content = msg.content if isinstance(msg.content, str) else ""
        if not content:
            continue

        for match in _DOCUMENT_BLOCK_PATTERN.finditer(content):
            rank = int(match.group(1))
            block = match.group(2).strip()
            if not block:
                continue

            source_match = re.search(r"Source:\s*(.+)", block, flags=re.IGNORECASE)
            source = source_match.group(1).strip() if source_match else "unknown"

            page_match = re.search(r"Page:\s*(.+)", block, flags=re.IGNORECASE)
            page = page_match.group(1).strip() if page_match else None

            # remove header lines from snippet
            snippet = re.sub(r"(?im)^Source:\s*.*$", "", block)
            snippet = re.sub(r"(?im)^Page:\s*.*$", "", snippet)
            snippet = re.sub(r"(?im)^Snippet:\s*", "", snippet).strip()

            sources.append({"rank": rank, "source": source, "page": page, "snippet": snippet[:800]})

    return sources
