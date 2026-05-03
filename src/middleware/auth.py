"""Admin API authentication middleware."""
from fastapi import Request
from fastapi.responses import JSONResponse
from src.config import config


async def admin_auth_middleware(request: Request, call_next):
    """Require Bearer token for /api/* (ADMIN_TOKEN) and /chat* (CHAT_TOKEN)."""
    path = request.url.path

    # /api/* — admin token
    if path.startswith("/api/"):
        token = config.get("server.admin_token", "")
        if token:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {token}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid admin token"},
                )

    # /chat, /chat/* — chat token
    if path == "/chat" or path.startswith("/chat/"):
        token = config.get("server.chat_token", "")
        if token:
            auth_header = request.headers.get("authorization", "")
            if auth_header != f"Bearer {token}":
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Missing or invalid chat token"},
                )

    return await call_next(request)
