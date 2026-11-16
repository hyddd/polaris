"""REST 接口回归：创建返回真实 ID、网页创建的日程/提醒绑定投递会话、按 ID 重命名会话。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.server.routes.data as data_routes
import src.server.routes.reminders as reminder_routes
from src.server.routes import sessions as session_routes
from src.domains.calendar.domain import CalendarDomain
from src.domains.calendar.store import CalendarStore
from src.domains.todos.domain import TodoDomain
from src.domains.todos.store import TodoStore


@pytest.fixture
def client(session_mgr):
    app = FastAPI()
    app.include_router(data_routes.router)
    app.include_router(reminder_routes.router)
    app.include_router(session_routes.router)
    return TestClient(app)


def test_create_todo_returns_item_with_id(client, tmp_path, monkeypatch):
    domain = TodoDomain(TodoStore(str(tmp_path / "todos.json")))
    monkeypatch.setattr(data_routes, "_require_todo_domain", lambda: domain)

    r = client.post("/api/data/todos", json={"data": {"title": "写周报"}})
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["title"] == "写周报" and item["id"]
    assert [t.id for t in domain.list_todos("all")] == [item["id"]]


def test_create_calendar_binds_web_session_and_returns_item(client, session_mgr, tmp_path, monkeypatch):
    """①：网页日历创建的日程，关联提醒要知道投给哪个会话。"""
    domain = CalendarDomain(CalendarStore(str(tmp_path / "calendar.json")))
    monkeypatch.setattr(data_routes, "_require_calendar_domain", lambda: domain)
    published = []
    monkeypatch.setattr("src.domains.calendar.domain.event_bus.publish",
                        lambda name, **kw: published.append((name, kw)))

    r = client.post("/api/data/calendar", json={"data": {"date": "2026-12-01", "title": "评审", "time": "15:00"}})
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["id"].startswith("evt-")

    name, kw = published[0]
    assert name == "calendar:event_created"
    assert kw["channel"] == "admin"
    assert kw["session_id"] == session_mgr.active_session("admin").session_id


def test_create_reminder_binds_web_session(client, session_mgr, monkeypatch):
    captured = {}

    class FakeDomain:
        def create(self, **kw):
            captured.update(kw)

            class R:
                def to_dict(self_inner):
                    return {"id": "rmd-1"}
            return R()

    monkeypatch.setattr(reminder_routes, "_require_reminder_domain", lambda: FakeDomain())
    r = client.post("/api/reminders", json={"title": "喝水", "trigger_time": "2026-12-01T10:00:00"})
    assert r.status_code == 200
    assert captured["channel"] == "admin"
    assert captured["session_id"] == session_mgr.active_session("admin").session_id


def test_rename_renames_the_requested_session_not_active(client, session_mgr):
    """⑨：以前网页走 `/rename` 聊天命令，改的是当前激活会话。"""
    active = session_mgr.active_session("admin")
    other = session_mgr.create(name="旧名字")
    old_active_name = active.name

    r = client.put(f"/api/sessions/{other.session_id}", json={"name": "新名字"})
    assert r.status_code == 200
    assert session_mgr.get(other.session_id).name == "新名字"
    assert session_mgr.get(active.session_id).name == old_active_name


def test_rename_validation(client, session_mgr):
    a = session_mgr.create(name="甲")
    session_mgr.create(name="乙")
    assert client.put(f"/api/sessions/{a.session_id}", json={"name": "乙"}).status_code == 400
    assert client.put(f"/api/sessions/{a.session_id}", json={"name": "  "}).status_code == 400
    assert client.put("/api/sessions/sess_nope", json={"name": "丙"}).status_code == 404
