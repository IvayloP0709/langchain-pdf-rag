from dotenv import load_dotenv
load_dotenv()  # Load .env file before creating LLM

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage,  ToolMessage, SystemMessage
from src.agent.state import AgentState
from src.agent.tools import search_documents, ask_clarification

# initialize llm
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# bind tools to llm
tools = [search_documents, ask_clarification]
llm_with_tools = llm.bind_tools(tools)

def planner_node(state:AgentState) -> AgentState:
    """
    Node that uses the LLM to plan the next action.

    The LLM decides whether to search documents, ask for clarification, or answer.
    """
    messages = state["messages"]

    # add system message if this is the first message
    if len(messages) == 1 and isinstance(messages[0], HumanMessage):
        system_message = SystemMessage(content="""You are a research assistant with access to a database of AI-related research papers.
    
Your task is to answer questions about the research papers.

IMPORTANT: Always search the documents FIRST using the search_documents tool before asking for clarification.
Only ask for clarification if the question is truly ambiguous or you cannot find the relevant information after checking the papers.

The database contains computer science research papers, so assume the questions are about CS/AI topics unless explicitly stated otherwise.
""")

        # preprend the system message
        messages = [system_message] + messages

    # Call the llm with tools 
    response = llm_with_tools.invoke(messages)

    # update the state
    return {
        "messages": [response],
        "documents": state.get("documents", []),
        "current_plan": response.content or "",
        "iteration_count": state.get("iteration_count", 0) + 1
    }

def tool_node(state: AgentState) -> AgentState:
    """
    Node that executes tool calls from the LLm
    """
    messages = state["messages"]
    last_message = messages[-1]

    # check if llm wants to use tools 
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return state 
    
    # execute each tool call
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_input = tool_call["args"]

        # call the appropriate tool
        if tool_name == "search_documents":
            result = search_documents.invoke(tool_input)
        elif tool_name == "ask_clarification":
            result = ask_clarification.invoke(tool_input)
        else:
            result = f"Unknown tool: {tool_name}"

        # create tool message 
        tool_messages.append(
            ToolMessage(
                content=result,
                tool_call_id=tool_call["id"]
            )
        )
    
    # update state with tool results 
    return {
        "messages": tool_messages,
        "documents": state.get("documents", []),
        "current_plan": state.get("current_plan", ""),
        "iteration_count": state.get("iteration_count", 0) 
    }

def synthesizer_node(state: AgentState) -> AgentState:
    """
    Node that generates the final answer based on retrieved documents.
    """
    messages = state["messages"]

    # get retrieved documents from tool results 
    documents = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and "Document" in msg.content:
            documents.append(msg.content)
    
    # create context from documents 
    context = "\n\n".join(documents) if documents else "No documents retrieved."

    # generate final answer 
    prompt = f"""Based on the following context, provide a comprehensive answer to the user's question.
    
    Context:
    {context}

    User's question: {messages[0].content if messages else "No question found"}

    Provide a clear, well-structured answer:
    """

    response = llm.invoke(prompt)

    return {
        "messages": [AIMessage(content=response.content)],
        "documents": state.get("documents", []),
        "current_plan": state.get("current_plan", ""),
        "iteration_count": state.get("iteration_count", 0)
    }