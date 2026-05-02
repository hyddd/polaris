"""Polaris Agent Server — unified backend for all channels.

Start: python -m src.server  (or: uvicorn src.server:app)

Endpoints:
  POST /chat          — non-streaming reply (Feishu, QQ, etc.)
  POST /chat/stream   — SSE streaming reply (Web)
  POST /sessions      — create new session
  GET  /sessions      — list all sessions
  GET  /sessions/{id} — session detail + message history
  POST /sessions/{id}/activate — switch active session
"""

import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import get_session_manager, SessionManager
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

# Enable HTTP request logging for LLM API calls
import logging
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("openai").setLevel(logging.INFO)

_tools_registered = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tools_registered
    if not _tools_registered:
        registry = ToolRegistry.get_instance()
        registry.register(TodoTool(data_file=str(TODOS_FILE)))
        registry.register(NoteTool(notes_dir=str(NOTES_DIR), archive_dir=str(ARCHIVE_DIR), persist_dir=str(CHROMA_PERSIST_DIR), collection_name="notes"))
        registry.register(GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True))
        registry.register(RAGSearchTool(persist_dir=CHROMA_PERSIST_DIR, collection_name="notes"))
        _tools_registered = True

    # Check embedding config (cloud API, no local model to pre-warm)
    try:
        from src.data_layer.vector_store import check_embedding_config
        check_embedding_config()
    except Exception:
        pass

    # Discover and start channel plugins
    from src.channels import ChannelManager
    mgr = ChannelManager()
    mgr.discover_and_start()

    yield


app = FastAPI(title="Polaris Agent Server", lifespan=lifespan)

# Admin frontend static files
ADMIN_DIR = Path(__file__).parent.parent / "admin" / "dist"


def _get_active_session(session_id: str | None, session_mgr: SessionManager, channel: str = "default"):
    """Resolve session: use given ID, switch if needed, or use active."""
    if session_id:
        result = session_mgr.switch(session_id, channel)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session_mgr.active_session(channel)


# --- Chat endpoints (for external channels: admin UI, remote bots, etc.) ---
# In-process channels (Feishu, QQ) call agent directly, not via HTTP.

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_mgr = get_session_manager()
    channel = req.channel or "default"
    _get_active_session(req.session_id, session_mgr, channel)
    response_text, tool_calls = process_message(req.message, session_mgr, channel)
    return ChatResponse(
        session_id=session_mgr.active_session(channel).session_id,
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
    channel = req.channel or "default"
    session = _get_active_session(req.session_id, session_mgr, channel)

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
    old_messages = list(memory._messages)
    human_msg = HumanMessage(content=req.message)
    state = AgentState(
        messages=old_messages + [human_msg],
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=session.pending_action,
        streaming=True,
        channel=channel,
    )

    async def generate() -> AsyncGenerator[str, None]:
        full_response = ""
        new_pending_action = None

        try:
            async for event in agent.astream_events(state, version="v2"):
                kind = event.get("event", "")

                # Token-level streaming from LLM
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        full_response += chunk.content
                        yield f"data: {json.dumps({'token': chunk.content}, ensure_ascii=False)}\n\n"

                # Tool call starting
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event.get("data", {}).get("input", {})
                    call_id = event.get("run_id", "")
                    yield f"event: tool_call\ndata: {json.dumps({'tool': tool_name, 'args': tool_input, 'call_id': call_id}, ensure_ascii=False)}\n\n"

                # Tool call finished — send result for thinking chain display
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "unknown")
                    tool_output = event.get("data", {}).get("output", "")
                    call_id = event.get("run_id", "")
                    # ToolMessage output — extract string content
                    if hasattr(tool_output, "content"):
                        tool_output = tool_output.content
                    yield f"event: tool_result\ndata: {json.dumps({'tool': tool_name, 'result': str(tool_output), 'call_id': call_id}, ensure_ascii=False)}\n\n"

                # Track pending_action changes from tool_node or command_node
                elif kind == "on_chain_end":
                    node_name = event.get("name", "")
                    if node_name in ("tool", "tools", "command"):
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict) and "pending_action" in output:
                            new_pending_action = output["pending_action"]

            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'traceback': tb[-300:]}, ensure_ascii=False)}\n\n"

        if full_response:
            # Strip intermediate tool messages, keep only user + final AI reply
            memory._messages = old_messages + [
                human_msg,
                AIMessage(content=full_response),
            ]
            session_mgr.record_message(req.message, full_response, channel)

        # Save pending_action to session for next invocation
        session.pending_action = new_pending_action

    return StreamingResponse(generate(), media_type="text/event-stream")


# --- Session management endpoints ---

@app.get("/sessions")
def list_sessions(channel: str = "default"):
    session_mgr = get_session_manager()
    sessions = session_mgr.list_sessions()
    active_session = session_mgr.active_session(channel)
    active_id = active_session.session_id
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
def activate_session(session_id: str, channel: str = "default"):
    session_mgr = get_session_manager()
    result = session_mgr.switch(session_id, channel)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"ok": True, "active_session": result.session_id, "name": result.name}


class CreateSessionRequest(BaseModel):
    name: str | None = None


@app.post("/sessions")
def create_session(req: CreateSessionRequest):
    session_mgr = get_session_manager()
    session = session_mgr.create(name=req.name)
    return {
        "session_id": session.session_id,
        "name": session.name,
        "created_at": session.created_at,
    }


@app.get("/sessions/{session_id}")
def get_session_detail(session_id: str):
    session_mgr = get_session_manager()
    session = session_mgr.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    messages = session.memory.get_history()
    compressor = session.compressor
    return {
        "session_id": session.session_id,
        "name": session.name,
        "messages": [
            {"type": m.type, "content": m.content if hasattr(m, "content") else ""}
            for m in messages
        ],
        "summary": compressor.summary,
        "token_stats": {
            "message_count": len(messages),
            "estimated_tokens": compressor._count_tokens(messages) + compressor._summary_tokens,
            "compression_trigger": compressor.compress_trigger,
        },
    }


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    session_mgr = get_session_manager()
    if not session_mgr.delete(session_id):
        raise HTTPException(status_code=400, detail=f"Cannot delete session: {session_id}")
    return {"ok": True}


# --- Admin API: Config management ---

from dotenv import dotenv_values

@app.get("/api/config")
def get_config():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return {"vars": {}}
    values = dotenv_values(env_path)
    # Mask sensitive values
    masked = {}
    for k, v in values.items():
        if any(s in k.upper() for s in ["KEY", "SECRET", "TOKEN", "PASSWORD"]):
            masked[k] = v[:4] + "****" if len(v) > 4 else "****"
        else:
            masked[k] = v
    return {"vars": masked}


class ConfigUpdate(BaseModel):
    vars: dict[str, str]


@app.post("/api/config")
def update_config(req: ConfigUpdate):
    env_path = Path(__file__).parent.parent / ".env"
    existing = dotenv_values(env_path) if env_path.exists() else {}
    existing.update(req.vars)
    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True}


# --- Admin API: Data management ---

import json as _json


@app.get("/api/data/{data_type}")
def list_data(data_type: str):
    if data_type == "calendar":
        path = CALENDAR_FILE
    elif data_type == "todos":
        path = TODOS_FILE
    else:
        raise HTTPException(400, f"Unknown type: {data_type}")

    if not path.exists():
        return {"items": []}
    return {"items": _json.loads(path.read_text(encoding="utf-8"))}


class DataUpdate(BaseModel):
    data: list | dict


@app.post("/api/data/{data_type}")
def create_data(data_type: str, req: DataUpdate):
    if data_type == "calendar":
        path = CALENDAR_FILE
    elif data_type == "todos":
        path = TODOS_FILE
    else:
        raise HTTPException(400, f"Unknown type: {data_type}")

    existing = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if isinstance(existing, list):
        existing.append(req.data)
    else:
        existing = req.data
    path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.put("/api/data/{data_type}/{item_id}")
def update_data(data_type: str, item_id: str, req: DataUpdate):
    if data_type == "todos":
        path = TODOS_FILE
    else:
        raise HTTPException(400, f"Update not supported for {data_type}")

    items = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    for i, item in enumerate(items):
        if item.get("id") == item_id:
            items[i] = req.data
            break
    path.write_text(_json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.delete("/api/data/{data_type}/{item_id}")
def delete_data(data_type: str, item_id: str):
    if data_type == "todos":
        path = TODOS_FILE
    else:
        raise HTTPException(400, f"Delete not supported for {data_type}")

    items = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    items = [i for i in items if i.get("id") != item_id]
    path.write_text(_json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


# --- Shared message processing (used by HTTP endpoints & in-process channels) ---

_message_lock = threading.Lock()


def process_message(text: str, session_mgr: SessionManager, channel: str = "default") -> tuple[str, list[dict]]:
    """统一消息处理入口。全局锁保证同一时间只处理一条消息。"""
    with _message_lock:
        return _process_message_impl(text, session_mgr, channel)


def _process_message_impl(text: str, session_mgr: SessionManager, channel: str = "default") -> tuple[str, list[dict]]:
    """统一消息处理入口。

    系统命令由 Agent Graph 的 command_node 拦截，不经过 LLM，不残留记忆。
    """
    from langchain_core.messages import HumanMessage, AIMessage
    from src.agent.graph import get_agent

    session = session_mgr.active_session(channel)
    memory = session.memory
    agent = get_agent()

    # Save pre-invoke state for rollback on error
    previous_messages = list(memory._messages)
    state_messages = previous_messages + [HumanMessage(content=text)]

    state = AgentState(
        messages=state_messages,
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=session.pending_action,
        channel=channel,
    )

    try:
        result = agent.invoke(state)
        response_text = _extract_response(result)
        tool_calls = _extract_tool_calls(result)
    except Exception as e:
        # Roll back memory and return error
        memory._messages = previous_messages
        import logging
        logging.getLogger("polaris.agent").error(f"Agent 调用失败: {e}", exc_info=True)
        return (f"抱歉，处理请求时出错：{e}", [])

    # Save pending_action from result
    session.pending_action = result.get("pending_action")

    if result.get("final_response"):
        return (response_text, tool_calls)

    # Persist only user msg + final AI reply. Strip intermediate tool messages.
    memory._messages = previous_messages + [
        HumanMessage(content=text),
        AIMessage(content=response_text),
    ]
    session_mgr.record_message(text, response_text, channel)

    return (response_text, tool_calls)


# --- Helpers ---

def _extract_response(result: dict) -> str:
    """Extract the final text response from agent result."""
    response = result.get("final_response", "")
    if response:
        return response
    messages = result.get("messages", [])
    for m in reversed(messages):
        if (hasattr(m, "content") and m.content
            and m.type == "ai"
            and not (hasattr(m, "tool_calls") and m.tool_calls)):
            return m.content
    return "抱歉，处理出错了。"


def _extract_tool_calls(result: dict) -> list[dict]:
    """Extract tool call summaries from agent result."""
    calls = []
    messages = result.get("messages", [])
    for m in messages:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                if isinstance(tc, dict):
                    calls.append({
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args") or {},
                    })
                else:
                    calls.append({
                        "tool": getattr(tc, "name", "unknown"),
                        "args": getattr(tc, "args", {}) or {},
                    })
    return calls


# --- Admin frontend catch-all (must be LAST) ---
from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def serve_admin(full_path: str):
    """Serve admin frontend — index.html for SPA routes, static files for assets."""
    if not ADMIN_DIR.exists():
        raise HTTPException(404, "Admin frontend not built. Run: cd admin && npm run build")
    file_path = ADMIN_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(ADMIN_DIR / "index.html")
