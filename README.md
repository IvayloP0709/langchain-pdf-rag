# Agent System Documentation

This directory contains a LangGraph-based agentic RAG system that can search research papers and answer questions using retrieval-augmented generation.

## Overview

The agent uses a **ReAct-style** pattern (Reasoning + Acting) where it:
1. **Plans** what action to take (search documents, ask for clarification, or answer)
2. **Executes** tools (searches the vector database)
3. **Synthesizes** a final answer based on retrieved documents

## Architecture

```
┌─────────────┐
│   User      │
│  Question   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  planner_node   │ ◄─── Decides next action
└────────┬────────┘
         │
         ▼
    ┌─────────┐
    │ Router  │ ────► Routes to: tools, synthesizer, or end
    └────┬────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────────┐
│ tools  │ │ synthesizer  │
│  node  │ │    node      │
└───┬────┘ └──────┬───────┘
    │             │
    └──────┬──────┘
           │
           ▼
        ┌─────┐
        │ END │
        └─────┘
```

## File Structure

### Core Files

- **`state.py`**: Defines `AgentState` - the state that flows through the graph
- **`graph.py`**: Creates and compiles the LangGraph workflow
- **`nodes.py`**: Contains the three main nodes:
  - `planner_node`: LLM decides what to do next
  - `tool_node`: Executes tool calls (searches documents)
  - `synthesizer_node`: Generates final answer from retrieved documents
- **`router.py`**: Routing logic that decides which node to go to next
- **`tools.py`**: Tool definitions (search_documents, ask_clarification)
- **`memory.py`**: Persistent conversation memory using SQLite

## How It Works

### 1. Initialization (`graph.py`)

```python
from src.agent.graph import create_agent_graph

app = create_agent_graph()
```

Creates a LangGraph workflow with:
- **Entry point**: `planner` node
- **Nodes**: planner, tools, synthesizer
- **Edges**: 
  - planner → (router) → tools/synthesizer/end
  - tools → planner (always)
  - synthesizer → end (always)

### 2. Running the Agent

```python
result = app.invoke({
    "messages": [HumanMessage(content="What are coding agents?")],
    "documents": [],
    "current_plan": "",
    "iteration_count": 0
})
```

### 3. Flow Example

**Step 1: Planner Node**
- Receives: `HumanMessage("What are coding agents?")`
- Adds system message (first time only)
- LLM decides: "I should search for information about coding agents"
- Returns: `AIMessage(tool_calls=[{"name": "search_documents", ...}])`

**Step 2: Router**
- Sees: `AIMessage` with `tool_calls`
- Routes to: `"tools"`

**Step 3: Tool Node**
- Executes: `search_documents.invoke({"query": "coding agents"})`
- Searches vectorstore, retrieves 5 documents
- Returns: `ToolMessage(content="Found 5 relevant documents...")`

**Step 4: Graph Edge**
- Automatically routes: `tools` → `planner`

**Step 5: Planner Node (2nd call)**
- Receives: Full conversation history including tool results
- LLM sees documents, decides to synthesize answer
- Returns: `AIMessage` (or routes to synthesizer)

**Step 6: Router**
- Sees: `ToolMessage` as last message
- Routes to: `"synthesize"`

**Step 7: Synthesizer Node**
- Extracts documents from `ToolMessage`
- Creates context prompt
- Generates final answer using LLM
- Returns: `AIMessage(content="Coding agents are...")`

**Step 8: Graph Edge**
- Automatically routes: `synthesizer` → `END`

## State Structure

```python
AgentState = {
    "messages": List[BaseMessage],      # Conversation history (appended)
    "documents": List[Document],        # Retrieved documents (replaced)
    "current_plan": str,                # LLM's current plan (replaced)
    "iteration_count": int              # Number of planner iterations (incremented)
}
```

**Important**: `messages` uses `Annotated[List[BaseMessage], add]` which means LangGraph automatically appends new messages instead of replacing them.

## Memory System

### Basic Agent (No Memory)

```python
from src.agent.graph import create_agent_graph

app = create_agent_graph()
result = app.invoke({"messages": [HumanMessage("Hello")], ...})
```

### Agent with Persistent Memory

```python
from src.agent.memory import create_agent_with_memory

agent = create_agent_with_memory()

# First call
result1 = agent(
    inputs={"messages": [HumanMessage("What are coding agents?")]},
    session_id="user_123"
)

# Second call - remembers previous conversation
result2 = agent(
    inputs={"messages": [HumanMessage("How do they work?")]},
    session_id="user_123"  # Same session_id = same conversation
)
```

**How memory works:**
1. Loads past messages from SQLite database (by `session_id`)
2. Combines past + new messages
3. Runs agent with full context
4. Saves new messages to database

## Tools

### `search_documents(query: str) -> str`

Searches the vector database for relevant documents.

**Usage:**
```python
from src.agent.tools import search_documents, set_vectorstore
from src.retrieval.vectorstore import load_vectorstore
from src.ingestion.embedders import get_embedding_model

# Initialize vectorstore
embeddings = get_embedding_model()
vectorstore = load_vectorstore(embeddings)
set_vectorstore(vectorstore)  # Makes it available to tools

# Now tools can use it
result = search_documents.invoke({"query": "coding agents"})
```

### `ask_clarification(question: str) -> str`

Asks the user for clarification (rarely used - agent prefers to search first).

## Router Logic

The router (`router.py`) decides the next node based on the last message:

| Last Message Type | Router Decision |
|-------------------|----------------|
| `AIMessage` with `tool_calls` | → `"tools"` |
| `ToolMessage` | → `"synthesize"` |
| `AIMessage` without `tool_calls` + has ToolMessages | → `"end"` |
| `iteration_count >= 5` | → `"end"` |

## Example Usage

### Basic Example

```python
from langchain_core.messages import HumanMessage
from src.agent.graph import create_agent_graph
from src.agent.tools import set_vectorstore
from src.retrieval.vectorstore import load_vectorstore
from src.ingestion.embedders import get_embedding_model

# Setup
embeddings = get_embedding_model()
vectorstore = load_vectorstore(embeddings)
set_vectorstore(vectorstore)

# Create and run agent
app = create_agent_graph()
result = app.invoke({
    "messages": [HumanMessage(content="What are coding agents?")],
    "documents": [],
    "current_plan": "",
    "iteration_count": 0
})

print(result["messages"][-1].content)  # Final answer
```

### With Memory

```python
from src.agent.memory import create_agent_with_memory
from langchain_core.messages import HumanMessage

agent = create_agent_with_memory()

# First question
result1 = agent(
    inputs={"messages": [HumanMessage("What are coding agents?")]},
    session_id="user_123"
)

# Follow-up question (agent remembers context)
result2 = agent(
    inputs={"messages": [HumanMessage("How do they work?")]},
    session_id="user_123"
)
```

## Troubleshooting

### "Error: vectorstore not initialized"

**Problem**: Tools can't find the vectorstore.

**Solution**: Call `set_vectorstore(vectorstore)` before running the agent:
```python
from src.agent.tools import set_vectorstore
set_vectorstore(vectorstore)
```

### Infinite Loop

**Problem**: Agent keeps looping, never ends.

**Solution**: Check router logic - it should detect when a final answer exists and route to `"end"`.

### Agent Asks for Clarification Instead of Searching

**Problem**: LLM doesn't know it should search first.

**Solution**: System message in `planner_node` should instruct it to search first. Check that system message is being added correctly.

## Key Concepts

### ReAct Pattern

**Reasoning**: LLM thinks about what to do  
**Acting**: Executes tools (searches documents)  
**Observing**: Sees tool results  
**Reasoning again**: Decides next step (answer or search more)

### State Management

- **Messages**: Accumulate (append) - full conversation history
- **Documents**: Replace - current retrieved documents
- **Current Plan**: Replace - LLM's current thinking
- **Iteration Count**: Increment - tracks how many planning steps

### Tool Binding

Tools are bound to the LLM using `llm.bind_tools(tools)`. This allows the LLM to:
- See available tools
- Decide when to use them
- Call them with appropriate arguments

## Next Steps

- Add more tools (e.g., web search, code execution)
- Implement checkpointing for state persistence
- Add LangSmith tracing for observability
- Deploy as FastAPI service
