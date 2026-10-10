"""LangGraph Agent Backend Orchestration.

Configures an asynchronous state graph utilizing:
1. Google Gemini Generative AI model
2. Dual-tool paradigm: Local native tools (DuckDuckGo Search, Arithmetic Calculator)
   and external RPC tools via Model Context Protocol (FastMCP)
3. Checkpointed state persistence using AsyncSqliteSaver
4. Dedicated background event loop thread for non-blocking UI streaming
"""

import sys
import asyncio
import threading
import logging
from typing import TypedDict, Annotated, List, Optional
from pathlib import Path

import aiosqlite
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool, BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

try:
    from src.config import DEFAULT_MODEL, DATABASE_PATH, MCP_SERVER_SCRIPT
except ImportError:
    from config import DEFAULT_MODEL, DATABASE_PATH, MCP_SERVER_SCRIPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_backend")

load_dotenv()

# =====================================================================
# Dedicated Async Event Loop for Streamlit / Multi-Threaded Hosts
# =====================================================================
_ASYNC_LOOP = asyncio.new_event_loop()
_ASYNC_THREAD = threading.Thread(target=_ASYNC_LOOP.run_forever, daemon=True)
_ASYNC_THREAD.start()


def _submit_async(coro):
    """Submit a coroutine to run on the background persistent event loop."""
    return asyncio.run_coroutine_threadsafe(coro, _ASYNC_LOOP)


def run_async(coro):
    """Synchronously block and return result of a coroutine executed in background loop."""
    return _submit_async(coro).result()


def submit_async_task(coro):
    """Schedule a coroutine on the background event loop without blocking."""
    return _submit_async(coro)


# =====================================================================
# 1. Foundation Model Initialization
# =====================================================================
llm = ChatGoogleGenerativeAI(
    model=DEFAULT_MODEL,
    temperature=0.2,
)

# =====================================================================
# 2. Tool Definitions & MCP Integration
# =====================================================================
search_tool = DuckDuckGoSearchRun()


@tool
def calculator(first_no: float, second_no: float, operation: str) -> str:
    """Performs basic arithmetic operations between two numbers.

    Args:
        first_no: The first operand.
        second_no: The second operand.
        operation: The arithmetic operation to execute ('add', 'sub', 'mul', 'div').
    """
    op = operation.lower().strip()
    if op in ("add", "+", "plus"):
        return str(first_no + second_no)
    elif op in ("sub", "subtract", "-", "minus"):
        return str(first_no - second_no)
    elif op in ("mul", "multiply", "*", "times"):
        return str(first_no * second_no)
    elif op in ("div", "divide", "/"):
        if second_no == 0:
            return "Error: Division by zero is undefined."
        return str(first_no / second_no)
    return f"Error: Unsupported operation '{operation}'. Supported: add, sub, mul, div."


def _init_mcp_client() -> MultiServerMCPClient:
    """Configure stdio client for Model Context Protocol servers."""
    return MultiServerMCPClient(
        {
            "stock_price_server": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [MCP_SERVER_SCRIPT],
            }
        }
    )


def load_mcp_tools() -> List[BaseTool]:
    """Dynamically discover and load tools exposed by registered MCP servers."""
    try:
        client = _init_mcp_client()
        discovered = run_async(client.get_tools())
        logger.info("Successfully discovered %d tool(s) via MCP.", len(discovered))
        return discovered
    except Exception as exc:
        logger.warning("Failed to initialize MCP tools (%s). Continuing with native tools.", exc)
        return []


mcp_tools = load_mcp_tools()
tools: List[BaseTool] = [search_tool, calculator, *mcp_tools]
llm_with_tools = llm.bind_tools(tools) if tools else llm

# =====================================================================
# 3. State Schema & Graph Nodes
# =====================================================================
class ChatState(TypedDict):
    """Graph state tracking the sequence of conversational messages."""
    messages: Annotated[List[BaseMessage], add_messages]


async def chat_node(state: ChatState):
    """Processes messages with LLM and returns response or tool call requests."""
    messages = state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(tools) if tools else None

# =====================================================================
# 4. Checkpointer & Graph Compilation
# =====================================================================
async def _init_checkpointer() -> AsyncSqliteSaver:
    """Initialize persistent SQLite checkpointer asynchronously."""
    db_file = Path(DATABASE_PATH)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(database=str(db_file))
    return AsyncSqliteSaver(conn)


checkpointer = run_async(_init_checkpointer())

# Build the state graph
graph = StateGraph(ChatState)
graph.add_node("chat_node", chat_node)
graph.add_edge(START, "chat_node")

if tool_node:
    graph.add_node("tools", tool_node)
    graph.add_conditional_edges("chat_node", tools_condition)
    graph.add_edge("tools", "chat_node")
else:
    graph.add_edge("chat_node", END)

chatbot = graph.compile(checkpointer=checkpointer)

# =====================================================================
# 5. Thread Management Utilities
# =====================================================================
async def _alist_threads() -> List[str]:
    """Retrieve all saved thread identifiers from checkpoint database."""
    all_threads = set()
    async for checkpoint in checkpointer.alist(None):
        thread_id = checkpoint.config.get("configurable", {}).get("thread_id")
        if thread_id:
            all_threads.add(str(thread_id))
    return sorted(list(all_threads))


def retrieve_all_threads() -> List[str]:
    """Synchronous interface to list all persistent conversation threads."""
    try:
        return run_async(_alist_threads())
    except Exception as exc:
        logger.error("Failed to retrieve conversation threads: %s", exc)
        return []
