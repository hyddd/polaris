"""team 服务 + 真实 MySQL：公共数据进 MySQL、拒绝私人数据、多个 team 进程共享同一个库。

personal ↔ team 的 HTTP 链路见 test_team_personal_http.py。
"""
from datetime import datetime, timedelta

import pytest

from src.core.db import PUBLIC, ScopeError
from src.core.db.public_store import NoPrivate
from src.domains.calendar.domain import CalendarDomain
from src.domains.calendar.public_store import PublicCalendarStore, ScopedCalendarStore
from src.domains.reminder.domain import ReminderDomain
from src.domains.reminder.handler import ReminderHandler
from src.domains.reminder.models import ReminderStatus
from src.domains.reminder.public_store import PublicReminderStore, ScopedReminderStore
from src.domains.todos.domain import TodoDomain
from src.domains.todos.public_store import PublicTodoStore, ScopedTodoStore

from .conftest import requires_mysql, FakeChroma

pytestmark = requires_mysql


def _todos():
    return TodoDomain(ScopedTodoStore(NoPrivate(), PublicTodoStore()))


def _calendar():
    return CalendarDomain(ScopedCalendarStore(NoPrivate(), PublicCalendarStore()))


# ---------------------------------------------------------------------------
# 待办
# ---------------------------------------------------------------------------

def test_team_todos_in_mysql_and_refuses_private(team_on):
    db = team_on
    team = _todos()
    pub = team.create_todo(title="团队周报", due="2026-11-20")                 # team 默认 public
    assert pub.scope == PUBLIC
    assert db.fetchone(f"SELECT title, due_date FROM {db.t('todos')} WHERE id=%s", (pub.id,))["title"] == "团队周报"
    with pytest.raises(ScopeError, match="只保存公共数据"):
        team.create_todo(title="买咖啡", scope="private")

    assert {t.title: t.scope for t in team.list_todos("all")} == {"团队周报": PUBLIC}
    assert [t.title for t in team.search("周报")] == ["团队周报"]

    assert team.update_todo(pub.id, {"priority": "high", "due": "2026-12-01", "tags": ["团队"]}).priority == "high"
    got = team.get_todo(pub.id)
    assert (got.due, got.tags, got.scope) == ("2026-12-01", ["团队"], PUBLIC)
    assert team.mark_done(pub.id).status == "done"
    assert team.delete_todo(pub.id) and team.get_todo(pub.id) is None


def test_two_team_processes_share_mysql(team_on):
    a, b = _todos(), _todos()
    a.create_todo(title="大家的")
    assert {t.title for t in b.list_todos("all")} == {"大家的"}


def test_strict_mode_rejects_bad_data_instead_of_truncating(team_on):
    from src.core.db import DatabaseError
    with pytest.raises(DatabaseError):
        _todos().create_todo(title="x" * 600)           # title 列 500：严格模式报错，不会被悄悄截断


# ---------------------------------------------------------------------------
# 日程
# ---------------------------------------------------------------------------

def test_team_calendar_sorted_move_delete(team_on):
    team = _calendar()
    a = team.create_event(date="2026-11-21", title="团队评审", time="15:30", duration=90, attendees=["张三"])
    team.create_event(date="2026-11-21", title="晨会", time="09:00")

    day = team.list_events("2026-11-21")
    assert [(e.title, e.scope, e.time) for e in day] == [("晨会", PUBLIC, "09:00"), ("团队评审", PUBLIC, "15:30")]
    got = team.get_event(a.id)
    assert (got.duration, got.attendees) == (90, ["张三"])

    moved = team.update_event(a.id, {"time": "16:00"}, date="2026-11-22")
    assert (moved.date, moved.time, moved.scope) == ("2026-11-22", "16:00", PUBLIC)
    assert team.delete_event(a.id) and team.get_event(a.id) is None


# ---------------------------------------------------------------------------
# 提醒
# ---------------------------------------------------------------------------

class _FakeScheduler:
    def __init__(self):
        self.jobs = {}

    def add_date_job(self, job_id, name, run_date, handler_type, handler_kwargs):
        self.jobs[job_id] = ("date", run_date)

    def add_cron_job(self, job_id, name, trigger_kwargs, handler_type, handler_kwargs):
        self.jobs[job_id] = ("cron", trigger_kwargs)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)
        return True


def _reminders():
    store = ScopedReminderStore(NoPrivate(), PublicReminderStore())
    return ReminderDomain(store, ReminderHandler([], store=store)), store


@pytest.fixture
def scheduler(monkeypatch):
    s = _FakeScheduler()
    monkeypatch.setattr("src.domains.scheduler.get_scheduler_domain", lambda: s)
    return s


def test_public_reminder_created_by_one_instance_is_scheduled_by_other(team_on, scheduler, session_mgr):
    me, _ = _reminders()
    colleague, _ = _reminders()
    when = datetime.now() + timedelta(hours=2)

    r = me.create(title="周会", trigger_time=when, channel="qq:creator", session_id="sess_creator")
    assert r.scope == PUBLIC and (r.channel, r.session_id) == ("admin", "")   # 投递目标不记录创建者的
    assert colleague.sync_public() == 1                                           # 同事的实例同步后调度
    assert colleague.sync_public() == 0                                           # 没变化不重复调度

    me.update(r.id, trigger_time=when + timedelta(minutes=30))
    assert colleague.sync_public() == 1                                           # 时间改了，重新调度
    me.delete(r.id)
    assert colleague.sync_public() == 1 and f"reminder:{r.id}" not in scheduler.jobs


def test_public_reminder_trigger_delivers_locally_and_marks_once(team_on, scheduler, session_mgr):
    db = team_on
    me, _ = _reminders()
    colleague, _ = _reminders()
    r = me.create(title="交周报", trigger_time=datetime.now() + timedelta(hours=1))

    me.trigger(r.id)
    colleague.trigger(r.id)                     # 两个实例都触发：各推送给自己的用户
    texts = [m.content for m in session_mgr.active_session("admin").memory.get_messages()]
    assert texts.count("⏰ 提醒：交周报") == 2   # 测试里两个"实例"共用同一个会话管理器
    assert db.fetchone(f"SELECT status FROM {db.t('reminders')} WHERE id=%s", (r.id,))["status"] == "cancelled"


def test_public_reminder_local_failure_does_not_mark_shared_failed(team_on, scheduler, session_mgr):
    db = team_on
    me, store = _reminders()
    r = me.create(title="x", trigger_time=datetime.now() + timedelta(hours=1))
    store.update(r.id, status=ReminderStatus.FAILED)    # 本机没送达时 handler 会这样写
    assert db.fetchone(f"SELECT status FROM {db.t('reminders')} WHERE id=%s", (r.id,))["status"] == "active"


def test_team_creates_linked_reminder_for_public_event(team_on, scheduler, session_mgr, monkeypatch):
    import src.domains.reminder.domain as rd
    me, store = _reminders()
    monkeypatch.setattr(rd, "_domain", me)
    when = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
    rd._on_calendar_created(event_id="evt-pub", title="团队会", event_time_str=when, scope="public")
    assert [r.scope for r in store.find_by_event_id("evt-pub")] == [PUBLIC]
    rd._on_calendar_deleted(event_id="evt-pub", scope="public")
    assert store.find_by_event_id("evt-pub") == []


def test_cleanup_never_deletes_public(team_on, scheduler, session_mgr):
    me, store = _reminders()
    old = datetime.now() - timedelta(days=30)
    pub = me.create(title="旧公共", trigger_time=datetime.now() + timedelta(hours=1))
    store.update(pub.id, trigger_time=old, status=ReminderStatus.CANCELLED)
    me.cleanup(retention_days=7)
    assert store.get(pub.id) is not None


# ---------------------------------------------------------------------------
# 笔记 / 知识库：正文和文档记录进 MySQL，向量在 team 本机的 Chroma
# ---------------------------------------------------------------------------

def test_team_notes_and_documents(team_on, tmp_path, monkeypatch):
    from src.domains.notes.domain import NotesDomain
    from src.domains.notes.public_store import PublicNoteStore, ScopedNoteStore
    from src.domains.rag.domain import RAGDomain
    from src.domains.rag.public_store import PublicDocMeta
    import src.domains.notes.domain as notes_mod

    db = team_on
    chroma = FakeChroma()
    rag = RAGDomain(chroma, doc_meta=PublicDocMeta())
    assert rag.local_scope == PUBLIC
    notes = NotesDomain(ScopedNoteStore(NoPrivate(), PublicNoteStore()), persist_dir="x", local_scope=PUBLIC)
    monkeypatch.setattr(notes_mod.NotesDomain, "_search_local",
                        lambda self, kw: [r for r in rag.search(kw)])          # 本机 Chroma 用替身

    pub = notes.create_note("部署手册", "MySQL 主从切换步骤")
    with pytest.raises(ScopeError):
        notes.create_note("日记", "今天很开心", scope="private")
    rag.index_note(pub.filename, pub.title, pub.content, pub.tags)             # 事件里是后台线程，这里直接调
    assert db.fetchone(f"SELECT title FROM {db.t('notes')} WHERE note_key=%s", (pub.filename,))["title"] == "部署手册"
    hits = notes.search("MySQL 主从")
    assert hits and (hits[0].scope, hits[0].title) == (PUBLIC, "部署手册")

    up = rag.upload_document(file_data="团队规范：代码评审必须两人通过".encode(), filename="规范.txt")
    assert up["scope"] == PUBLIC
    assert db.fetchone(f"SELECT filename FROM {db.t('knowledge_documents')} WHERE doc_id=%s",
                       (up["doc_id"],))["filename"] == "规范.txt"
    assert [d["filename"] for d in rag.list_documents()] == ["规范.txt"]
    assert any(r.scope == PUBLIC and "代码评审" in r.content for r in rag.search("代码评审"))
    assert rag.delete_document(up["doc_id"]) and rag.list_documents() == []
    assert notes.archive_note(pub.filename) and notes.get_note(pub.filename) is None
