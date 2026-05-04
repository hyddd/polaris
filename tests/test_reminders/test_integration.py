import json
from datetime import datetime, timedelta
from src.domains.reminder.models import Reminder, RepeatRule, ReminderStatus
from src.domains.reminder.store import ReminderStore


def test_full_lifecycle(tmp_path):
    """测试提醒完整生命周期"""
    store = ReminderStore(str(tmp_path / "reminders.json"))

    # 创建
    r = Reminder(
        id="rmd-test",
        title="测试提醒",
        trigger_time=datetime.now() + timedelta(hours=1),
        repeat_rule=RepeatRule.NONE,
    )
    store.create(r)

    # 查询
    assert store.get("rmd-test").title == "测试提醒"
    assert len(store.list_active()) == 1

    # 修改
    store.update("rmd-test", title="修改后的提醒")
    assert store.get("rmd-test").title == "修改后的提醒"

    # 暂停
    store.update("rmd-test", status=ReminderStatus.PAUSED)
    assert len(store.list_active()) == 0

    # 恢复
    store.update("rmd-test", status=ReminderStatus.ACTIVE)
    assert len(store.list_active()) == 1

    # 删除
    store.delete("rmd-test")
    assert store.get("rmd-test") is None


def test_persistence(tmp_path):
    """测试数据持久化"""
    path = str(tmp_path / "reminders.json")

    # 写入
    store1 = ReminderStore(path)
    store1.create(Reminder(id="rmd-1", title="持久化测试"))

    # 重新加载
    store2 = ReminderStore(path)
    assert store2.get("rmd-1").title == "持久化测试"
