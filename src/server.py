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

import logging
import re as _re
import json as _json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import get_session_manager, SessionManager
from src.tools.registry import ToolRegistry
from src.core.context import set_context as _set_ctx
from src.core.config import config

CALENDAR_FILE = config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))
TODOS_FILE = config.resolve_path(config.get("storage.todos_file", "data/todos.json"))

from src.message import process_message
from src.core.lock import get_session_lock, cleanup_session_locks
from src.storage.atomic import _atomic_write


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
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("openai").setLevel(logging.INFO)

_tools_registered = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.core.config import config
    if not config.get("llm.api_key", ""):
        raise RuntimeError(
            "LLM API Key 未配置。请在 data/config.local.yaml 中设置 llm.api_key。"
        )

    global _tools_registered
    if not _tools_registered:
        registry = ToolRegistry.get_instance()
        registry.discover_and_register()
        _tools_registered = True

    # Check embedding config (cloud API, no local model to pre-warm)
    try:
        from src.storage.vector import check_embedding_config
        check_embedding_config()
    except Exception:
        pass

    # Discover and start channel plugins (YAML-config driven)
    from src.channels import discover_and_start, stop_all
    channels = discover_and_start()

    # 启动 cron 框架
    from src.cron import CronScheduler, set_cron_scheduler
    cron = CronScheduler()
    cron.start()
    set_cron_scheduler(cron)

    # 通知各模块：框架已就绪（各 tools/channels 可自初始化）
    from src.core.events import event_bus
    event_bus.publish("app:startup", cron=cron, channels=channels)

    def _daily_tick():
        event_bus.publish("cleanup:cron")

    cron.add_cron_job(_daily_tick, "daily-tick", hour=3, minute=0)
    srv_logger = logging.getLogger("polaris.server")
    srv_logger.info("每日维护事件已注册: 每天 03:00")

    app.state.cron = cron

    yield

    # 停止所有 channel
    stop_all()

    # 清理 cron 调度器
    cron.shutdown()


# --- Middleware ---


async def _admin_auth(request: Request, call_next):
    """Require Bearer token for /api/* (ADMIN_TOKEN) and /chat* (CHAT_TOKEN)."""
    path = request.url.path
    if path.startswith("/api/"):
        token = config.get("server.admin_token", "")
        if token and request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse(401, content={"detail": "Missing or invalid admin token"})
    if path == "/chat" or path.startswith("/chat/"):
        token = config.get("server.chat_token", "")
        if token and request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse(401, content={"detail": "Missing or invalid chat token"})
    return await call_next(request)


# --- Rate limiter ---

import time as _time
import asyncio
from collections import defaultdict as _defaultdict

_rate_limiter: "SlidingWindowRateLimiter | None" = None


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clients: dict[str, list[float]] = _defaultdict(list)
        self._request_count = 0
        self._lock = asyncio.Lock()

    async def _cleanup(self):
        now = _time.time()
        cutoff = now - self.window_seconds
        for client_id in list(self._clients.keys()):
            self._clients[client_id] = [t for t in self._clients[client_id] if t > cutoff]
            if not self._clients[client_id]:
                del self._clients[client_id]

    async def is_allowed(self, client_id: str) -> bool:
        async with self._lock:
            self._request_count += 1
            now = _time.time()
            cutoff = now - self.window_seconds
            if self._request_count % 100 == 0:
                await self._cleanup()
            ts = self._clients[client_id]
            while ts and ts[0] <= cutoff:
                ts.pop(0)
            if len(ts) >= self.max_requests:
                return False
            ts.append(now)
            return True

    def get_retry_after(self, client_id: str) -> int:
        ts = self._clients.get(client_id, [])
        if not ts:
            return 0
        return max(1, int(self.window_seconds - (_time.time() - ts[0])))


def _get_limiter() -> SlidingWindowRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SlidingWindowRateLimiter(
            max_requests=config.get("server.rate_limit_max_requests", 30),
            window_seconds=config.get("server.rate_limit_window_seconds", 60),
        )
    return _rate_limiter


async def _rate_limit(request: Request, call_next):
    path = request.url.path
    if path not in ("/chat", "/chat/stream"):
        return await call_next(request)
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    limiter = _get_limiter()
    if not await limiter.is_allowed(client_ip):
        retry = limiter.get_retry_after(client_ip)
        return JSONResponse(429, content={"detail": "请求过于频繁，请稍后再试"}, headers={"Retry-After": str(retry)})
    return await call_next(request)


app = FastAPI(title="Polaris Agent Server", lifespan=lifespan)
app.middleware("http")(_admin_auth)
app.middleware("http")(_rate_limit)


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
async def chat(req: ChatRequest):
    session_mgr = get_session_manager()
    channel = req.channel or "default"
    session = _get_active_session(req.session_id, session_mgr, channel)

    # 重试逻辑
    if req.retry_message_id:
        original_content = _retry_message(session.session_id, req.retry_message_id, session_mgr, channel)
        response_text, tool_calls = await process_message(original_content, session_mgr, channel)
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 编辑逻辑
    if req.edit_message_id and req.edit_content:
        new_content = _edit_message(session.session_id, req.edit_message_id, req.edit_content, session_mgr, channel)
        response_text, tool_calls = await process_message(new_content, session_mgr, channel)
        return ChatResponse(
            session_id=session.session_id,
            response=response_text,
            tool_calls=tool_calls,
        )

    # 正常聊天
    response_text, tool_calls = await process_message(req.message, session_mgr, channel)
    return ChatResponse(
        session_id=session.session_id,
        response=response_text,
        tool_calls=tool_calls,
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
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
        response_text, _ = await process_message(message_content, session_mgr, channel)

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
    session_lock = get_session_lock(channel, session.session_id)

    async def generate() -> AsyncGenerator[str, None]:
        full_response = ""
        new_pending_action = None

        # Non-blocking try_lock: if another request is already processing
        # for this session, return an error instead of blocking the SSE stream.
        if session_lock.locked():
            yield f"event: error\ndata: {json.dumps({'error': '该会话正在处理中，请稍后再试'}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'session_id': session.session_id}, ensure_ascii=False)}\n\n"
            return

        await session_lock.acquire()
        try:
            # 在锁内设置 context，防止并发覆盖
            user_id = channel.split(":", 1)[-1] if ":" in channel else ""
            _set_ctx(channel=channel, session_id=session.session_id, user_id=user_id)
            async for event in agent.astream_events(state, version="v2"):
                kind = event.get("event", "")

                # 客户端断连时主动停止，避免锁一直不释放
                if await request.is_disconnected():
                    break

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
    try:
        session = session_mgr.create(name=req.name)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
    cleanup_session_locks(session_id)
    return {"ok": True}


# --- Admin API: Config management ---

_SENSITIVE_KEY_PATTERN = _re.compile(r"KEY|SECRET|TOKEN|PASSWORD", _re.IGNORECASE)


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _mask_value(key: str, value: str) -> str:
    if _is_sensitive_key(key):
        return "****"
    return str(value)


@app.get("/api/config")
def get_config():
    from src.core.config import config
    cfg = config.as_dict()
    lines = []
    _flatten_config(cfg, "", lines)
    masked = {}
    for key, value in lines:
        masked[key] = _mask_value(key, value)
    return {"vars": masked}


def _flatten_config(d: dict, prefix: str, out: list):
    """递归展平 YAML 配置树为 key=value 列表。"""
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten_config(v, full_key, out)
        else:
            out.append((full_key, v))


class ConfigUpdate(BaseModel):
    vars: dict[str, str]


@app.post("/api/config")
def update_config(req: ConfigUpdate):
    from src.core.config import config

    for key, value in req.vars.items():
        config.set(key, value)
    config.reload()
    return {"ok": True}


# --- Admin API: Data management ---

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


# --- Admin frontend catch-all (must be LAST) ---

@app.get("/{full_path:path}")
async def serve_admin(full_path: str):
    """Serve admin frontend — index.html for SPA routes, static files for assets."""
    if not ADMIN_DIR.exists():
        raise HTTPException(404, "Admin frontend not built. Run: cd admin && npm run build")
    file_path = ADMIN_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(ADMIN_DIR / "index.html")
