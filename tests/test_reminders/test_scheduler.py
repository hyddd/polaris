from datetime import datetime
from src.tools.reminder.models import Reminder, RepeatRule
from src.tools.reminder.service import repeat_rule_to_cron_kwargs


def test_repeat_rule_to_cron_kwargs_daily():
    dt = datetime(2026, 5, 3, 14, 30)
    kwargs = repeat_rule_to_cron_kwargs(dt, RepeatRule.DAILY)
    assert kwargs == {"hour": 14, "minute": 30}


def test_repeat_rule_to_cron_kwargs_weekly():
    dt = datetime(2026, 5, 4, 9, 0)  # Monday
    kwargs = repeat_rule_to_cron_kwargs(dt, RepeatRule.WEEKLY)
    assert kwargs == {"hour": 9, "minute": 0, "day_of_week": 0}


def test_repeat_rule_to_cron_kwargs_monthly():
    dt = datetime(2026, 5, 15, 10, 0)
    kwargs = repeat_rule_to_cron_kwargs(dt, RepeatRule.MONTHLY)
    assert kwargs == {"hour": 10, "minute": 0, "day": 15}
