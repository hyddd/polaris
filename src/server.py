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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import config

# --- App lifecycle ---

# Structured logging setup
from src.core.observability import setup_logging
_log_level = getattr(logging, config.get("logging.level", "INFO").upper(), logging.INFO)
_log_format = config.get("logging.format", "text")
setup_logging(level=_log_level, json_mode=(_log_format == "json"))

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
        from src.domains.rag.vector import check_embedding_config
        check_embedding_config()
    except Exception:
        pass

    # Discover and start channel plugins (YAML-config driven)
    from src.core.channel.loader import discover_and_start, stop_all
    channels = discover_and_start()

    # 启动 cron 框架
    from src.cron import CronScheduler, set_cron_scheduler
    cron = CronScheduler()
    cron.start()
    set_cron_scheduler(cron)

    # 确保所有 Domain 模块已导入（注册 app:startup handler）
    import src.domains  # noqa: F401

    # 通知各模块：框架已就绪（各 tools/channels/heartbeat 可自初始化）
    from src.core.infra import event_bus
    event_bus.publish("app:startup", cron=cron, channels=channels)

    app.state.cron = cron

    yield

    # 停止所有 channel
    stop_all()

    # 清理 cron 调度器
    cron.shutdown()


# --- Import middleware and routes ---

from src.core.tools.registry import ToolRegistry

from src.middleware import demo_limit, admin_auth, rate_limit
from src.routes.chat import router as chat_router
from src.routes.sessions import router as sessions_router
from src.routes.config import router as config_router
from src.routes.data import router as data_router
from src.routes.notes import router as notes_router
from src.routes.knowledge import router as knowledge_router
from src.routes.reminders import router as reminders_router
from src.routes.voice import router as voice_router
from src.routes.status import router as status_router

# --- Create app and register middleware ---

app = FastAPI(title="Polaris Agent Server", lifespan=lifespan)
app.middleware("http")(demo_limit)
app.middleware("http")(admin_auth)
app.middleware("http")(rate_limit)

# --- Register route routers ---

app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(config_router)
app.include_router(data_router)
app.include_router(notes_router)
app.include_router(knowledge_router)
app.include_router(reminders_router)
app.include_router(voice_router)
app.include_router(status_router)

# --- Admin frontend catch-all (must be LAST) ---

ADMIN_DIR = Path(__file__).parent.parent / "admin" / "dist"


def _serve_index():
    if not ADMIN_DIR.exists():
        raise HTTPException(404, "Admin frontend not built. Run: cd admin && npm run build")
    return FileResponse(ADMIN_DIR / "index.html")


@app.get("/{full_path:path}")
async def serve_admin(full_path: str):
    """Serve admin frontend — index.html for SPA routes, static files for assets."""
    if not ADMIN_DIR.exists():
        raise HTTPException(404, "Admin frontend not built. Run: cd admin && npm run build")
    file_path = ADMIN_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    return _serve_index()
