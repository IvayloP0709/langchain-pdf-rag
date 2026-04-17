import os
from pathlib import Path
from typing import Any, Dict, List

import requests
import streamlit as st


def _api_get(base_url: str, path: str) -> requests.Response:
    """Helper function to make GET requests to the API."""
    return requests.get(f"{base_url}{path}", timeout=60)


def _api_post(base_url: str, path: str, payload: Dict[str, Any]) -> requests.Response:
    """Helper function to make POST requests to the API."""
    return requests.post(f"{base_url}{path}", json=payload, timeout=300)


def _save_uploaded_pdfs(uploaded_files, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0

    for uploaded in uploaded_files:
        out_path = target_dir / uploaded.name
        out_path.write_bytes(uploaded.getbuffer())
        written += 1

    return written


st.set_page_config(page_title="Research Paper Copilot", page_icon="📚", layout="wide")
st.title("Research Paper Copilot UI")
st.caption("Demo UI for ingest, ask, and chat workflows")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

default_api = os.getenv("API_BASE_URL", "http://localhost:8000")

with st.sidebar:
    st.header("Settings")
    api_base_url = st.text_input("API Base URL", value=default_api)
    persist_directory = st.text_input("Vectorstore Persist Directory", value="./chroma_db")
    session_id = st.text_input("Chat Session ID", value="demo")

    if st.button("Health Check"):
        try:
            response = _api_get(api_base_url, "/health")
            response.raise_for_status()
            st.success(f"API is healthy: {response.json()}")
        except Exception as exc:
            st.error(f"Health check failed: {exc}")

tab_ingest, tab_ask, tab_chat = st.tabs(["Ingest", "Ask", "Chat"])

with tab_ingest:
    st.subheader("Ingest Documents")
    uploaded_files = st.file_uploader(
        "Upload PDF files to ingest into the vectorstore",
        type=["pdf"],
        accept_multiple_files=True,
    )

    col_left, col_right = st.columns(2)

    with col_left:
        if st.button("Ingest Uploaded PDFs"):
            if not uploaded_files:
                st.warning("Please upload at least one PDF file to ingest.")
            else:
                upload_dir = Path("data") / "uploads"
                try:
                    count = _save_uploaded_pdfs(uploaded_files, upload_dir)
                    payload = {
                        "pdf_directory": str(upload_dir).replace("\\", "/"),
                        "persist_directory": persist_directory,
                    }
                    response = _api_post(api_base_url, "/ingest", payload)
                    if response.ok:
                        st.success(f"Ingested {count} PDFs successfully.")
                        st.json(response.json())
                    else:
                        st.error(f"Ingestion failed {response.status_code}: {response.text}")
                except Exception as exc:
                    st.error(f"Error during ingestion: {exc}")

    with col_right:
        if st.button("Ingest Existing data/papers"):
            try:
                payload = {
                    "pdf_directory": "data/papers",
                    "persist_directory": persist_directory,
                }
                response = _api_post(api_base_url, "/ingest", payload)
                if response.ok:
                    st.success("Ingested existing data/papers successfully.")
                    st.json(response.json())
                else:
                    st.error(f"Ingestion failed {response.status_code}: {response.text}")
            except Exception as exc:
                st.error(f"Error during ingestion: {exc}")

with tab_ask:
    st.subheader("Ask a One-Off Question")
    ask_text = st.text_area("Enter your question here", value="What is RAG?")
    if st.button("Ask"):
        try:
            payload = {
                "question": ask_text,
                "persist_directory": persist_directory,
            }
            response = _api_post(api_base_url, "/ask", payload)
            if not response.ok:
                st.error(f"Ask failed {response.status_code}: {response.text}")
            else:
                data = response.json()
                st.markdown("### Answer")
                st.write(data.get("answer", ""))

                st.markdown("### Sources")
                for source in data.get("sources", []):
                    with st.expander(f"#{source.get('rank')} - {source.get('source')}"):
                        st.write(source.get("snippet", ""))
        except Exception as exc:
            st.error(f"Error during ask: {exc}")

with tab_chat:
    st.subheader("Session Chat")
    chat_input = st.text_input("Message", value="Summarize RAG in simple terms.")

    if st.button("Send chat message"):
        try:
            payload = {
                "message": chat_input,
                "persist_directory": persist_directory,
            }
            response = _api_post(api_base_url, f"/chat/{session_id}", payload)
            if not response.ok:
                st.error(f"Chat failed {response.status_code}: {response.text}")
            else:
                data = response.json()
                st.session_state.chat_history.append(
                    {
                        "user": chat_input,
                        "assistant": data.get("answer", ""),
                        "sources": data.get("sources", []),
                    }
                )
        except Exception as exc:
            st.error(f"Error during chat: {exc}")

    st.markdown("### Chat History")
    for turn in reversed(st.session_state.chat_history):
        st.markdown(f"**You:** {turn['user']}")
        st.markdown(f"**Assistant:** {turn['assistant']}")
        sources: List[Dict[str, Any]] = turn.get("sources", [])
        if sources:
            with st.expander("Sources"):
                for source in sources:
                    st.markdown(f"- `{source.get('source', 'unknown')}`")
                    st.write(source.get("snippet", ""))
