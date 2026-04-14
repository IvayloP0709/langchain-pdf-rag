"""Tests for latest-question handling in the synthesizer node."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import src.agent.nodes as nodes


class FakeLLM:
    def __init__(self):
        self.last_prompt = None

    def invoke(self, prompt):
        self.last_prompt = prompt
        return AIMessage(content="final answer")


def test_latest_human_question_returns_most_recent_user_message():
    messages = [
        HumanMessage(content="What is RAG?"),
        AIMessage(content="RAG is..."),
        HumanMessage(content="What did I ask just now?"),
    ]

    assert nodes._latest_human_question(messages) == "What did I ask just now?"


def test_synthesizer_node_uses_latest_human_question(monkeypatch):
    fake_llm = FakeLLM()

    monkeypatch.setattr(
        nodes,
        "_get_llm_with_tools",
        lambda: (fake_llm, None),
    )

    state = {
        "messages": [
            HumanMessage(content="What is RAG?"),
            AIMessage(content="tool call or prior response"),
            HumanMessage(content="What did I ask just now?"),
            ToolMessage(content="retrieved context", tool_call_id="1"),
        ],
        "documents": [],
        "current_plan": "",
        "iteration_count": 1,
    }

    result = nodes.synthesizer_node(state)

    assert "What did I ask just now?" in fake_llm.last_prompt
    assert "What is RAG?" not in fake_llm.last_prompt
    assert result["messages"][-1].content == "final answer"
