"""personal ↔ team 的 HTTP 链路（不需要 MySQL）。

team 一侧用真实的 REST 路由 + 领域服务，公共数据用本地文件存储代替 MySQL（MySQL 部分见 test_public_mysql.py）；
personal 一侧用 Remote*Store，通过 TestClient 调 team 的接口。两边在同一个进程里，配置按 personal（连着 team）。
"""
import time
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.db import PUBLIC, PRIVATE, RemoteClient, RemoteError
from src.core.db.public_store import NoPrivate

from .conftest import FakeChroma, set_mode


class _Scheduler:
    def __init__(self):
        self.jobs = {}

    def add_date_job(self, job_id, name, run_date, handler_type, handler_kwargs):
        self.jobs[job_id] = ("date", run_date)

    def add_cron_job(self, job_id, name, trigger_kwargs, handler_type, handler_kwargs):
        self.jobs[job_id] = ("cron", trigger_kwargs)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)
        return True


def _team_app() -> FastAPI:
    from src.server.routes import data, reminders, notes, knowledge, status
    app = FastAPI()
    for m in (data, reminders, notes, knowledge, status):
        app.include_router(m.router)
    return app


@pytest.fixture
def team(tmp_path, monkeypatch, personal_linked, session_mgr):
    """team 服务：真实路由 + 领域服务（全局单例），公共数据存在 tmp_path/team 下的文件里。"""
    import src.domains.reminder.domain as rd
    import src.domains.rag.domain as rag_mod
    from src.domains.todos import set_todo_domain
    from src.domains.todos.domain import TodoDomain
    from src.domains.todos.public_store import ScopedTodoStore
    from src.domains.todos.store import TodoStore
    from src.domains.calendar.domain import CalendarDomain, set_calendar_domain
    from src.domains.calendar.public_store import ScopedCalendarStore
    from src.domains.calendar.store import CalendarStore
    from src.domains.reminder.domain import ReminderDomain
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.public_store import ScopedReminderStore
    from src.domains.reminder.store import ReminderStore
    from src.domains.notes import set_notes_domain
    from src.domains.notes.domain import NotesDomain
    from src.domains.notes.public_store import ScopedNoteStore
    from src.domains.notes.store import NoteStore
    from src.domains.rag.domain import RAGDomain
    from src.domains.rag.public_store import JsonDocMeta

    d = tmp_path / "team"
    scheduler = _Scheduler()
    monkeypatch.setattr("src.domains.scheduler.get_scheduler_domain", lambda: scheduler)

    set_todo_domain(TodoDomain(ScopedTodoStore(NoPrivate(), TodoStore(str(d / "todos.json")))))
    set_calendar_domain(CalendarDomain(ScopedCalendarStore(NoPrivate(), CalendarStore(str(d / "cal.json")))))
    rstore = ScopedReminderStore(NoPrivate(), ReminderStore(str(d / "rem.json")))
    monkeypatch.setattr(rd, "_domain", ReminderDomain(rstore, ReminderHandler([], store=rstore)))

    class TeamDocs(JsonDocMeta):
        scope = PUBLIC
    chroma = FakeChroma()
    rag = RAGDomain(chroma, doc_meta=TeamDocs(d / "docs.json"))
    monkeypatch.setattr(rag_mod, "_domain", rag)
    notes = NotesDomain(ScopedNoteStore(NoPrivate(), NoteStore(str(d / "notes"), str(d / "notes/archive"))),
                        persist_dir="x", local_scope=PUBLIC)
    monkeypatch.setattr(NotesDomain, "_search_local",
                        lambda self, kw: [r for r in rag.search(kw)] if self is notes else [])
    set_notes_domain(notes)

    client = RemoteClient("http://team.test")
    client._http = TestClient(_team_app(), base_url="http://team.test")
    # /api/instance 回报 team：team 一侧按 team 模式自报家门
    monkeypatch.setattr("src.core.db.instance_info", lambda: {"mode": "team", "name": "测试团队"})
    yield {"client": client, "chroma": chroma, "scheduler": scheduler, "dir": d}
    set_todo_domain(None)
    set_calendar_domain(None)
    set_notes_domain(None)


def _getter(team):
    return lambda: team["client"]


# ---------------------------------------------------------------------------
# 连接校验
# ---------------------------------------------------------------------------

def _mock_client(handler) -> RemoteClient:
    return RemoteClient("http://team.test", transport=httpx.MockTransport(handler))


def test_remote_refuses_non_team_service():
    """remote.url 误指向另一个 personal 服务：拒绝，避免读到别人的私人数据。"""
    c = _mock_client(lambda req: httpx.Response(200, json={"mode": "personal", "name": "张三"}))
    with pytest.raises(RemoteError, match="不是团队服务"):
        c.get("/api/data/todos")


def test_remote_maps_errors():
    def handler(req):
        if req.url.path == "/api/instance":
            return httpx.Response(200, json={"mode": "team"})
        if req.url.path == "/api/missing":
            return httpx.Response(404, json={"detail": "不存在"})
        if req.url.path == "/api/html":
            return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})
        raise httpx.ConnectError("refused")
    c = _mock_client(handler)
    with pytest.raises(RemoteError) as e:
        c.get("/api/missing")
    assert e.value.status == 404 and "不存在" in str(e.value)
    with pytest.raises(RemoteError, match="不是 JSON"):
        c.get("/api/html")
    with pytest.raises(RemoteError, match="连不上团队服务"):
        c.get("/api/down")
    assert c.team_info is None            # 连接失败后下次重新确认对方身份


def test_instance_endpoint_reports_mode(monkeypatch):
    from src.server.routes import status
    app = FastAPI()
    app.include_router(status.router)
    set_mode(monkeypatch, "team", db_host="db.test")
    info = TestClient(app).get("/api/instance").json()
    assert (info["mode"], info["name"], info["private"]) == ("team", "测试team", False)


# ---------------------------------------------------------------------------
# 待办 / 日程
# ---------------------------------------------------------------------------

def test_todos_public_via_team_private_local(team, tmp_path):
    from src.domains.todos.domain import TodoDomain
    from src.domains.todos.public_store import RemoteTodoStore, ScopedTodoStore
    from src.domains.todos.store import TodoStore
    from src.domains.todos import get_todo_domain

    me = TodoDomain(ScopedTodoStore(TodoStore(str(tmp_path / "me.json")), RemoteTodoStore(_getter(team))))
    pub = me.create_todo(title="团队周报")                         # 默认 public → 存到 team
    pri = me.create_todo(title="买咖啡", scope="private")
    assert (pub.scope, pri.scope) == (PUBLIC, PRIVATE)
    assert [t.title for t in get_todo_domain().list_todos("all")] == ["团队周报"]     # team 只看到公共的
    assert "团队周报" not in (tmp_path / "me.json").read_text()

    assert {t.title: t.scope for t in me.list_todos("all")} == {"买咖啡": PRIVATE, "团队周报": PUBLIC}
    assert me.update_todo(pub.id, {"priority": "high"}).priority == "high"
    assert me.mark_done(pub.id).status == "done"
    assert get_todo_domain().get_todo(pub.id).status == "done"
    assert me.delete_todo(pub.id) and get_todo_domain().get_todo(pub.id) is None
    assert me.delete_todo("todo-nope") is False


def test_calendar_public_via_team(team, tmp_path):
    from src.domains.calendar.domain import CalendarDomain, get_calendar_domain
    from src.domains.calendar.public_store import RemoteCalendarStore, ScopedCalendarStore
    from src.domains.calendar.store import CalendarStore

    me = CalendarDomain(ScopedCalendarStore(CalendarStore(str(tmp_path / "cal.json")), RemoteCalendarStore(_getter(team))))
    a = me.create_event(date="2026-11-21", title="团队评审", time="15:30", attendees=["张三"])
    me.create_event(date="2026-11-21", title="看牙", time="09:00", scope="private")
    assert get_calendar_domain().get_event(a.id).title == "团队评审"
    assert [(e.title, e.scope) for e in me.list_events("2026-11-21")] == [("看牙", PRIVATE), ("团队评审", PUBLIC)]

    moved = me.update_event(a.id, {"time": "16:00"}, date="2026-11-22")
    assert (moved.date, moved.time, moved.scope) == ("2026-11-22", "16:00", PUBLIC)
    assert me.delete_event(a.id) and get_calendar_domain().get_event(a.id) is None


def test_team_down_shows_private_only_with_reason(tmp_path, personal_linked):
    from src.domains.todos.domain import TodoDomain
    from src.domains.todos.public_store import RemoteTodoStore, ScopedTodoStore
    from src.domains.todos.store import TodoStore
    from src.tools.todos.tool import TodoTool
    from src.domains.todos import set_todo_domain

    down = _mock_client(lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    me = TodoDomain(ScopedTodoStore(TodoStore(str(tmp_path / "me.json")), RemoteTodoStore(lambda: down)))
    me.create_todo(title="本机的", scope="private")
    assert [t.title for t in me.list_todos("all")] == ["本机的"]
    assert "连不上团队服务" in me.public_error
    set_todo_domain(me)
    try:
        out = TodoTool()._run(action="create", title="公共的", scope="public")
    finally:
        set_todo_domain(None)
    assert out.startswith("操作失败") and "连不上团队服务" in out


def test_team_rejects_private_over_http(team, monkeypatch):
    set_mode(monkeypatch, "team", db_host="db.test")
    r = team["client"]._http.post("/api/data/todos", json={"data": {"title": "x", "scope": "private"}})
    assert r.status_code == 400 and "只保存公共数据" in r.json()["detail"]


# ---------------------------------------------------------------------------
# 提醒
# ---------------------------------------------------------------------------

def _personal_reminders(team, tmp_path):
    from src.domains.reminder.domain import ReminderDomain
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.public_store import RemoteReminderStore, ScopedReminderStore
    from src.domains.reminder.store import ReminderStore
    store = ScopedReminderStore(ReminderStore(str(tmp_path / "me-rem.json")), RemoteReminderStore(_getter(team)))
    return ReminderDomain(store, ReminderHandler([], store=store)), store


def test_public_reminder_via_team_sync_pause_trigger(team, tmp_path, session_mgr):
    from src.domains.reminder import get_reminder_domain
    from src.domains.reminder.models import ReminderStatus
    me, store = _personal_reminders(team, tmp_path)
    jobs = team["scheduler"].jobs
    when = datetime.now() + timedelta(hours=2)

    r = me.create(title="周会", trigger_time=when)
    assert r.scope == PUBLIC and get_reminder_domain().get(r.id).title == "周会"
    assert me.sync_public() == 0                         # 本机创建时已调度，签名一致不重复

    get_reminder_domain().update(r.id, trigger_time=when + timedelta(minutes=30))   # 别人在 team 上改了时间
    assert me.sync_public() == 1

    assert me.pause(r.id).status == ReminderStatus.PAUSED
    assert get_reminder_domain().get(r.id).status == ReminderStatus.PAUSED
    assert me.resume(r.id).status == ReminderStatus.ACTIVE

    me.trigger(r.id)                                      # 到点：推给本机用户，并把共享状态标成已送达
    texts = [m.content for m in session_mgr.active_session("admin").memory.get_messages()]
    assert "⏰ 提醒：周会" in texts
    assert get_reminder_domain().get(r.id).status == ReminderStatus.CANCELLED

    me.create(title="私事", trigger_time=when, scope="private")
    assert {x.title: x.scope for x in me.list_all()} == {"周会": PUBLIC, "私事": PRIVATE}
    assert me.delete(r.id) and get_reminder_domain().get(r.id) is None
    assert f"reminder:{r.id}" not in jobs


# ---------------------------------------------------------------------------
# 笔记 / 知识库
# ---------------------------------------------------------------------------

def _wait(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_notes_and_knowledge_via_team(team, tmp_path, monkeypatch):
    from src.domains.notes import get_notes_domain
    from src.domains.notes.domain import NotesDomain
    from src.domains.notes.public_store import RemoteNoteStore, ScopedNoteStore
    from src.domains.notes.store import NoteStore
    from src.domains.rag.domain import RAGDomain
    from src.domains.rag.public_store import JsonDocMeta, RemoteKnowledge

    me = NotesDomain(ScopedNoteStore(NoteStore(str(tmp_path / "notes"), str(tmp_path / "notes/archive")),
                                     RemoteNoteStore(_getter(team))), persist_dir="")
    pub = me.create_note("部署手册", "MySQL 主从切换步骤")
    pri = me.create_note("日记", "今天很开心", scope="private")
    assert (pub.scope, pri.scope) == (PUBLIC, PRIVATE)
    assert get_notes_domain().get_note(pub.filename).title == "部署手册"
    assert not (tmp_path / "notes" / pub.filename).exists() and (tmp_path / "notes" / pri.filename).exists()
    assert {n.title: n.scope for n in me.list_notes()} == {"部署手册": PUBLIC, "日记": PRIVATE}

    # team 收到新笔记后在自己的 Chroma 里建向量；personal 检索公共笔记交给 team
    assert _wait(lambda: any(k.startswith("note:") for k in team["chroma"].docs))
    hits = me.search("MySQL 主从")
    assert any(h.scope == PUBLIC and h.title == "部署手册" for h in hits)

    assert me.update_note(pub.filename, content="新内容").content == "新内容"
    assert me.archive_note(pub.filename) and get_notes_domain().get_note(pub.filename) is None

    my_chroma = FakeChroma()
    rag = RAGDomain(my_chroma, doc_meta=JsonDocMeta(tmp_path / "meta.json"), remote=RemoteKnowledge(_getter(team)))
    up_pub = rag.upload_document(file_data="团队规范：代码评审必须两人通过".encode(), filename="规范.txt")
    up_pri = rag.upload_document(file_data="我的清单：周末爬山".encode(), filename="清单.txt", scope="private")
    assert (up_pub["scope"], up_pri["scope"]) == (PUBLIC, PRIVATE)
    assert all("规范" not in v[0] for v in my_chroma.docs.values())          # 公共文档的向量在 team
    assert {d["filename"]: d["scope"] for d in rag.list_documents()} == {"规范.txt": PUBLIC, "清单.txt": PRIVATE}
    assert {r.scope for r in rag.search("代码评审 爬山")} == {PUBLIC, PRIVATE}
    assert rag.delete_document(up_pub["doc_id"]) and rag.delete_document(up_pri["doc_id"])
    assert rag.list_documents() == [] and not rag.delete_document("doc_nope")


def test_remote_retries_idempotent_request_once_after_reset():
    calls = {"n": 0}

    def handler(req):
        if req.url.path == "/api/instance":
            return httpx.Response(200, json={"mode": "team"})
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return httpx.Response(200, json={"items": []})
    c = _mock_client(handler)
    assert c.get("/api/data/todos") == {"items": []} and calls["n"] == 2
    calls["n"] = 0
    with pytest.raises(RemoteError):            # POST 不重试：可能已经建上了
        c.post("/api/data/todos", {"data": {}})


def test_public_reminder_still_delivered_when_team_down(tmp_path, personal_linked, session_mgr, monkeypatch):
    """触发时团队服务连不上：用最近一次同步到的数据照常推送，不抛异常。"""
    from src.domains.reminder.domain import ReminderDomain
    from src.domains.reminder.handler import ReminderHandler
    from src.domains.reminder.models import Reminder
    from src.domains.reminder.public_store import RemoteReminderStore, ScopedReminderStore
    from src.domains.reminder.store import ReminderStore
    monkeypatch.setattr("src.domains.scheduler.get_scheduler_domain", lambda: _Scheduler())
    down = _mock_client(lambda req: (_ for _ in ()).throw(httpx.ConnectError("refused")))
    store = ScopedReminderStore(ReminderStore(str(tmp_path / "rem.json")), RemoteReminderStore(lambda: down))
    me = ReminderDomain(store, ReminderHandler([], store=store))
    r = Reminder(title="站会", trigger_time=datetime.now() + timedelta(hours=1), scope=PUBLIC,
                 channel="admin", session_id="")
    me._public_cache[r.id] = r
    me.trigger(r.id)
    texts = [m.content for m in session_mgr.active_session("admin").memory.get_messages()]
    assert "⏰ 提醒：站会" in texts
