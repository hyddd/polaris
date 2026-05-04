"""Per-session locks for message processing."""
import threading

_message_locks: dict[str, threading.Lock] = {}


def get_session_lock(channel: str, session_id: str) -> threading.Lock:
    """Return (and lazily create) the lock for a given session+channel."""
    key = f"{channel}:{session_id}"
    if key not in _message_locks:
        _message_locks[key] = threading.Lock()
    return _message_locks[key]


def cleanup_session_locks(session_id: str) -> None:
    """Remove all per-session locks for the given session ID (all channels)."""
    keys_to_remove = [k for k in _message_locks if k.endswith(f":{session_id}")]
    for key in keys_to_remove:
        del _message_locks[key]
