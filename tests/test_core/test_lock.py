"""Tests for src.core.lock — per-session locking."""

import threading
import time

from src.core import lock as lock_mod
from src.core.lock import get_session_lock, cleanup_session_locks


def test_acquire_and_release():
    """Lock can be acquired and released without error."""
    # 清理全局状态
    lock_mod._message_locks.clear()

    lck = get_session_lock("telegram", "user1")
    assert hasattr(lck, "acquire") and hasattr(lck, "release")

    acquired = lck.acquire(timeout=1)
    assert acquired is True
    lck.release()

    # 同一 key 返回同一个 lock 实例
    assert get_session_lock("telegram", "user1") is lck


def test_concurrent_access():
    """Concurrent threads are mutually excluded by the lock."""
    lock_mod._message_locks.clear()

    lck = get_session_lock("wechat", "sess1")
    entered = []
    barrier = threading.Barrier(2, timeout=3)

    def worker(tag):
        with lck:
            entered.append(f"{tag}_start")
            # 等待另一线程也到达，证明它们没有同时进入
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            entered.append(f"{tag}_end")

    t1 = threading.Thread(target=worker, args=("t1",))
    t2 = threading.Thread(target=worker, args=("t2",))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    # 如果锁工作正常，一个线程的 start/end 不会被另一个线程的 start 打断
    # 即顺序应为 X_start, X_end, Y_start, Y_end（X/Y 可互换）
    assert len(entered) == 4
    assert entered[0].endswith("_start")
    assert entered[1].endswith("_end")
    assert entered[0].split("_")[0] == entered[1].split("_")[0]


def test_cleanup_session_locks():
    lock_mod._message_locks.clear()

    get_session_lock("telegram", "u1")
    get_session_lock("wechat", "u1")
    get_session_lock("telegram", "u2")

    cleanup_session_locks("u1")

    assert "telegram:u1" not in lock_mod._message_locks
    assert "wechat:u1" not in lock_mod._message_locks
    assert "telegram:u2" in lock_mod._message_locks
