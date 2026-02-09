from langgraph.graph import StateGraph, END
from src.agent.state import AgentState
from src.agent.nodes import planner_node, tool_node, synthesizer_node
from src.agent.router import should_continue
from dotenv import load_dotenv

load_dotenv()

def create_agent_graph():
    """
    Create and compile the LangGraph agent.

    Returns:
        Compiled graph ready to be used.
    """
    # create graph
    workflow = StateGraph(AgentState)

    # add nodes
    workflow.add_node("planner", planner_node)
    workflow.add_node("tools", tool_node)
    workflow.add_node("synthesizer", synthesizer_node)

    # set entry point 
    workflow.set_entry_point("planner")

    # add conditional edges from planner 
    workflow.add_conditional_edges(
        "planner",
        should_continue,
        {
            "tools": "tools",
            "synthesize": "synthesizer", 
            "end": END
        }
    )

    # after tools, go back to planner to evaluate results 
    workflow.add_edge("tools", "planner")

    # after synthesizer, end 
    workflow.add_edge("synthesizer", END)

    # compile graph 
    app = workflow.compile()

    return app

# Example usage 
if __name__ == "__main__":
    from langchain_core.messages import HumanMessage 
    from src.agent.tools import set_vectorstore
    from src.retrieval.vectorstore import load_vectorstore
    from src.ingestion.embedders import get_embedding_model

    # initialize vectorstore
    embeddings = get_embedding_model()
    vectorstore = load_vectorstore(embeddings)
    set_vectorstore(vectorstore)

    # create agent 
    app = create_agent_graph()

    # run agent 
    result = app.invoke({
        "messages": [HumanMessage(content="What are coding agents and how do they work?")],
        "documents": [],
        "current_plan": "",
        "iteration_count": 0
    })

    print("\n" + "="*50)
    print("FINAL ANSWER:")
    print("="*50)
    print(result["messages"][-1].content)
    
    print("\n" + "="*50)
    print("AGENT STATE:")
    print("="*50)
    print(f"Iteration count: {result.get('iteration_count', 0)}")
    print(f"Current plan: {result.get('current_plan', '')}")
    print(f"Number of messages: {len(result.get('messages', []))}")
    print(f"Number of documents: {len(result.get('documents', []))}")
    
    print("\n" + "="*50)
    print("MESSAGE HISTORY:")
    print("="*50)
    for i, msg in enumerate(result.get('messages', [])):
        msg_type = type(msg).__name__
        if hasattr(msg, 'content'):
            content_preview = msg.content[:100] if msg.content else "(no content)"
        else:
            content_preview = str(msg)[:100]
        
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            print(f"{i+1}. {msg_type}: tool_calls={msg.tool_calls}")
        else:
            print(f"{i+1}. {msg_type}: {content_preview}...")
