"""Test for checking the 2-turn conversation memory."""

from pathlib import Path
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_community.chat_message_histories import SQLChatMessageHistory

from src.agent import memory
import src.agent.graph as graph_module 


def test_memory_persistence(monkeypatch,tmp_path: Path):
    """ 
    Practical test:
    1) Call agent once with session_id="u1"
    2) Call again with same session_id="u1" and check if the memory is preserved
    3) Verify second call recieves prior history
    4) Verify SQL history contains both user turns 
    """
    db_path = tmp_path / "chat_history.db"
    connection_string = f"sqlite:///{db_path}"

    def test_chat_history(session_id: str, connection_string_override=None):
        return SQLChatMessageHistory(
            session_id=session_id,
            connection=connection_string,
        )
    
    # force memory layer to use temp sqlite db (isolated test)
    monkeypatch.setattr(memory, "get_chat_history", test_chat_history)

    class FakeApp:
        def __init__(self):
            self.call_message_lengths = []

        def invoke(self, inputs: dict):
            all_messages = inputs["messages"]
            self.call_message_lengths.append(len(all_messages))
        
            # fake 'model response' so agent can store it 
            last_user_text = all_messages[-1].content if all_messages else "no input"
            ai = AIMessage(content=f"Echo: {last_user_text}")

            return {
                "messages": all_messages + [ai],
                "documents": [],
                "current_plan": "",
                "iteration_count": 1,
            }
        
    fake_app = FakeApp()

    # replace graph creation to avoid calling the LLM or vectorstore
    monkeypatch.setattr(graph_module, "create_agent_graph", lambda: fake_app)

    agent = memory.create_agent_with_memory()
    session_id = "u1"

    # turn 1 
    out1 = agent(
        inputs={
            "messages": [HumanMessage(content="My project is about RAG over PDFs.")],
            "documents": [],
            "current_plan": "",
            "iteration_count": 0,
        },
        session_id=session_id
    )
    assert out1["messages"][-1].content.startswith("Echo:")

    # turn 2 (same session_id should include prior conversation)
    out2 = agent(
        inputs={
            "messages": [HumanMessage(content="What is my project about?")],
            "documents": [],
            "current_plan": "",
            "iteration_count": 0,
        },
        session_id=session_id
    )
    assert out2["messages"][-1].content.startswith("Echo:")

    # key assertion - second call got more context than first call
    assert fake_app.call_message_lengths[1] > fake_app.call_message_lengths[0]

    # verify persistent SQL history contains both user messages 
    history = SQLChatMessageHistory(session_id=session_id, connection=connection_string)
    saved_texts = [m.content for m in history.messages]
        
    assert any("RAG over PDFs" in text for text in saved_texts)
    assert any("What is my project about?" in text for text in saved_texts)