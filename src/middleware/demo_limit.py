"""Demo mode rate limiting middleware."""
import os
import time as _time
import asyncio
from fastapi import Request
from fastapi.responses import JSONResponse


_demo_counters: dict[str, list[float]] = {}
_demo_lock = asyncio.Lock()
_demo_daily = int(os.environ.get("DEMO_DAILY_MESSAGES", "0"))


async def demo_limit(request: Request, call_next):
    """Demo mode: per-IP daily message cap."""
    if not _demo_daily:
        return await call_next(request)
    path = request.url.path
    if path not in ("/api/chat", "/api/chat/stream"):
        return await call_next(request)

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

    now = _time.time()
    async with _demo_lock:
        ts = _demo_counters.setdefault(client_ip, [])
        cutoff = now - 86400
        ts[:] = [t for t in ts if t > cutoff]
        if len(ts) >= _demo_daily:
            return JSONResponse(
                status_code=429,
                content={"detail": f"试用版每日消息上限已达（{_demo_daily}条），请明天再来。"},
                headers={"Retry-After": "86400"},
            )
        ts.append(now)

    return await call_next(request)
