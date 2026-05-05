"""Rate limiting middleware with sliding window."""
import time as _time
import asyncio
from collections import defaultdict as _defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from src.core.config import config


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


_rate_limiter: "SlidingWindowRateLimiter | None" = None


def get_limiter() -> SlidingWindowRateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = SlidingWindowRateLimiter(
            max_requests=config.get("server.rate_limit_max_requests", 30),
            window_seconds=config.get("server.rate_limit_window_seconds", 60),
        )
    return _rate_limiter


async def rate_limit(request: Request, call_next):
    """Rate limit middleware for /chat and /chat/stream endpoints."""
    path = request.url.path
    if path not in ("/api/chat", "/api/chat/stream"):
        return await call_next(request)
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    limiter = get_limiter()
    if not await limiter.is_allowed(client_ip):
        retry = limiter.get_retry_after(client_ip)
        return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"}, headers={"Retry-After": str(retry)})
    return await call_next(request)
