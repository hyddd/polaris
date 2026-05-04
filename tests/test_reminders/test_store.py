import json
import tempfile
from pathlib import Path
from datetime import datetime
from src.domains.reminder.models import Reminder, ReminderStatus
from src.domains.reminder.store import ReminderStore


def test_create_and_get(tmp_path):
    store = ReminderStore(str(tmp_path / "reminders.json"))
    r = Reminder(id="rmd-1", title="测试", trigger_time=datetime(2026, 5, 3, 9, 0))
    store.create(r)
    got = store.get("rmd-1")
    assert got.title == "测试"


def test_list_active(tmp_path):
    store = ReminderStore(str(tmp_path / "reminders.json"))
    store.create(Reminder(id="rmd-1", title="A", status=ReminderStatus.ACTIVE))
    store.create(Reminder(id="rmd-2", title="B", status=ReminderStatus.CANCELLED))
    active = store.list_active()
    assert len(active) == 1
    assert active[0].id == "rmd-1"


def test_update(tmp_path):
    store = ReminderStore(str(tmp_path / "reminders.json"))
    store.create(Reminder(id="rmd-1", title="旧标题"))
    store.update("rmd-1", title="新标题")
    assert store.get("rmd-1").title == "新标题"


def test_delete(tmp_path):
    store = ReminderStore(str(tmp_path / "reminders.json"))
    store.create(Reminder(id="rmd-1", title="测试"))
    store.delete("rmd-1")
    assert store.get("rmd-1") is None
