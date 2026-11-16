"""① 提醒投递：网页创建的提醒送得到；送不到不能标成已完成。"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import src.session.manager as manager_mod
from src.domains.reminder.domain import ReminderDomain
from src.domains.reminder.handler import ReminderHandler
from src.domains.reminder.models import Reminder, ReminderStatus, RepeatRule
from src.domains.reminder.store import ReminderStore


@pytest.fixture
def store(tmp_path):
    return ReminderStore(str(tmp_path / "reminders.json"))


def _one_shot(store, **kw):
    r = Reminder(title="开会", trigger_time=datetime.now() - timedelta(minutes=1), **kw)
    store.create(r)
    return r


def _disk_contents(sid):
    data = json.loads((manager_mod.SESSIONS_DIR / f"{sid}.json").read_text(encoding="utf-8"))
    return [m["content"] for m in data["messages"]]


def test_unbound_admin_reminder_goes_to_web_active_session(session_mgr, store):
    """网页日历/提醒接口创建的提醒 session_id 为空：以前到点直接丢、还标成完成。"""
    target = session_mgr.active_session("admin")
    r = _one_shot(store, channel="admin", session_id="")

    delivered = ReminderHandler([], store=store).handle(r)

    assert "⏰ 提醒：开会" in [m.content for m in target.memory.get_messages()]
    assert "⏰ 提醒：开会" in _disk_contents(target.session_id)      # 已落盘，重启不丢
    assert store.get(r.id).status == ReminderStatus.CANCELLED          # 送达才算完成
    assert delivered is True


def test_reminder_for_deleted_session_falls_back(session_mgr, store):
    gone = session_mgr.create(name="会被删")
    session_mgr.delete(gone.session_id)
    r = _one_shot(store, channel="admin", session_id=gone.session_id)
    delivered = ReminderHandler([], store=store).handle(r)
    active = session_mgr.active_session("admin")
    assert "⏰ 提醒：开会" in [m.content for m in active.memory.get_messages()]
    assert delivered is True


class _Channel:
    name = "qq"

    def __init__(self, result):
        self.result = result

    def send_message(self, **kw):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.parametrize("channels", [
    [],                                   # 渠道插件不存在
    [_Channel(False)],                    # 发送返回失败
    [_Channel(RuntimeError("网络断了"))],  # 发送抛异常
])
def test_undelivered_one_shot_is_failed_not_completed(session_mgr, store, channels):
    r = _one_shot(store, channel="qq:u1", session_id="")
    delivered = ReminderHandler(channels, store=store).handle(r)
    assert store.get(r.id).status == ReminderStatus.FAILED
    assert delivered is False


def test_delivered_channel_reminder_completes(session_mgr, store):
    r = _one_shot(store, channel="qq:u1", session_id="")
    assert ReminderHandler([_Channel(True)], store=store).handle(r) is True
    assert store.get(r.id).status == ReminderStatus.CANCELLED


def test_resume_failed_reminder_redelivers(session_mgr, store):
    """failed 的提醒在提醒页点“恢复”会立即重投。"""
    r = _one_shot(store, channel="qq:u1", session_id="")
    channel = _Channel(False)
    handler = ReminderHandler([channel], store=store)
    domain = ReminderDomain(store, handler)
    handler.handle(r)
    assert store.get(r.id).status == ReminderStatus.FAILED

    channel.result = True
    with patch("src.domains.scheduler.get_scheduler_domain", return_value=object()):
        domain.resume(r.id)
    assert store.get(r.id).status == ReminderStatus.CANCELLED


def test_repeating_reminder_status_unchanged_on_failure(session_mgr, store):
    r = Reminder(title="日报", trigger_time=datetime.now(), repeat_rule=RepeatRule.DAILY,
                 channel="qq:u1")
    store.create(r)
    assert ReminderHandler([], store=store).handle(r) is False
    assert store.get(r.id).status == ReminderStatus.ACTIVE
