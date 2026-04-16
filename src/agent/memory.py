from typing import List

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import BaseMessage


class SimpleMemory:
    """Simple in-memory conversation history."""

    def __init__(self, max_messages: int = 20):
        self.messages: List[BaseMessage] = []
        self.max_messages = max_messages

    def add_message(self, message: BaseMessage):
        """Add a message to history."""
        self.messages.append(message)

        # keep only last n messages
        if len(self.messages) >= self.max_messages:
            self.messages = self.messages[-self.max_messages :]

    def get_messages(self) -> List[BaseMessage]:
        """Get all messages."""
        return self.messages

    def clear(self):
        """Clear history."""
        self.messages = []


def get_chat_history(session_id: str, connection_string: str = "sqlite:///chat_history.db"):
    """
    Get a persistent chat history for a session.

    Args:
        session_id: unique identifier for the conversation
        connection_string: database connection string

    Returns:
        SQLChatMessageHistory instance
    """
    return SQLChatMessageHistory(session_id=session_id, connection=connection_string)


# update graph so it uses history
def create_agent_with_memory():
    """Create agent that uses persistent memory."""
    from src.agent.graph import create_agent_graph

    app = create_agent_graph()

    # wrap invoke to add memory
    def invoke_with_memory(inputs: dict, session_id: str):
        # load history
        history = get_chat_history(session_id)
        past_messages = history.messages

        # combine past messages with new input
        all_messages = past_messages + inputs["messages"]

        # run agent
        result = app.invoke({**inputs, "messages": all_messages})

        # save new messages to history
        for msg in inputs["messages"]:
            history.add_user_message(msg.content if hasattr(msg, "content") else str(msg))

        for msg in result["messages"][len(all_messages) :]:
            history.add_ai_message(msg.content if hasattr(msg, "content") else str(msg))

        return result

    return invoke_with_memory
