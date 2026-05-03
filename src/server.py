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

import os
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import get_session_manager, SessionManager
from src.tools.registry import ToolRegistry
from src.context import set_context as _set_ctx


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    channel: str = ""
    retry_message_id: str | None = None  # 重试指定消息
    edit_message_id: str | None = None   # 编辑指定消息
    edit_content: str | None = None      # 编辑后的内容


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
    from src.config import LLM_API_KEY
    if not LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY 未配置。请在环境变量或 .env 文件中设置 OPENAI_API_KEY。"
        )

    global _tools_registered
    if not _tools_registered:
        registry = ToolRegistry.get_instance()
        registry.discover_and_register()
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

    # 初始化提醒模块
    from src.reminders.store import ReminderStore
    from src.reminders.scheduler import ReminderScheduler
    from src.reminders.handlers import ReminderHandler
    from src.reminders import set_scheduler
    from src.config import REMINDERS_FILE

    reminder_store = ReminderStore(str(REMINDERS_FILE))
    reminder_handler = ReminderHandler(mgr)
    reminder_scheduler = ReminderScheduler(reminder_store, reminder_handler)
    reminder_scheduler.start()
    set_scheduler(reminder_scheduler)

    app.state.reminder_scheduler = reminder_scheduler
    app.state.reminder_store = reminder_store

    yield

    # 清理提醒调度器
    reminder_scheduler.shutdown()


app = FastAPI(title="Polaris Agent Server", lifespan=lifespan)


# --- Admin API auth middleware ---

@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    """Require Bearer token for /api/* (ADMIN_TOKEN) and /chat* (CHAT_TOKEN)."""
    import src.config as _cfg
    path = request.url.path

    # /api/* — admin token
    if path.startswith("/api/"):
        token = _cfg.ADMIN_TOKEN
        if token:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {token}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid admin token"},
                )

    # /chat, /chat/* — chat token
    if path == "/chat" or path.startswith("/chat/"):
        token = _cfg.CHAT_TOKEN
        if token:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {token}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid chat token"},
                )

    return await call_next(request)


# Admin frontend static files
ADMIN_DIR = Path(__file__).parent.parent / "admin" / "dist"


def _get_active_session(session_id: str | None, session_mgr: SessionManager, channel: str = "default"):
    """Resolve session: use given ID, switch if needed, or use active."""
    if session_id:
        result = session_mgr.switch(session_id, channel)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session_mgr.active_session(channel)


def _retry_message(session_id: str, message_id: str, session_mgr: SessionManager, channel: str = "default"):
    """重试指定消息：找到原消息，重新执行"""
    session = session_mgr.get(session_id) if session_id else session_mgr.active_session(channel)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    original = session.get_message(message_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"消息不存在: {message_id}")

    # 获取原消息内容
    content = original.content if hasattr(original, 'content') else str(original)
    return content


def _edit_message(session_id: str, message_id: str, new_content: str, session_mgr: SessionManager, channel: str = "default"):
    """编辑消息并返回新内容"""
    session = session_mgr.get(session_id) if session_id else session_mgr.active_session(channel)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # 更新消息内容
    if not session.update_message(message_id, new_content):
        raise HTTPException(status_code=404, detail=f"消息不存在: {message_id}")

    return new_content


# --- Chat endpoints (for external channels: admin UI, remote bots, etc.) ---
# In-process channels (Feishu, QQ) call agent directly, not via HTTP.

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_mgr = get_session_manager()
    channel = req.channel or "default"
    session = _get_active_session(req.session_id, session_mgr, channel)

    # 重试逻辑
    if req.retry_message_id:
        original_content = _retry_message(session.session_id, req.retry_message_id, session_mgr, channel)
        response_text, tool_calls = process_message(original_content, session_mgr, channel)
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 编辑逻辑
    if req.edit_message_id and req.edit_content:
        new_content = _edit_message(session.session_id, req.edit_message_id, req.edit_content, session_mgr, channel)
        response_text, tool_calls = process_message(new_content, session_mgr, channel)
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 正常聊天
    response_text, tool_calls = process_message(req.message, session_mgr, channel)
    return ChatResponse(
        session_id=session.session_id,
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

    # Determine the message content (retry/edit/normal)
    message_content = req.message

    # 重试逻辑
    if req.retry_message_id:
        message_content = _retry_message(session.session_id, req.retry_message_id, session_mgr, channel)

    # 编辑逻辑
    elif req.edit_message_id and req.edit_content:
        message_content = _edit_message(session.session_id, req.edit_message_id, req.edit_content, session_mgr, channel)

    # System commands: wrap in SSE
    if message_content.strip().startswith("/"):
        response_text, _ = process_message(message_content, session_mgr, channel)

        async def cmd_gen() -> AsyncGenerator[str, None]:
            import json as _j
            yield f"event: message\ndata: {_j.dumps({'content': response_text}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {_j.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
        return StreamingResponse(cmd_gen(), media_type="text/event-stream")

    # Normal message: streaming agent pipeline
    agent = get_agent()
    memory = session.memory
    old_messages = memory.get_messages()

    # Create HumanMessage with ID for retry/edit support
    human_msg = HumanMessage(content=message_content)
    memory.add_message(human_msg)
    human_msg_id = memory.get_message_id(human_msg)

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

    # Acquire per-session lock before streaming starts
    session_lock = _get_session_lock(channel, session.session_id)

    async def generate() -> AsyncGenerator[str, None]:
        full_response = ""
        new_pending_action = None

        # Non-blocking try_lock: if another request is already processing
        # for this session, return an error instead of blocking the SSE stream.
        if not session_lock.acquire(blocking=False):
            yield f"event: error\ndata: {json.dumps({'error': '该会话正在处理中，请稍后再试'}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
            return

        try:
            # 在锁内设置 context，防止并发覆盖
            user_id = channel.split(":", 1)[-1] if ":" in channel else ""
            _set_ctx(channel=channel, session_id=session.session_id, user_id=user_id)
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

        finally:
            session_lock.release()

        if full_response:
            # Strip intermediate tool messages, keep only user + final AI reply
            memory.set_messages(old_messages + [
                human_msg,
                AIMessage(content=full_response),
            ])
            session_mgr.record_message(message_content, full_response, channel)

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
            {
                "id": session.memory.get_message_id(m) or f"msg_{i}",
                "type": m.type,
                "content": m.content if hasattr(m, "content") else "",
            }
            for i, m in enumerate(messages)
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
    _cleanup_session_locks(session_id)
    return {"ok": True}


# --- Admin API: Config management ---

import re as _re
import tempfile
from dotenv import dotenv_values


def _atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomic file write with backup.

    Strategy:
      1. Write new content to a temp file in the same directory.
      2. If original exists, create .bak backup.
      3. os.replace() temp -> original (atomic on POSIX).
      4. On any failure, attempt to restore from backup.

    Raises the original exception after restore attempt.
    """
    path = Path(path)
    dir_fd = path.parent
    backup = path.with_suffix(path.suffix + ".bak")
    tmp_fd = None
    tmp_path = None

    try:
        # Step 1: write to temp file in same directory (same filesystem for rename)
        tmp_fd = tempfile.NamedTemporaryFile(
            mode="w", encoding=encoding, dir=dir_fd,
            suffix=".tmp", delete=False,
        )
        tmp_path = Path(tmp_fd.name)
        tmp_fd.write(content)
        tmp_fd.flush()
        os.fsync(tmp_fd.fileno())  # ensure data hits disk
        tmp_fd.close()
        tmp_fd = None

        # Step 2: backup existing file
        if path.exists():
            import shutil
            shutil.copy2(path, backup)

        # Step 3: atomic rename
        os.replace(str(tmp_path), str(path))
        tmp_path = None  # rename succeeded, don't clean up

    except Exception:
        # Attempt restore from backup if original was overwritten or corrupted
        if backup.exists() and (not path.exists() or path.read_text(encoding=encoding) != content):
            try:
                import shutil
                shutil.copy2(backup, path)
            except Exception:
                pass  # best-effort restore
        raise
    finally:
        # Clean up temp file if rename didn't happen
        if tmp_fd is not None:
            tmp_fd.close()
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

# Whitelist of config keys that can be written via the admin API.
# Unknown keys are rejected to prevent environment variable injection.
ALLOWED_CONFIG_KEYS: set[str] = {
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "ADMIN_TOKEN",
    "CHAT_TOKEN",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "DATA_DIR",
    "CHROMA_PERSIST_DIR",
    "POLARIS_MODEL_MAX_CONTEXT",
    "POLARIS_COMPRESSION_THRESHOLD",
    "GOOGLE_CALENDAR_CREDENTIALS_PATH",
    "GOOGLE_CALENDAR_ID",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
}

_SENSITIVE_KEY_PATTERN = _re.compile(r"KEY|SECRET|TOKEN|PASSWORD", _re.IGNORECASE)


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _mask_value(key: str, value: str) -> str:
    """Fully mask sensitive values — leak no characters."""
    if _is_sensitive_key(key):
        return "****"
    return value


@app.get("/api/config")
def get_config():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return {"vars": {}}
    values = dotenv_values(env_path)
    masked = {k: _mask_value(k, v) for k, v in values.items()}
    return {"vars": masked}


class ConfigUpdate(BaseModel):
    vars: dict[str, str]


@app.post("/api/config")
def update_config(req: ConfigUpdate):
    unknown_keys = set(req.vars.keys()) - ALLOWED_CONFIG_KEYS
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Rejected unknown config keys: {', '.join(sorted(unknown_keys))}",
        )
    env_path = Path(__file__).parent.parent / ".env"
    existing = dotenv_values(env_path) if env_path.exists() else {}
    existing.update(req.vars)
    lines = [f"{k}={v}" for k, v in existing.items()]
    _atomic_write(env_path, "\n".join(lines) + "\n")
    # Reload config module so changes take effect immediately
    from src.config import reload
    reload()
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
    _atomic_write(path, _json.dumps(existing, ensure_ascii=False, indent=2))
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
    _atomic_write(path, _json.dumps(items, ensure_ascii=False, indent=2))
    return {"ok": True}


@app.delete("/api/data/{data_type}/{item_id}")
def delete_data(data_type: str, item_id: str):
    if data_type == "todos":
        path = TODOS_FILE
    else:
        raise HTTPException(400, f"Delete not supported for {data_type}")

    items = _json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    items = [i for i in items if i.get("id") != item_id]
    _atomic_write(path, _json.dumps(items, ensure_ascii=False, indent=2))
    return {"ok": True}


# --- Shared message processing (used by HTTP endpoints & in-process channels) ---

# Per-session locks: each session/channel pair gets its own lock so independent
# sessions can be processed concurrently.  A separate dict-level lock protects
# creation of new per-session locks.
_message_locks: dict[str, threading.Lock] = {}
_message_locks_guard = threading.Lock()


def _get_session_lock(channel: str, session_id: str) -> threading.Lock:
    """Return (and lazily create) the lock for a given session+channel."""
    key = f"{channel}:{session_id}"
    lock = _message_locks.get(key)
    if lock is None:
        with _message_locks_guard:
            lock = _message_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                _message_locks[key] = lock
    return lock


def _cleanup_session_locks(session_id: str) -> None:
    """Remove all per-session locks for the given session ID (all channels)."""
    with _message_locks_guard:
        keys_to_remove = [k for k in _message_locks if k.endswith(f":{session_id}")]
        for key in keys_to_remove:
            del _message_locks[key]


def process_message(text: str, session_mgr: SessionManager, channel: str = "default") -> tuple[str, list[dict]]:
    """统一消息处理入口。per-session 锁保证同一会话串行处理，不同会话可并发。"""
    session_id = session_mgr.active_session(channel).session_id
    with _get_session_lock(channel, session_id):
        # 在锁内设置 context，防止并发覆盖
        user_id = channel.split(":", 1)[-1] if ":" in channel else ""
        _set_ctx(channel=channel, session_id=session_id, user_id=user_id)
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
    previous_messages = memory.get_messages()

    # Create HumanMessage with ID for retry/edit support
    human_msg = HumanMessage(content=text)
    memory.add_message(human_msg)
    human_msg_id = memory.get_message_id(human_msg)

    state_messages = previous_messages + [human_msg]

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
        memory.set_messages(previous_messages)
        import logging
        logging.getLogger("polaris.agent").error(f"Agent 调用失败: {e}", exc_info=True)
        return (f"抱歉，处理请求时出错：{e}", [])

    # Save pending_action from result
    session.pending_action = result.get("pending_action")

    if result.get("final_response"):
        return (response_text, tool_calls)

    # Persist only user msg + final AI reply. Strip intermediate tool messages.
    # Keep the original human message with its ID
    memory.set_messages(previous_messages + [
        human_msg,
        AIMessage(content=response_text),
    ])
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
