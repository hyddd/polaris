"""CalendarDomain — 日程管理基础设施。"""

from .domain import get_calendar_domain, set_calendar_domain, CalendarDomain
from .models import CalendarEvent

__all__ = ["get_calendar_domain", "set_calendar_domain", "CalendarDomain", "CalendarEvent"]
