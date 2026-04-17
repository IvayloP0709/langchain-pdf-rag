import re
from typing import List

from fastapi import FastAPI, HTTPException
from langchain_core.messages import ToolMessage

from populate_vectorstore import populate_vectorstore
from src.agent.graph import create_agent_graph
from src.agent.memory import create_agent_with_memory
from src.api.schemas import (
    AskRequest,
    AskResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    IngestRequest,
    IngestResponse,
    SourceBlock,
)
from src.config import validate_runtime_config
from src.main import build_initial_state, format_agent_error, initialize_vectorstore

app = FastAPI(title="langchain-pdf-rag API", version="0.1.0")

_agent_graph = None
_memory_agent = None
_initialized_persist_dir = None


def _ensure_runtime_ready() -> None:
    """Ensure that the runtime environment is properly configured."""
    ok, message = validate_runtime_config()
    if not ok:
        raise HTTPException(status_code=400, detail=message)


def _ensure_vectorstore_loaded(persist_directory: str) -> None:
    """Ensure that the vectorstore is loaded and ready."""
    global _initialized_persist_dir
    if _initialized_persist_dir == persist_directory:
        return

    try:
        initialize_vectorstore(persist_directory)
        _initialized_persist_dir = persist_directory
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{exc} Run ingestion first via POST /ingest or with 'python -m src.main ingest'."
            ),
        ) from exc


def _get_graph():
    """Get or create the agent graph."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


def _get_memory_agent():
    """Get or create the memory agent."""
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = create_agent_with_memory()
    return _memory_agent


def _extract_sources(messages) -> List[SourceBlock]:
    """
    Extract source information from the agent's messages.
    Expected format includes sections like:
    Document 1:
    <snippet>
    """
    sources: List[SourceBlock] = []
    pattern = re.compile(r"Document\s+(\d+):\n?(.*?)\s*(?=\nDocument\s+\d+:|\Z)", re.DOTALL)

    for msg in messages or []:
        if not isinstance(msg, ToolMessage):
            continue

        content = msg.content if isinstance(msg.content, str) else ""
        if not content:
            continue

        for match in pattern.finditer(content):
            rank = int(match.group(1))
            block = match.group(2).strip()
            if not block:
                continue

            source_match = re.search(r"Source:\s*(.+)", block, flags=re.IGNORECASE)
            source = source_match.group(1).strip() if source_match else "unknown"

            # remove header lines from snippet
            snippet = re.sub(r"(?im)^Source:\s*.*$", "", block)
            snippet = re.sub(r"(?im)^Page:\s*.*$", "", snippet)
            snippet = re.sub(r"(?im)^Snippet:\s*", "", snippet).strip()

            sources.append(SourceBlock(source=source, snippet=snippet[:800], rank=rank))

    return sources


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.post("/ingest", response_model=IngestResponse)
def ingest(payload: IngestRequest) -> IngestResponse:
    """Endpoint to trigger document ingestion."""
    _ensure_runtime_ready()

    vectorstore = populate_vectorstore(
        pdf_directory=payload.pdf_directory,
        md_directory=payload.md_directory,
        persist_directory=payload.persist_directory,
    )

    if vectorstore is None:
        raise HTTPException(
            status_code=400,
            detail="Ingestion failed. Check input directories and document contents.",
        )

    return IngestResponse(
        status="ok",
        message="Ingestion completed successfully.",
        persist_directory=payload.persist_directory,
    )


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    """Endpoint to ask a question to the agent."""
    _ensure_runtime_ready()

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    _ensure_vectorstore_loaded(payload.persist_directory)
    graph = _get_graph()

    try:
        result = graph.invoke(build_initial_state(question))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=format_agent_error(exc)) from exc

    answer = result["messages"][-1].content if result.get("messages") else ""
    sources = _extract_sources(result.get("messages", []))

    return AskResponse(
        answer=answer,
        sources=sources,
    )


@app.post("/chat/{session_id}", response_model=ChatResponse)
def chat(session_id: str, payload: ChatRequest) -> ChatResponse:
    """Endpoint to have a conversational interaction with the agent."""
    _ensure_runtime_ready()

    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    _ensure_vectorstore_loaded(payload.persist_directory)
    agent = _get_memory_agent()

    try:
        result = agent(
            inputs=build_initial_state(message),
            session_id=session_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=format_agent_error(exc)) from exc

    answer = result["messages"][-1].content if result.get("messages") else ""
    sources = _extract_sources(result.get("messages", []))

    return ChatResponse(
        session_id=session_id,
        answer=answer,
        sources=sources,
    )
