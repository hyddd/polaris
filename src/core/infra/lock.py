"""Per-session locks for message processing.

锁只按 session_id 区分：Web、QQ、飞书、CLI 等不同入口操作同一个会话时必须互斥，
否则各自读到旧历史、各自写回，后写的一方会覆盖前一方的整轮对话。

锁本身是 threading.Lock，因为调用方分布在不同线程和事件循环里
（主事件循环、QQ 自有事件循环、飞书每条消息一个线程、APScheduler 线程）。
在 async 代码里只能用 hold_session_lock() 获取，不能阻塞式 acquire：
阻塞会卡住整个事件循环，而持锁方恰恰需要事件循环才能往下执行并释放锁。
"""
import asyncio
import threading
import time
from contextlib import asynccontextmanager

_message_locks: dict[str, threading.Lock] = {}

_POLL_INTERVAL = 0.05


class SessionBusyError(Exception):
    """会话正在被其他请求处理，且在超时时间内没有释放。"""


def get_session_lock(session_id: str) -> threading.Lock:
    """Return (and lazily create) the lock for a given session."""
    # setdefault 在 CPython 下是原子的，多线程同时首次获取也只会建出一把锁
    return _message_locks.setdefault(session_id, threading.Lock())


@asynccontextmanager
async def hold_session_lock(session_id: str, timeout: float | None = None):
    """在 async 代码里获取会话锁：轮询非阻塞 acquire，等待期间让出事件循环。

    timeout=None 表示一直等；超时抛 SessionBusyError。
    等待中被取消时还没拿到锁，不会泄漏。
    """
    lock = get_session_lock(session_id)
    deadline = None if timeout is None else time.monotonic() + timeout
    while not lock.acquire(blocking=False):
        if deadline is not None and time.monotonic() >= deadline:
            raise SessionBusyError(session_id)
        await asyncio.sleep(_POLL_INTERVAL)
    try:
        yield
    finally:
        lock.release()


def cleanup_session_locks(session_id: str) -> None:
    """Remove the lock for the given session ID."""
    _message_locks.pop(session_id, None)
