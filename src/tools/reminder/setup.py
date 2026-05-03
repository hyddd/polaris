"""提醒模块的全局依赖，由 server.py 初始化。"""

import logging

from .service import ReminderService, schedule_reminder

logger = logging.getLogger("polaris.reminders.setup")

_reminder_store = None
_reminder_service = None
_reminder_handler = None


def get_reminder_store():
    return _reminder_store


def set_reminder_store(store):
    global _reminder_store
    _reminder_store = store


def get_reminder_service():
    return _reminder_service


def set_reminder_service(service):
    global _reminder_service
    _reminder_service = service


def get_reminder_handler():
    return _reminder_handler


def set_reminder_handler(handler):
    global _reminder_handler
    _reminder_handler = handler


def reminder_setup(cron, store, handler):
    """初始化提醒：加载活跃提醒并加入 cron 调度。"""
    reminders = store.list_active()
    for r in reminders:
        schedule_reminder(cron, handler, r)
    service = ReminderService(store, cron, handler)
    set_reminder_service(service)
    set_reminder_store(store)
    set_reminder_handler(handler)
