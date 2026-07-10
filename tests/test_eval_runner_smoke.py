import json

from langchain_core.messages import AIMessage, ToolMessage

import src.agent.graph as agent_graph
import src.eval.runner as runner
import src.main as main_module
import src.retrieval.retrievers as retrievers
from src.eval.schema import EvalExample, write_eval_set


class FakeDoc:
    def __init__(self, source, page):
        self.metadata = {"source": source, "page": page}


class FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, query):
        return self.docs


class FakeGraph:
    def invoke(self, _state):
        return {
            "messages": [
                ToolMessage(
                    content=(
                        "Document 1:\n"
                        "Source: data/papers/a.pdf\n"
                        "Page: 0\n"
                        "Snippet: some grounded content"
                    ),
                    tool_call_id="tool-1",
                ),
                AIMessage(content="A generated answer."),
            ]
        }


def _write_fixture_eval_set(path):
    examples = [
        EvalExample(
            id="eval_0001",
            question="What is X?",
            reference_answer="X is a thing.",
            expected_source="data/papers/a.pdf",
            expected_page=0,
        ),
        EvalExample(
            id="eval_0002",
            question="What is Y?",
            reference_answer="Y is another thing.",
            expected_source="data/papers/b.pdf",
            expected_page=1,
        ),
    ]
    write_eval_set(str(path), examples)


def test_run_evaluation_smoke(tmp_path, monkeypatch):
    eval_set_path = tmp_path / "eval_set.jsonl"
    _write_fixture_eval_set(eval_set_path)
    output_dir = tmp_path / "runs"

    captured_retriever_kwargs = {}

    def fake_create_retriever(vectorstore, search_type, k, reranker_mode, candidate_k):
        captured_retriever_kwargs.update(
            search_type=search_type, k=k, reranker_mode=reranker_mode, candidate_k=candidate_k
        )
        return FakeRetriever([FakeDoc("data/papers/a.pdf", 0)])

    monkeypatch.setattr(main_module, "initialize_vectorstore", lambda persist_directory: object())
    monkeypatch.setattr(agent_graph, "create_agent_graph", lambda: FakeGraph())
    monkeypatch.setattr(retrievers, "create_retriever", fake_create_retriever)

    summary = runner.run_evaluation(
        eval_set_path=str(eval_set_path),
        persist_directory="unused",
        output_dir=str(output_dir),
        skip_judge=True,
    )

    assert summary["num_examples"] == 2
    assert summary["skip_judge"] is True
    # FakeRetriever/FakeGraph always "retrieve" a.pdf; only eval_0001 expects a.pdf
    assert summary["retrieval_direct"]["hit_rate"] == 0.5
    assert summary["retrieval_agent"]["hit_rate"] == 0.5

    assert captured_retriever_kwargs["reranker_mode"] == "none"
    assert captured_retriever_kwargs["candidate_k"] == 15

    run_dirs = [p for p in output_dir.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    assert (run_dir / "summary.json").exists()
    assert (output_dir / "history.csv").exists()

    lines = (run_dir / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["generated_answer"] == "A generated answer."
    assert first["judge"] is None


def test_run_evaluation_raises_on_empty_eval_set(tmp_path, monkeypatch):
    import pytest

    eval_set_path = tmp_path / "eval_set.jsonl"
    eval_set_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        runner.run_evaluation(eval_set_path=str(eval_set_path))
