from src.tools.persona import PersonaTool
from src.session.manager import get_session_manager


def test_persona_get_empty():
    """Get returns message when no persona is set."""
    tool = PersonaTool()
    # Reset global session manager to clean state
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    session = mgr.active_session()
    session.persona = ""
    result = tool._run(action="get")
    assert "没有人设" in result


def test_persona_set_and_get():
    """Set updates persona, get reads it back."""
    tool = PersonaTool()
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    session = mgr.active_session()

    result = tool._run(action="set", content="你是一个幽默的助手")
    assert "已更新" in result
    assert session.persona == "你是一个幽默的助手"

    result = tool._run(action="get")
    assert "幽默的助手" in result


def test_persona_set_replaces():
    """Set fully replaces existing persona."""
    tool = PersonaTool()
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    session = mgr.active_session()

    tool._run(action="set", content="旧人设")
    tool._run(action="set", content="新人设")
    assert session.persona == "新人设"


def test_persona_set_empty_content():
    """Set with no content returns error."""
    tool = PersonaTool()
    import src.session.manager as sm
    sm._session_manager = None
    get_session_manager()

    result = tool._run(action="set")
    assert "请提供" in result


def test_persona_persistence(tmp_path):
    """Persona survives session serialization round-trip."""
    import src.session.manager as sm
    sm._session_manager = None
    mgr = get_session_manager()
    session = mgr.active_session()
    session.persona = "测试人设"

    # Round-trip through to_dict/from_dict
    from src.session.manager import Session
    data = session.to_dict()
    restored = Session.from_dict(data)
    assert restored.persona == "测试人设"
