"""ReminderDomain — 提醒管理核心服务。"""

import logging
from datetime import datetime, timedelta

from src.core.infra import event_bus
from .models import Reminder, RepeatRule, ReminderStatus
from .store import ReminderStore
from .handler import ReminderHandler

logger = logging.getLogger("polaris.reminder")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def repeat_rule_to_cron_kwargs(trigger_time: datetime, repeat_rule: RepeatRule) -> dict:
    """将重复规则转换为 APScheduler CronTrigger 关键字参数。"""
    if repeat_rule == RepeatRule.DAILY:
        return {"hour": trigger_time.hour, "minute": trigger_time.minute}
    elif repeat_rule == RepeatRule.WEEKLY:
        return {
            "hour": trigger_time.hour,
            "minute": trigger_time.minute,
            "day_of_week": trigger_time.weekday(),
        }
    elif repeat_rule == RepeatRule.MONTHLY:
        return {
            "hour": trigger_time.hour,
            "minute": trigger_time.minute,
            "day": trigger_time.day,
        }
    return {}


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class ReminderDomain:
    def __init__(self, store: ReminderStore, handler: ReminderHandler):
        self._store = store
        self._handler = handler

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_active(self) -> list[Reminder]:
        return self._store.list_active()

    def list_all(self) -> list[Reminder]:
        return self._store.list_all()

    def get(self, reminder_id: str) -> Reminder | None:
        return self._store.get(reminder_id)

    def find_by_event_id(self, event_id: str) -> list[Reminder]:
        return self._store.find_by_event_id(event_id)

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def create(self, title: str, trigger_time: datetime,
               repeat_rule: str = "none", description: str = "",
               event_id: str | None = None, channel: str = "admin",
               session_id: str = "") -> Reminder:
        """创建提醒并调度。"""
        r = Reminder(
            title=title,
            description=description,
            trigger_time=trigger_time,
            repeat_rule=RepeatRule(repeat_rule),
            event_id=event_id,
            channel=channel,
            session_id=session_id,
        )
        self._store.create(r)
        self._schedule(r)
        event_bus.publish("reminder:reminder_created",
                          reminder_id=r.id, title=r.title,
                          trigger_time=r.trigger_time.isoformat())
        logger.info(f"已创建提醒: {r.id} - {r.title} @ {r.trigger_time}")
        return r

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        """更新提醒，如涉及时间/重复规则则重新调度。"""
        need_reschedule = "trigger_time" in kwargs or "repeat_rule" in kwargs
        r = self._store.update(reminder_id, **kwargs)
        if not r:
            return None
        if need_reschedule:
            self._unschedule(reminder_id)
            r = self._store.get(reminder_id)
            if r and r.status == ReminderStatus.ACTIVE:
                self._schedule(r)
        event_bus.publish("reminder:reminder_updated",
                          reminder_id=r.id, title=r.title,
                          trigger_time=r.trigger_time.isoformat())
        logger.info(f"已更新提醒: {r.id}")
        return r

    def delete(self, reminder_id: str) -> bool:
        """删除提醒并移除调度。"""
        deleted = self._store.delete(reminder_id)
        if deleted:
            self._unschedule(reminder_id)
            event_bus.publish("reminder:reminder_deleted",
                              reminder_id=reminder_id)
            logger.info(f"已删除提醒: {reminder_id}")
        return deleted

    def pause(self, reminder_id: str) -> Reminder | None:
        """暂停提醒。"""
        r = self._store.update(reminder_id, status=ReminderStatus.PAUSED)
        if r:
            self._unschedule(reminder_id)
            logger.info(f"已暂停提醒: {r.id}")
        return r

    def resume(self, reminder_id: str) -> Reminder | None:
        """恢复提醒。"""
        r = self._store.update(reminder_id, status=ReminderStatus.ACTIVE)
        if r:
            self._schedule(r)
            logger.info(f"已恢复提醒: {r.id}")
        return r

    # ------------------------------------------------------------------
    # 维护
    # ------------------------------------------------------------------

    def cleanup(self, retention_days: int = 7) -> int:
        """清理过期已取消的提醒。"""
        from src.core.config import config
        retention = config.get("cleanup.reminders_retention_days", retention_days)
        cutoff = datetime.now() - timedelta(days=retention)
        count = 0
        for r in self._store.list_all():
            if r.status == ReminderStatus.CANCELLED and r.trigger_time < cutoff:
                self._store.delete(r.id)
                count += 1
        if count:
            logger.info(f"清理 {count} 条过期提醒（保留 {retention} 天）")
        return count

    # ------------------------------------------------------------------
    # 触发（供 SchedulerDomain 调用）
    # ------------------------------------------------------------------

    def trigger(self, reminder_id: str) -> None:
        """触发提醒（由 SchedulerDomain 调度回调）。"""
        reminder = self._store.get(reminder_id)
        if not reminder:
            logger.warning(f"触发失败，提醒不存在: {reminder_id}")
            return
        self._handler.handle(reminder)

    # ------------------------------------------------------------------
    # 调度委托 SchedulerDomain
    # ------------------------------------------------------------------

    def _schedule(self, reminder: Reminder):
        """通过 SchedulerDomain 注册调度任务。"""
        from src.domains.scheduler import get_scheduler_domain
        scheduler = get_scheduler_domain()
        if not scheduler:
            logger.warning("SchedulerDomain 未就绪，跳过调度")
            return

        if reminder.repeat_rule == RepeatRule.NONE:
            if reminder.trigger_time <= datetime.now():
                # 过期的一次性提醒直接触发
                logger.info(f"提醒时间已过，立即触发: {reminder.id} - {reminder.title}")
                self._handler.handle(reminder)
                return
            scheduler.add_date_job(
                job_id=f"reminder:{reminder.id}",
                name=f"提醒: {reminder.title}",
                run_date=reminder.trigger_time.isoformat(),
                handler_type="reminder",
                handler_kwargs={"reminder_id": reminder.id},
            )
        else:
            kwargs = repeat_rule_to_cron_kwargs(reminder.trigger_time, reminder.repeat_rule)
            scheduler.add_cron_job(
                job_id=f"reminder:{reminder.id}",
                name=f"提醒: {reminder.title}",
                trigger_kwargs=kwargs,
                handler_type="reminder",
                handler_kwargs={"reminder_id": reminder.id},
            )

    def _unschedule(self, reminder_id: str):
        """通过 SchedulerDomain 移除调度任务。"""
        from src.domains.scheduler import get_scheduler_domain
        scheduler = get_scheduler_domain()
        if scheduler:
            scheduler.remove_job(f"reminder:{reminder_id}")


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------
_domain: ReminderDomain | None = None


def get_reminder_domain() -> ReminderDomain:
    return _domain


# ---------------------------------------------------------------------------
# 启动集成
# ---------------------------------------------------------------------------
def _on_startup(channels=None, **kwargs):
    """框架就绪后自初始化。"""
    from src.core.config import config
    global _domain

    path = str(config.resolve_path(
        config.get("storage.reminders_file", "data/reminders.json")))
    store = ReminderStore(path)
    handler = ReminderHandler(channels or [], store=store)
    _domain = ReminderDomain(store, handler)

    # 恢复活跃提醒的调度
    now = datetime.now()
    for r in store.list_active():
        if r.repeat_rule == RepeatRule.NONE and r.trigger_time <= now:
            store.update(r.id, status=ReminderStatus.CANCELLED)
            logger.info(f"跳过过期提醒: {r.id} - {r.title}")
        else:
            _domain._schedule(r)
    logger.info(f"提醒域已初始化，加载 {len(store.list_all())} 条提醒")


event_bus.subscribe("app:startup", _on_startup)


# ---------------------------------------------------------------------------
# Cleanup 集成
# ---------------------------------------------------------------------------
def _on_cleanup(**kwargs):
    domain = get_reminder_domain()
    if domain:
        domain.cleanup()


event_bus.subscribe("cleanup:now", _on_cleanup)
event_bus.subscribe("cleanup:cron", _on_cleanup)


# ---------------------------------------------------------------------------
# Calendar 事件同步
# ---------------------------------------------------------------------------
def _on_calendar_created(event_id=None, title=None, event_time_str=None,
                         channel="admin", session_id="", **kwargs):
    domain = get_reminder_domain()
    if not domain:
        return

    # 去重：已存在关联提醒则跳过
    if domain.find_by_event_id(event_id):
        logger.debug(f"日程 {event_id} 已有关联提醒，跳过")
        return

    try:
        event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
        reminder_time = event_datetime - timedelta(minutes=15)
        is_past = reminder_time <= datetime.now()
        status = ReminderStatus.CANCELLED if is_past else ReminderStatus.ACTIVE

        r = Reminder(
            title=f"{title} 即将开始",
            description=f"日程「{title}」将在15分钟后开始",
            trigger_time=reminder_time,
            repeat_rule=RepeatRule.NONE,
            event_id=event_id,
            channel=channel or "admin",
            session_id=session_id or "",
            status=status,
        )
        domain._store.create(r)
        if not is_past:
            domain._schedule(r)
        logger.info(f"已创建日程关联提醒: {r.id} @ {reminder_time}")
    except Exception as e:
        logger.error(f"创建日程关联提醒失败: {e}")


def _on_calendar_updated(event_id=None, title=None, event_time_str=None, **kwargs):
    domain = get_reminder_domain()
    if not domain:
        return

    for reminder in domain.find_by_event_id(event_id):
        try:
            event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            new_reminder_time = event_datetime - timedelta(minutes=15)
            new_title = f"{title} 即将开始"

            domain._store.update(reminder.id,
                                 trigger_time=new_reminder_time, title=new_title)
            if new_reminder_time > datetime.now():
                domain._store.update(reminder.id, status=ReminderStatus.ACTIVE)
            reminder = domain._store.get(reminder.id)

            domain._unschedule(reminder.id)
            if new_reminder_time > datetime.now():
                domain._schedule(reminder)
            logger.info(f"已更新日程关联提醒: {reminder.id} @ {new_reminder_time}")
        except Exception as e:
            logger.error(f"更新日程关联提醒失败: {e}")


def _on_calendar_deleted(event_id=None, **kwargs):
    domain = get_reminder_domain()
    if not domain:
        return

    for reminder in domain.find_by_event_id(event_id):
        try:
            if domain.delete(reminder.id):
                logger.info(f"已删除日程关联提醒: {reminder.id}")
        except Exception as e:
            logger.error(f"删除日程关联提醒失败: {e}")


event_bus.subscribe("calendar:event_created", _on_calendar_created)
event_bus.subscribe("calendar:event_updated", _on_calendar_updated)
event_bus.subscribe("calendar:event_deleted", _on_calendar_deleted)
