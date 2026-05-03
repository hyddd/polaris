from datetime import datetime
from src.reminders.models import Reminder, RepeatRule, ReminderStatus


def test_create_reminder():
    r = Reminder(
        id="rmd-test123",
        title="测试提醒",
        description="测试描述",
        trigger_time=datetime(2026, 5, 3, 9, 0),
        repeat_rule=RepeatRule.NONE,
        channel="feishu",
        session_id="session-1",
        user_id="user-1",
    )
    assert r.id == "rmd-test123"
    assert r.title == "测试提醒"
    assert r.status == ReminderStatus.ACTIVE
    assert r.event_id is None


def test_reminder_to_dict():
    r = Reminder(
        id="rmd-test123",
        title="测试",
        trigger_time=datetime(2026, 5, 3, 9, 0),
    )
    d = r.to_dict()
    assert d["id"] == "rmd-test123"
    assert d["trigger_time"] == "2026-05-03T09:00:00"
    assert d["repeat_rule"] == "none"


def test_reminder_from_dict():
    d = {
        "id": "rmd-test123",
        "title": "测试",
        "trigger_time": "2026-05-03T09:00:00",
        "repeat_rule": "none",
        "status": "active",
        "channel": "feishu",
        "session_id": "s1",
        "user_id": "u1",
        "created_at": "2026-05-02T10:00:00",
    }
    r = Reminder.from_dict(d)
    assert r.trigger_time == datetime(2026, 5, 3, 9, 0)
    assert r.repeat_rule == RepeatRule.NONE
