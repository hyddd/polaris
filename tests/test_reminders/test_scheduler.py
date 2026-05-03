from datetime import datetime, timedelta
from src.reminders.models import Reminder, RepeatRule
from src.reminders.scheduler import ReminderScheduler


def test_to_cron_daily():
    scheduler = ReminderScheduler(None, None)
    dt = datetime(2026, 5, 3, 14, 30)
    assert scheduler._to_cron(dt, RepeatRule.DAILY) == "30 14 * * *"


def test_to_cron_weekly():
    scheduler = ReminderScheduler(None, None)
    dt = datetime(2026, 5, 4, 9, 0)  # Monday
    assert scheduler._to_cron(dt, RepeatRule.WEEKLY) == "0 9 * * 0"


def test_to_cron_monthly():
    scheduler = ReminderScheduler(None, None)
    dt = datetime(2026, 5, 15, 10, 0)
    assert scheduler._to_cron(dt, RepeatRule.MONTHLY) == "0 10 15 * *"
