"""不需要 MySQL 的部分：服务模式与 scope 解析、RRF 融合、公共数据不可用时的降级、工具标签。"""
import pytest

from src.core.db import PUBLIC, PRIVATE, ScopeError, DatabaseError, resolve_scope, default_scope, instance_info
from src.domains.rag.merge import rrf_merge
from src.domains.todos.models import TodoItem
from src.domains.todos.public_store import ScopedTodoStore
from src.domains.todos.store import TodoStore

from .conftest import set_mode


def test_personal_without_team_is_private_only(personal_alone):
    assert default_scope() == PRIVATE
    assert resolve_scope(None) == PRIVATE
    assert resolve_scope("私有") == PRIVATE
    with pytest.raises(ScopeError, match="没有连接团队服务"):
        resolve_scope("public")
    info = instance_info()
    assert (info["mode"], info["public"], info["private"]) == ("personal", False, True)


def test_personal_with_team_defaults_public(personal_linked, monkeypatch):
    from src.core.config import config
    assert resolve_scope(None) == PUBLIC
    assert resolve_scope("团队") == PUBLIC and resolve_scope("个人") == PRIVATE
    with pytest.raises(ScopeError):
        resolve_scope("everyone")
    monkeypatch.setitem(config._data, "visibility", {"default_scope": "private"})
    assert resolve_scope(None) == PRIVATE
    assert instance_info()["remote"] == "http://team.test"


def test_team_refuses_private_and_needs_database(monkeypatch):
    set_mode(monkeypatch, "team", db_host="db.test")
    assert resolve_scope(None) == PUBLIC
    with pytest.raises(ScopeError, match="只保存公共数据"):
        resolve_scope("private")
    info = instance_info()
    assert (info["mode"], info["mode_label"], info["private"]) == ("team", "团队服务", False)
    set_mode(monkeypatch, "team")                       # 没配数据库
    with pytest.raises(ScopeError, match="没有配置数据库"):
        resolve_scope("public")


def test_unknown_mode_falls_back_to_personal(monkeypatch):
    from src.core.db import instance_mode
    set_mode(monkeypatch, "master")
    assert instance_mode() == "personal"


def test_personal_skips_linked_reminder_for_public_event(monkeypatch):
    """公共日程的关联提醒由 team 服务创建；personal 只给私人日程建。"""
    import src.domains.reminder.domain as rd
    set_mode(monkeypatch, "personal", remote="http://team.test")
    assert rd._handled_by_team("public") and not rd._handled_by_team("private")
    set_mode(monkeypatch, "team", db_host="db.test")
    assert not rd._handled_by_team("public")


def test_rrf_merge_orders_by_rank_not_raw_score():
    a = ["x", "y", "z"]            # 来源 A 的名次
    b = ["y", "w"]                 # 来源 B 的名次；y 两边都靠前
    merged = [item for item, _ in rrf_merge([a, b], key=lambda s: s, top_k=3)]
    assert merged[0] == "y"
    assert set(merged) <= {"x", "y", "z", "w"} and len(merged) == 3


class _DownPublic:
    """模拟公共库连不上。"""
    def __getattr__(self, name):
        def fail(*a, **kw):
            raise DatabaseError("连不上公共库 test")
        return fail


def test_public_down_lists_private_with_reason(tmp_path):
    private = TodoStore(str(tmp_path / "todos.json"))
    private.create_todo({"id": "todo-1", "title": "本机的", "priority": "medium", "status": "pending", "due": ""})
    store = ScopedTodoStore(private, _DownPublic())
    items = store.list_todos("all")
    assert [t.title for t in items] == ["本机的"]
    assert "连不上公共库" in store.public_error
    # 按 ID 操作私有数据不受影响
    assert store.mark_done("todo-1").status == "done"


def test_todo_tool_marks_scope_and_reports_public_down(tmp_path, monkeypatch):
    from src.domains.todos.domain import TodoDomain, set_todo_domain
    from src.tools.todos.tool import TodoTool
    private = TodoStore(str(tmp_path / "todos.json"))
    private.create_todo({"id": "todo-1", "title": "本机的", "priority": "high", "status": "pending", "due": ""})
    set_todo_domain(TodoDomain(ScopedTodoStore(private, _DownPublic())))
    try:
        out = TodoTool()._run(action="list", status="all")
    finally:
        set_todo_domain(None)
    assert "【私人】" in out and "本机的" in out
    assert "团队服务暂时连不上" in out


def test_private_models_round_trip_scope():
    t = TodoItem.from_dict({"id": "a", "title": "t", "priority": "low", "status": "pending", "due": ""})
    assert t.scope == PRIVATE and t.to_dict()["scope"] == PRIVATE


def test_scope_tags_and_system_prompt_rule():
    """展示用【公共】/【私人】；系统提示词要求模型回答时保留；用户说"私人"也能识别。"""
    from src.core.db import scope_tag
    from src.agent.executor import UNIFIED_SYSTEM_PROMPT
    from src.cli.ui.views import _scope
    assert scope_tag("public") == "【公共】" and scope_tag("private") == "【私人】"
    assert _scope({"scope": "public"}) == "【公共】" and _scope({}) == "【私人】"
    assert "【公共】" in UNIFIED_SYSTEM_PROMPT and "【私人】" in UNIFIED_SYSTEM_PROMPT
    assert resolve_scope("私人") == PRIVATE


def test_no_private_placeholder():
    from src.core.db.public_store import NoPrivate
    n = NoPrivate()
    assert n.list_todos("all") == [] and n.search("x") == [] and n.find_by_event_id("e") == []
    assert n.get_todo("x") is None and n.cleanup(3) == 0


def test_schema_uses_plain_table_names_and_db_t():
    """表名不加前缀；建表语句里的表名都经过 db.t()（测试据此换成临时表）。"""
    from src.core.db.mysql import Database
    from src.core.db.schema import ensure_schema, TABLES

    class _Recorder(Database):
        def __init__(self):
            self.sql = []

        def execute(self, sql, args=None):
            self.sql.append(sql)
            return 0

    plain = _Recorder()
    assert plain.t("todos") == "`todos`"
    ensure_schema(plain)
    assert len(plain.sql) == len(TABLES) and all("CREATE TABLE IF NOT EXISTS `" in s for s in plain.sql)

    class _Temp(_Recorder):
        def t(self, name):
            return f"`tmp_{name}`"
    temp = _Temp()
    ensure_schema(temp)
    assert all(f"`tmp_{name}`" in s for name, s in zip(TABLES, temp.sql))
