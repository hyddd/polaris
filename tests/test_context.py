"""Tests for src/context.py — contextvars-based context management."""

import pytest
from src.context import set_context, get_context, get_channel, get_session_id, get_user_id, _context


@pytest.fixture(autouse=True)
def _reset_context():
    """Reset ContextVar before each test to avoid cross-test pollution."""
    token = _context.set({})
    yield
    _context.reset(token)


def test_get_context_returns_empty_dict_by_default():
    """Before any set_context call, get_context returns {}."""
    ctx = get_context()
    assert isinstance(ctx, dict)


def test_set_context_stores_all_fields():
    set_context(channel="qq:user123", session_id="sess_abc", user_id="user123")
    ctx = get_context()
    assert ctx["channel"] == "qq:user123"
    assert ctx["session_id"] == "sess_abc"
    assert ctx["user_id"] == "user123"


def test_get_helpers_return_correct_values():
    set_context(channel="feishu:open123", session_id="sess_xyz", user_id="open123")
    assert get_channel() == "feishu:open123"
    assert get_session_id() == "sess_xyz"
    assert get_user_id() == "open123"


def test_get_helpers_return_empty_string_when_unset():
    """In a fresh context (no set_context), helpers return ''."""
    assert get_channel() == ""
    assert get_session_id() == ""
    assert get_user_id() == ""


def test_set_context_overwrites_previous():
    set_context(channel="a", session_id="b", user_id="c")
    set_context(channel="x", session_id="y", user_id="z")
    assert get_channel() == "x"
    assert get_session_id() == "y"
    assert get_user_id() == "z"
