"""Streamlit Frontend for LangGraph MCP Agentic Chatbot.

Provides a reactive, streaming conversational interface featuring:
- Live token-by-token streaming
- Visual status cards during tool executions (DuckDuckGo, Calculator, MCP FastMCP)
- Persistent conversation threads backed by SQLite checkpointing
- Async-to-sync event queue bridge for non-blocking UI rendering
"""

import queue
import uuid
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk

try:
    from src.backend import chatbot, retrieve_all_threads, submit_async_task, tools
except ImportError:
    from backend import chatbot, retrieve_all_threads, submit_async_task, tools

# =====================================================================
# Page Configuration & Styling
# =====================================================================
st.set_page_config(
    page_title="LangGraph MCP Agentic Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .badge {
        display: inline-block;
        padding: 0.25em 0.6em;
        font-size: 0.85em;
        font-weight: 600;
        border-radius: 0.375rem;
        background-color: #e9ecef;
        color: #495057;
        margin-right: 0.3rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# State & Thread Utilities
# =====================================================================
def generate_thread_id() -> str:
    """Generate a unique conversation thread ID."""
    return str(uuid.uuid4())


def reset_chat():
    """Initialize a brand-new conversation thread."""
    new_id = generate_thread_id()
    st.session_state["thread_id"] = new_id
    add_thread(new_id)
    st.session_state["message_history"] = []


def add_thread(thread_id: str):
    """Ensure the given thread ID exists in session state list."""
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)


def load_conversation(thread_id: str):
    """Load stored messages from LangGraph checkpoint state."""
    state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
    messages = state.values.get("messages", [])
    history = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            history.append({"role": "user", "content": content})
        elif isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                ]
                content = "".join(text_parts)
            if content:
                history.append({"role": "assistant", "content": str(content)})
    return history


# =====================================================================
# Session Initialization
# =====================================================================
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []

if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()

if "chat_threads" not in st.session_state:
    persisted_threads = retrieve_all_threads()
    st.session_state["chat_threads"] = persisted_threads if persisted_threads else []

add_thread(st.session_state["thread_id"])

# =====================================================================
# Sidebar Navigation & Management
# =====================================================================
with st.sidebar:
    st.title("⚡ LangGraph Agent")
    st.caption("Model Context Protocol (MCP) Enabled")

    if st.button("➕ New Conversation", use_container_width=True, type="primary"):
        reset_chat()
        st.rerun()

    st.divider()
    st.subheader("🛠️ Active Capabilities")
    for t in tools:
        t_name = getattr(t, "name", "tool")
        st.markdown(f"- **`{t_name}`**")

    st.divider()
    st.subheader("💬 Saved Threads")
    for tid in reversed(st.session_state["chat_threads"]):
        is_current = tid == st.session_state["thread_id"]
        label = f"📌 {tid[:8]}..." if not is_current else f"👉 {tid[:8]}... (Active)"
        if st.button(label, key=f"thread_{tid}", use_container_width=True):
            st.session_state["thread_id"] = tid
            st.session_state["message_history"] = load_conversation(tid)
            st.rerun()

    st.divider()
    st.caption("Engine: LangGraph StateGraph | Checkpoint: SQLite aio")

# =====================================================================
# Main Chat Canvas
# =====================================================================
st.markdown('<div class="main-header">Autonomous Agentic Chatbot</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Powered by Google Gemini 2.5, LangGraph Orchestration & Model Context Protocol (MCP)</div>',
    unsafe_allow_html=True,
)

# Display active thread badge
st.markdown(
    f'<span class="badge">Session ID: {st.session_state["thread_id"]}</span>'
    f'<span class="badge">Tools Online: {len(tools)}</span>',
    unsafe_allow_html=True,
)
st.write("")

# Render message history
for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User input field
user_input = st.chat_input("Ask a question, request calculations, search web, or query stock prices...")

if user_input:
    # Append & display human prompt
    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    config_payload = {
        "configurable": {"thread_id": st.session_state["thread_id"]},
        "metadata": {"thread_id": st.session_state["thread_id"]},
        "run_name": "chat_turn",
    }

    # Assistant streaming response container
    with st.chat_message("assistant"):
        status_holder = {"box": None}

        def stream_generator():
            event_queue: queue.Queue = queue.Queue()

            async def _run_stream():
                try:
                    async for message_chunk, metadata in chatbot.astream(
                        {"messages": [HumanMessage(content=user_input)]},
                        config=config_payload,
                        stream_mode="messages",
                    ):
                        event_queue.put((message_chunk, metadata))
                except Exception as exc:
                    event_queue.put(("error", exc))
                finally:
                    event_queue.put(None)

            submit_async_task(_run_stream())

            while True:
                item = event_queue.get()
                if item is None:
                    break
                message_chunk, metadata = item
                if message_chunk == "error":
                    raise metadata

                # Display visual tool invocation status
                if isinstance(message_chunk, ToolMessage):
                    tool_name = getattr(message_chunk, "name", "external tool")
                    if status_holder["box"] is None:
                        status_holder["box"] = st.status(
                            f"⚙️ Running `{tool_name}` ...", expanded=True
                        )
                    else:
                        status_holder["box"].update(
                            label=f"⚙️ Running `{tool_name}` ...",
                            state="running",
                            expanded=True,
                        )

                # Stream response tokens
                if isinstance(message_chunk, AIMessageChunk) and message_chunk.content:
                    content = message_chunk.content
                    if isinstance(content, str):
                        yield content
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and "text" in part:
                                yield part["text"]
                            elif isinstance(part, str):
                                yield part

        try:
            ai_message = st.write_stream(stream_generator())
        except Exception as err:
            st.error(f"Execution Error: {err}")
            ai_message = f"An error occurred while generating the response: {err}"

        # Finalize tool indicator status
        if status_holder["box"] is not None:
            status_holder["box"].update(
                label="✅ Tool execution completed", state="complete", expanded=False
            )

    # Persist assistant message in UI history
    st.session_state["message_history"].append(
        {"role": "assistant", "content": ai_message}
    )
