"""ReminderDomain 单元测试（CRUD 部分，不测试调度）。"""

from datetime import datetime, timedelta

import pytest

from src.domains.reminder.store import ReminderStore
from src.domains.reminder.handler import ReminderHandler
from src.domains.reminder.domain import ReminderDomain
from src.domains.reminder.models import ReminderStatus


@pytest.fixture
def domain(tmp_path):
    store = ReminderStore(str(tmp_path / "reminders.json"))
    handler = ReminderHandler(channels=[], store=store)
    return ReminderDomain(store, handler)


def _future_time(hours=1):
    return datetime.now() + timedelta(hours=hours)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


def test_create_reminder(domain):
    trigger = _future_time()
    r = domain.create("喝水提醒", trigger_time=trigger, description="每小时喝一杯水")
    assert r.title == "喝水提醒"
    assert r.description == "每小时喝一杯水"
    assert r.status == ReminderStatus.ACTIVE
    assert r.trigger_time == trigger


def test_list_active(domain):
    domain.create("提醒A", trigger_time=_future_time())
    r2 = domain.create("提醒B", trigger_time=_future_time())
    domain.pause(r2.id)
    active = domain.list_active()
    assert len(active) == 1
    assert active[0].title == "提醒A"


def test_update_reminder(domain):
    r = domain.create("原标题", trigger_time=_future_time())
    updated = domain.update(r.id, title="新标题", description="更新描述")
    assert updated is not None
    assert updated.title == "新标题"
    assert updated.description == "更新描述"


def test_delete_reminder(domain):
    r = domain.create("待删除", trigger_time=_future_time())
    assert domain.delete(r.id) is True
    assert domain.get(r.id) is None


def test_pause_and_resume(domain):
    r = domain.create("暂停测试", trigger_time=_future_time())
    # 暂停
    paused = domain.pause(r.id)
    assert paused is not None
    assert paused.status == ReminderStatus.PAUSED
    # 活跃列表中应无此提醒
    assert len(domain.list_active()) == 0
    # 恢复
    resumed = domain.resume(r.id)
    assert resumed is not None
    assert resumed.status == ReminderStatus.ACTIVE
    assert len(domain.list_active()) == 1
