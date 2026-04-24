"""Polaris Agent Server — unified backend for all channels.

Start: python -m src.server  (or: uvicorn src.server:app)

Endpoints:
  POST /chat          — non-streaming reply (Feishu, QQ, etc.)
  POST /chat/stream   — SSE streaming reply (Web)
  GET  /sessions      — list all sessions
  POST /sessions/{id}/activate — switch active session
"""

import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.state import AgentState
from src.session_manager import get_session_manager, SessionManager
from src.tools.registry import ToolRegistry
from src.tools.todos import TodoTool
from src.tools.notes import NoteTool
from src.tools.calendar import GoogleCalendarTool
from src.tools.rag import RAGSearchTool
from src.config import CALENDAR_FILE, TODOS_FILE, NOTES_DIR, ARCHIVE_DIR, CHROMA_PERSIST_DIR


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    channel: str = ""


class ChatResponse(BaseModel):
    session_id: str
    response: str
    tool_calls: list[dict] = []


class SessionInfo(BaseModel):
    session_id: str
    name: str
    message_count: int
    last_active: str
    summary: str
    is_active: bool


# --- App lifecycle ---

_tools_registered = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tools_registered
    if not _tools_registered:
        registry = ToolRegistry.get_instance()
        registry.register(TodoTool(data_file=str(TODOS_FILE)))
        registry.register(NoteTool(notes_dir=str(NOTES_DIR), archive_dir=str(ARCHIVE_DIR)))
        registry.register(GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True))
        registry.register(RAGSearchTool(persist_dir=CHROMA_PERSIST_DIR, collection_name="notes"))
        _tools_registered = True

    # Discover and start channel plugins
    from src.channels import ChannelManager
    mgr = ChannelManager()
    mgr.discover_and_start()

    yield


app = FastAPI(title="Polaris Agent Server", lifespan=lifespan)


def _get_active_session(session_id: str | None, session_mgr: SessionManager):
    """Resolve session: use given ID, switch if needed, or use active."""
    if session_id and session_id != session_mgr._active_id:
        result = session_mgr.switch(session_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session_mgr.active_session


# --- Chat endpoints (for external channels: Chainlit UI, remote bots, etc.) ---
# In-process channels (Feishu, future QQ/WeChat) call agent directly, not via HTTP.

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_mgr = get_session_manager()
    _get_active_session(req.session_id, session_mgr)
    response_text, tool_calls = process_message(req.message, session_mgr)
    return ChatResponse(
        session_id=session_mgr.active_session.session_id,
        response=response_text,
        tool_calls=tool_calls,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE streaming — node-level progress via LangGraph astream.

    Yields events as each graph node completes:
      event: node — which node just ran (command, agent, tools)
      event: tool_call — LLM decided to call a tool
      event: message — final response text
      event: done — stream complete
    """
    import json
    from typing import AsyncGenerator

    session_mgr = get_session_manager()
    session = _get_active_session(req.session_id, session_mgr)

    # System commands: wrap in SSE
    if req.message.strip().startswith("/"):
        response_text, _ = process_message(req.message, session_mgr)

        async def cmd_gen() -> AsyncGenerator[str, None]:
            import json as _j
            yield f"event: message\ndata: {_j.dumps({'content': response_text}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {_j.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
        return StreamingResponse(cmd_gen(), media_type="text/event-stream")

    # Normal message: streaming agent pipeline
    agent = get_agent()
    memory = session.memory
    memory.add_message(HumanMessage(content=req.message))
    state = AgentState(
        messages=memory.get_history(),
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )

    async def generate() -> AsyncGenerator[str, None]:
        full_response = ""

        try:
            async for chunk in agent.astream(state, stream_mode="updates"):
                node_name = list(chunk.keys())[0] if chunk else "unknown"
                node_output = list(chunk.values())[0] if chunk else {}

                yield f"event: node\ndata: {json.dumps({'node': node_name}, ensure_ascii=False)}\n\n"

                # Check for tool calls in agent node output
                msgs = node_output.get("messages", [])
                for msg in msgs:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            yield f"event: tool_call\ndata: {json.dumps({'tool': tc.get('name', ''), 'args': tc.get('args', {})}, ensure_ascii=False)}\n\n"

                    elif hasattr(msg, "content") and msg.content:
                        # Collect final AI response
                        if msg.type == "ai" and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                            full_response = msg.content

                # Command node final_response
                if node_output.get("final_response"):
                    full_response = node_output["final_response"]

            yield f"event: message\ndata: {json.dumps({'content': full_response or '无回复'}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        if full_response:
            memory.add_message(AIMessage(content=full_response))
            session_mgr.record_message(req.message, full_response)

    return StreamingResponse(generate(), media_type="text/event-stream")


# --- Session management endpoints ---

@app.get("/sessions")
def list_sessions():
    session_mgr = get_session_manager()
    sessions = session_mgr.list_sessions()
    active_id = session_mgr._active_id
    return {
        "active_session_id": active_id,
        "sessions": [
            SessionInfo(
                session_id=s.session_id,
                name=s.name,
                message_count=s.metadata.get("message_count", 0),
                last_active=s.last_active,
                summary=s.compressor.summary[:100] if s.compressor.summary else "",
                is_active=(s.session_id == active_id),
            )
            for s in sessions
        ],
    }


@app.post("/sessions/{session_id}/activate")
def activate_session(session_id: str):
    session_mgr = get_session_manager()
    result = session_mgr.switch(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"ok": True, "active_session": result.session_id, "name": result.name}


# --- Shared message processing (used by HTTP endpoints & in-process channels) ---

_message_lock = threading.Lock()


def process_message(text: str, session_mgr: SessionManager) -> tuple[str, list[dict]]:
    """统一消息处理入口。全局锁保证同一时间只处理一条消息。"""
    with _message_lock:
        return _process_message_impl(text, session_mgr)


def _process_message_impl(text: str, session_mgr: SessionManager) -> tuple[str, list[dict]]:
    """统一消息处理入口。

    系统命令由 Agent Graph 的 command_node 拦截，不经过 LLM，不残留记忆。
    """
    from langchain_core.messages import HumanMessage, AIMessage
    from src.agent.graph import get_agent

    session = session_mgr.active_session
    memory = session.memory
    agent = get_agent()

    # Save pre-invoke state, then add user message for the graph
    previous_messages = list(memory._messages)
    memory.add_message(HumanMessage(content=text))

    state = AgentState(
        messages=memory.get_history(),
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )

    result = agent.invoke(state)
    response_text = _extract_response(result)
    tool_calls = _extract_tool_calls(result)

    if result.get("final_response"):
        return (response_text, tool_calls)

    # Persist only user msg + final AI reply. Strip intermediate tool messages.
    memory._messages = previous_messages + [
        HumanMessage(content=text),
        AIMessage(content=response_text),
    ]
    session_mgr.record_message(text, response_text)

    return (response_text, tool_calls)


# --- Helpers ---

def _extract_response(result: dict) -> str:
    """Extract the final text response from agent result."""
    response = result.get("final_response", "")
    if response:
        return response
    messages = result.get("messages", [])
    for m in reversed(messages):
        if hasattr(m, "content") and m.content and not (
            hasattr(m, "tool_calls") and m.tool_calls
        ):
            return m.content
    return "抱歉，处理出错了。"


def _extract_tool_calls(result: dict) -> list[dict]:
    """Extract tool call summaries from agent result."""
    calls = []
    messages = result.get("messages", [])
    for m in messages:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                calls.append({
                    "tool": tc.get("name", "unknown"),
                    "args": tc.get("args", {}),
                })
    return calls
