from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

import src.api.app as api_app


def test_health_ok():
    client = TestClient(api_app.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_empty(monkeypatch):
    """Test to check if an empty question returns a 400 error."""
    client = TestClient(api_app.app)
    monkeypatch.setattr(api_app, "_ensure_runtime_ready", lambda: None)

    response = client.post("/ask", json={"question": "   "})

    assert response.status_code == 400
    assert "Question cannot be empty" in response.json()["detail"]


def test_chat_empty(monkeypatch):
    """Test to check if an empty question in chat returns a 400 error."""
    client = TestClient(api_app.app)
    monkeypatch.setattr(api_app, "_ensure_runtime_ready", lambda: None)

    response = client.post("/chat/demo", json={"message": "   "})

    assert response.status_code == 400
    assert "Message cannot be empty" in response.json()["detail"]


def test_ask_returns_answer_and_resources(monkeypatch):
    """Test to check if a valid question returns an answer and sources."""
    client = TestClient(api_app.app)

    class FakeGraph:
        def invoke(self, _state):
            return {
                "messages": [
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
                ],
                "documents": [],
            }

    monkeypatch.setattr(api_app, "_ensure_runtime_ready", lambda: None)
    monkeypatch.setattr(api_app, "_ensure_vectorstore_loaded", lambda _p: None)
    monkeypatch.setattr(api_app, "_get_graph", lambda: FakeGraph())

    response = client.post("/ask", json={"question": "What is RAG?"})
    body = response.json()

    assert response.status_code == 200
    assert "answer" in body and body["answer"]
    assert "sources" in body and len(body["sources"]) == 1
    assert body["sources"][0]["source"] == "data/papers/sample.pdf"


def test_ingest_failure(monkeypatch):
    """Test to check if ingestion failure returns a 400 error."""
    client = TestClient(api_app.app)

    monkeypatch.setattr(api_app, "_ensure_runtime_ready", lambda: None)
    monkeypatch.setattr(api_app, "populate_vectorstore", lambda **kwargs: None)

    response = client.post(
        "/ingest",
        json={
            "pdf_directory": "missing",
            "md_directory": "missing",
            "persist_directory": "missing",
        },
    )

    assert response.status_code == 400
    assert "Ingestion failed" in response.json()["detail"]
