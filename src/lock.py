"""Per-session locks for message processing."""
import threading

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
