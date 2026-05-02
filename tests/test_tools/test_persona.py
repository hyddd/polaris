from src.tools.persona import PersonaTool
from src.session.manager import get_session_manager


def _reset():
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    # Ensure a clean persona for the active session
    session = mgr.active_session()
    session.persona = {"name": "", "role": "", "traits": [], "style": "", "language": "中文", "extra": ""}
    return mgr


def test_persona_get_empty():
    """Get returns message when no persona is set."""
    tool = PersonaTool()
    _reset()
    result = tool._run(action="get")
    assert "没有人设" in result


def test_persona_set_single_field():
    """Set with a single field updates only that field."""
    tool = PersonaTool()
    mgr = _reset()
    session = mgr.active_session()

    result = tool._run(action="set", name="小星")
    assert "已更新" in result
    assert session.persona["name"] == "小星"
    # Other fields untouched
    assert session.persona["role"] == ""
    assert session.persona["traits"] == []


def test_persona_set_multiple_fields():
    """Set with multiple fields updates all of them."""
    tool = PersonaTool()
    mgr = _reset()
    session = mgr.active_session()

    tool._run(action="set", name="小星", role="私人秘书", traits=["温柔", "专业"])
    assert session.persona["name"] == "小星"
    assert session.persona["role"] == "私人秘书"
    assert session.persona["traits"] == ["温柔", "专业"]


def test_persona_set_preserves_unset():
    """Set with partial fields preserves existing values."""
    tool = PersonaTool()
    mgr = _reset()
    session = mgr.active_session()

    tool._run(action="set", name="小星", role="私人秘书")
    tool._run(action="set", traits=["幽默"])  # only update traits
    assert session.persona["name"] == "小星"  # preserved
    assert session.persona["role"] == "私人秘书"  # preserved
    assert session.persona["traits"] == ["幽默"]  # updated


def test_persona_get_after_set():
    """Get returns formatted text after set."""
    tool = PersonaTool()
    _reset()

    tool._run(action="set", name="小星", role="私人秘书", traits=["温柔"])
    result = tool._run(action="get")
    assert "小星" in result
    assert "私人秘书" in result
    assert "温柔" in result


def test_persona_set_no_fields():
    """Set with no fields returns error."""
    tool = PersonaTool()
    _reset()

    result = tool._run(action="set")
    assert "请提供" in result


def test_persona_persistence():
    """Persona survives session serialization round-trip."""
    mgr = _reset()
    session = mgr.active_session()
    session.persona = {"name": "小星", "role": "秘书", "traits": ["温柔"], "style": "", "language": "中文", "extra": ""}

    from src.session.manager import Session
    data = session.to_dict()
    restored = Session.from_dict(data)
    assert restored.persona["name"] == "小星"
    assert restored.persona["role"] == "秘书"
    assert restored.persona["traits"] == ["温柔"]


def test_persona_backward_compat_string():
    """Old string persona is migrated into extra field."""
    from src.session.manager import Session
    data = {"id": "s1", "name": "test", "created_at": "", "last_active": "",
            "messages": [], "persona": "旧人设文本", "message_count": 0}
    session = Session.from_dict(data)
    assert session.persona["extra"] == "旧人设文本"
    assert session.persona["name"] == ""
