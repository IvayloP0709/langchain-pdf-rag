import argparse
import time

PROCESS_START = time.perf_counter()

def initialize_vectorstore(persist_directory: str):
    """Load embeddings and vectorstore, then inject it into agent tools."""
    from src.ingestion.embedders import get_embedding_model
    from src.retrieval.vectorstore import load_vectorstore
    from src.agent.tools import set_vectorstore

    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings, persist_directory)
    set_vectorstore(vectorstore)

def run_ingest(args: argparse.Namespace) -> int:
    """Run the document ingestion and vectorstore population."""
    from populate_vectorstore import populate_vectorstore

    vectorstore = populate_vectorstore(
        pdf_directory=args.pdf_directory,
        md_directory=args.md_directory,
        persist_directory=args.persist_directory,
    )

    return 0 if vectorstore is not None else 1 

def run_ask(args: argparse.Namespace) -> int:
    """ Ask a question to the agent. """
    if not args.question.strip():
        print("ERROR: Question cannot be empty.")
        return 1

    t0 = time.perf_counter()
    from langchain_core.messages import HumanMessage
    from src.agent.graph import create_agent_graph
    t_imports = time.perf_counter()

    try:
        initialize_vectorstore(args.persist_directory)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("Run ingestion first: python -m src.main ingest")
        return 1
    t_init = time.perf_counter()

    app = create_agent_graph()
    t_graph = time.perf_counter()

    try:
        response = app.invoke(
            {
                "messages": [HumanMessage(content=args.question)],
                "documents": [],
                "current_plan": "",
                "iteration_count": 0,
            }
        )
    except Exception as exc:
        err = str(exc).lower()

        if "insufficient_quota" in err or "rate limit" in err:
            print("ERROR: OpenAI API quota exceeded or rate limited.")
            print("Check billing/usage at https://platform.openai.com/account/usage.")
            return 1

        if "api key" in err or "authentication" in err:
            print("ERROR: OpenAI API key issue.")
            print("Make sure OPENAI_API_KEY is set correctly in environment variables.")
            return 1

        print(f"ERROR: Failed to generate an answer: {exc}")
        return 1

    t_end = time.perf_counter()
    print(
        "Timing: "
        f"pre-ask={t0 - PROCESS_START:.2f}s, "
        f"imports={t_imports - t0:.2f}s, "
        f"init={t_init - t_imports:.2f}s, "
        f"graph={t_graph - t_init:.2f}s, "
        f"agent={t_end - t_graph:.2f}s, "
        f"ask-total={t_end - t0:.2f}s"
    )

    print(f"\nAnswer:\n")
    print(response["messages"][-1].content)  # print the last message (agent's response)
    return 0

def run_chat(args: argparse.Namespace) -> int:
    """Chat interactively with the agent."""
    from langchain_core.messages import HumanMessage
    from src.agent.memory import create_agent_with_memory

    try:
        initialize_vectorstore(args.persist_directory)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("Run ingestion first: python -m src.main ingest")
        return 1
    
    agent = create_agent_with_memory()

    print("Interactive chat started")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not user_input:
            print("Please enter a question.")
            continue

        result = agent(
            inputs={
                "messages": [HumanMessage(content=user_input)],
                "documents": [],
                "current_plan": "",
                "iteration_count": 0,
            },
            session_id=args.session_id,
        )

        print("\nAssistant:")
        print(result["messages"][-1].content)
        print()

    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project CLI: ingest docs and run ask/chat workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Build/update vectorstore from documents.")
    ingest_parser.add_argument("--pdf-directory", default="data/papers", help="Directory containing PDF files.")
    ingest_parser.add_argument("--md-directory", default=None, help="Optional directory containing Markdown files.")
    ingest_parser.add_argument("--persist-directory", default="./chroma_db", help="Vectorstore persistence directory.")
    ingest_parser.set_defaults(func=run_ingest)

    ask_parser = subparsers.add_parser("ask", help="Ask a single question.")
    ask_parser.add_argument("question",help="Question to ask the agent.")
    ask_parser.add_argument("--persist-directory", default="./chroma_db", help="Vectorstore persistence directory.")
    ask_parser.set_defaults(func=run_ask)

    chat_parser = subparsers.add_parser("chat", help="Start interactive chat with persistent memory.")
    chat_parser.add_argument("--session-id", default="default_session", help="Session ID for chat memory.")
    chat_parser.add_argument("--persist-directory", default="./chroma_db", help="Vectorstore persistence directory.")
    chat_parser.set_defaults(func=run_chat)

    return parser 

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
