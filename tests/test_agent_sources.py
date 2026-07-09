from langchain_core.messages import AIMessage, ToolMessage

from src.agent.sources import extract_sources_from_messages


def test_extracts_source_and_page():
    messages = [
        ToolMessage(
            content=(
                "Document 1:\n"
                "Source: data/papers/sample.pdf\n"
                "Page: 1\n"
                "Snippet: retrieval augmented generation improves factuality"
            ),
            tool_call_id="tool-1",
        ),
        AIMessage(content="RAG combines retrieval with generation."),
    ]

    sources = extract_sources_from_messages(messages)

    assert len(sources) == 1
    assert sources[0]["rank"] == 1
    assert sources[0]["source"] == "data/papers/sample.pdf"
    assert sources[0]["page"] == "1"
    assert "retrieval augmented generation" in sources[0]["snippet"]


def test_multiple_documents_in_one_message():
    content = (
        "Document 1:\n"
        "Source: a.pdf\n"
        "Page: 0\n"
        "Snippet: first snippet\n"
        "Document 2:\n"
        "Source: b.pdf\n"
        "Page: 2\n"
        "Snippet: second snippet"
    )
    messages = [ToolMessage(content=content, tool_call_id="tool-1")]

    sources = extract_sources_from_messages(messages)

    assert [s["source"] for s in sources] == ["a.pdf", "b.pdf"]
    assert [s["page"] for s in sources] == ["0", "2"]


def test_missing_page_returns_none():
    content = "Document 1:\nSource: a.pdf\nSnippet: no page info here"
    messages = [ToolMessage(content=content, tool_call_id="tool-1")]

    sources = extract_sources_from_messages(messages)

    assert sources[0]["page"] is None


def test_ignores_non_tool_messages():
    messages = [AIMessage(content="Document 1:\nSource: a.pdf\nSnippet: fake")]

    assert extract_sources_from_messages(messages) == []


def test_empty_messages():
    assert extract_sources_from_messages([]) == []
    assert extract_sources_from_messages(None) == []
