from operator import add
from typing import Annotated, List, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    State that flows through the agent graph.

    - messages: conversation history (appended to)
    - documents: retrieved documents (replaced)
    - current_plan: agent's current plan (replaced)
    - iteration_count: number of iterations (incremented)
    """

    messages: Annotated[List[BaseMessage], add]  # add = append to list
    documents: List[Document]  # replaced each time
    current_plan: str  # replaced each time
    iteration_count: int  # incremented
