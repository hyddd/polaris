"""Sliding window rate limiter middleware for FastAPI.

Only applies to /chat and /chat/stream endpoints to prevent abuse
that could lead to excessive LLM API costs and tool execution storms.
"""

import time
import asyncio
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from src.config import config

# Singleton limiter instance (lazily initialized)
_limiter: "SlidingWindowRateLimiter | None" = None


class SlidingWindowRateLimiter:
    """基于滑动窗口的速率限制器（进程内单例，无外部依赖）。"""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clients: dict[str, list[float]] = defaultdict(list)
        self._request_count = 0
        self._lock = asyncio.Lock()

    async def _cleanup(self):
        """清理所有客户端中已超出窗口期的记录，防止内存泄漏。"""
        now = time.time()
        cutoff = now - self.window_seconds
        for client_id in list(self._clients.keys()):
            self._clients[client_id] = [
                t for t in self._clients[client_id] if t > cutoff
            ]
            if not self._clients[client_id]:
                del self._clients[client_id]

    async def is_allowed(self, client_id: str) -> bool:
        """检查客户端是否允许请求。

        在滑动窗口内未超过 max_requests 时返回 True，
        否则返回 False。
        """
        async with self._lock:
            self._request_count += 1
            now = time.time()
            cutoff = now - self.window_seconds

            # 每 100 次请求触发一次全局清理，防止内存泄漏
            if self._request_count % 100 == 0:
                await self._cleanup()

            # 获取该客户端的时间戳列表
            timestamps = self._clients[client_id]

            # 移除窗口之外的时间戳（列表头部是最老的）
            while timestamps and timestamps[0] <= cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.max_requests:
                return False

            timestamps.append(now)
            return True

    def get_retry_after(self, client_id: str) -> int:
        """返回客户端需要等待多少秒后才能再次请求。"""
        timestamps = self._clients.get(client_id, [])
        if not timestamps:
            return 0
        now = time.time()
        oldest = timestamps[0]
        wait = int(self.window_seconds - (now - oldest))
        return max(1, wait)


def get_limiter() -> SlidingWindowRateLimiter:
    """获取或创建全局单例限流器（懒加载）。"""
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowRateLimiter(
            max_requests=config.get("server.rate_limit_max_requests", 30),
            window_seconds=config.get("server.rate_limit_window_seconds", 60),
        )
    return _limiter


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI 中间件：对 /chat 和 /chat/stream 端点进行速率限制。

    使用客户端 IP（优先取 X-Forwarded-For）作为标识，
    超限时返回 429 状态码及 Retry-After 头。
    """
    path = request.url.path

    # 仅对 /chat 和 /chat/stream 限流
    if path not in ("/chat", "/chat/stream"):
        return await call_next(request)

    # 获取客户端 IP
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    limiter = get_limiter()

    if not await limiter.is_allowed(client_ip):
        retry_after = limiter.get_retry_after(client_ip)
        return JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
