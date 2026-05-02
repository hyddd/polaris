from src.tools.persona import PersonaTool
from src.session.manager import get_session_manager


def _reset():
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    session = mgr.active_session()
    session.persona = {"name": "", "call_user": "", "pronouns": "", "timezone": "Asia/Shanghai", "notes": ""}
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

    result = tool._run(action="set", name="诸葛亮")
    assert "已更新" in result
    assert session.persona["name"] == "诸葛亮"
    assert session.persona["call_user"] == ""
    assert session.persona["notes"] == ""


def test_persona_set_multiple_fields():
    """Set with multiple fields updates all of them."""
    tool = PersonaTool()
    mgr = _reset()
    session = mgr.active_session()

    tool._run(action="set", name="诸葛亮", call_user="主公", notes="足智多谋的军师")
    assert session.persona["name"] == "诸葛亮"
    assert session.persona["call_user"] == "主公"
    assert session.persona["notes"] == "足智多谋的军师"


def test_persona_set_preserves_unset():
    """Set with partial fields preserves existing values."""
    tool = PersonaTool()
    mgr = _reset()
    session = mgr.active_session()

    tool._run(action="set", name="诸葛亮", call_user="主公")
    tool._run(action="set", notes="足智多谋")  # only update notes
    assert session.persona["name"] == "诸葛亮"  # preserved
    assert session.persona["call_user"] == "主公"  # preserved
    assert session.persona["notes"] == "足智多谋"  # updated


def test_persona_get_after_set():
    """Get returns formatted text after set."""
    tool = PersonaTool()
    _reset()

    tool._run(action="set", name="诸葛亮", call_user="主公", notes="军师")
    result = tool._run(action="get")
    assert "诸葛亮" in result
    assert "主公" in result
    assert "军师" in result


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
    session.persona = {"name": "诸葛亮", "call_user": "主公", "pronouns": "他", "timezone": "Asia/Shanghai", "notes": "军师"}

    from src.session.manager import Session
    data = session.to_dict()
    restored = Session.from_dict(data)
    assert restored.persona["name"] == "诸葛亮"
    assert restored.persona["call_user"] == "主公"
    assert restored.persona["notes"] == "军师"


def test_persona_backward_compat_string():
    """Old string persona is migrated into notes field."""
    from src.session.manager import Session
    data = {"id": "s1", "name": "test", "created_at": "", "last_active": "",
            "messages": [], "persona": "旧人设文本", "message_count": 0}
    session = Session.from_dict(data)
    assert session.persona["notes"] == "旧人设文本"
    assert session.persona["name"] == ""


def test_persona_backward_compat_old_dict():
    """Old dict persona with role/traits/style is migrated into notes."""
    from src.session.manager import Session
    data = {"id": "s1", "name": "test", "created_at": "", "last_active": "",
            "messages": [], "message_count": 0,
            "persona": {"name": "小星", "role": "秘书", "traits": ["温柔"], "style": "", "language": "中文", "extra": ""}}
    session = Session.from_dict(data)
    assert session.persona["name"] == "小星"
    assert "秘书" in session.persona["notes"]
    assert "温柔" in session.persona["notes"]
