"""Admin authentication middleware."""
from fastapi import Request
from fastapi.responses import JSONResponse
from src.core.config import config


async def admin_auth(request: Request, call_next):
    """Require Bearer token for /api/* (ADMIN_TOKEN)."""
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/voice/"):
        token = config.get("server.admin_token", "")
        if token and request.headers.get("authorization", "") != f"Bearer {token}":
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid admin token"})
    return await call_next(request)
