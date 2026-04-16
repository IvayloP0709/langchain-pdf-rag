from langchain_core.messages import AIMessage, ToolMessage

from src.agent.state import AgentState


def should_continue(state: AgentState) -> str:
    """
    Router function that decides the next node based on the state.

    Returns:
    "tools" if LLM wants to use tools
    "synthesize" if LLM is ready to generate answer
    "end" if max iterations are reached or answer is complete
    """
    messages = state["messages"]
    iteration_count = state.get("iteration_count", 0)
    max_iterations = 5

    # check max iterations
    if iteration_count >= max_iterations:
        return "end"

    if not messages:
        return "end"

    # check last message
    last_message = messages[-1]

    # Case 1: Last message is AIMessage with tool_calls → execute tools
    if (
        isinstance(last_message, AIMessage)
        and hasattr(last_message, "tool_calls")
        and last_message.tool_calls
    ):
        return "tools"

    # Case 2: Last message is ToolMessage → synthesize (tool just finished)
    if isinstance(last_message, ToolMessage):
        return "synthesize"

    # Case 3: Last message is AIMessage without tool_calls → check if it's a final answer
    if isinstance(last_message, AIMessage) and (
        not hasattr(last_message, "tool_calls") or not last_message.tool_calls
    ):
        # If there are ToolMessages before this, it means we already synthesized
        has_tool_results = any(isinstance(msg, ToolMessage) for msg in messages[:-1])
        if has_tool_results and last_message.content:
            return "end"  # Already synthesized, end

    # Case 4: Last message is HumanMessage → this shouldn't happen after first iteration
    # But if it does, end to prevent loops
    if hasattr(last_message, "content") and not isinstance(last_message, (AIMessage, ToolMessage)):
        # Check if we've already answered
        has_ai_answer = any(
            isinstance(msg, AIMessage) and (not hasattr(msg, "tool_calls") or not msg.tool_calls)
            for msg in messages
        )
        if has_ai_answer:
            return "end"

    # default: end
    return "end"
