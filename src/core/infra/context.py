"""Centralized context for channel, session_id, user_id.

Uses Python contextvars for thread-safe, coroutine-safe context propagation.
Set once at the message-processing entry point, read anywhere downstream.
"""

import contextvars

_context: contextvars.ContextVar[dict] = contextvars.ContextVar("polaris_context", default={})


def get_context() -> dict:
    """Get current context (channel, session_id, user_id)."""
    return _context.get({})


def set_context(channel: str = "", session_id: str = "", user_id: str = ""):
    """Set current context."""
    _context.set({"channel": channel, "session_id": session_id, "user_id": user_id})


def get_channel() -> str:
    return get_context().get("channel", "")


def get_session_id() -> str:
    return get_context().get("session_id", "")


def get_user_id() -> str:
    return get_context().get("user_id", "")
