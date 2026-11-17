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


def _signature(r: Reminder) -> tuple:
    """决定调度方式的字段；变了就要重新调度。"""
    return (r.trigger_time, r.repeat_rule, r.status)


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

class ReminderDomain:
    def __init__(self, store: ReminderStore, handler: ReminderHandler):
        self._store = store
        self._handler = handler
        # 本实例已按什么参数调度了哪些公共提醒：sync_public 据此判断要不要重新调度
        self._public_sigs: dict[str, tuple] = {}
        # 最近一次同步到的公共提醒：personal 触发时 team 服务恰好连不上，也能照常提醒
        self._public_cache: dict[str, Reminder] = {}

    @property
    def public_error(self) -> str | None:
        return getattr(self._store, "public_error", None)

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
               session_id: str = "", scope: str | None = None) -> Reminder:
        """创建提醒并调度。scope：public 存公共库（每个实例都推送给自己的用户）、private 存本机。"""
        from src.core.db import resolve_scope, PUBLIC
        scope = resolve_scope(scope)
        if scope == PUBLIC:
            channel, session_id = "admin", ""     # 投递目标是各实例自己的用户，不记录创建者的会话
        r = Reminder(
            title=title,
            description=description,
            trigger_time=trigger_time,
            repeat_rule=RepeatRule(repeat_rule),
            event_id=event_id,
            channel=channel,
            session_id=session_id,
            scope=scope,
        )
        # personal 存公共提醒时 ID 由 team 服务分配，以存储返回的为准
        r = self._store.create(r)
        self._schedule(r)
        if scope == PUBLIC:
            self._public_sigs[r.id] = _signature(r)
            self._public_cache[r.id] = r
        event_bus.publish("reminder:reminder_created",
                          reminder_id=r.id, title=r.title,
                          trigger_time=r.trigger_time.isoformat())
        logger.info(f"已创建{scope}提醒: {r.id} - {r.title} @ {r.trigger_time}")
        return r

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        """更新提醒，如涉及时间/重复规则则重新调度。"""
        need_reschedule = "trigger_time" in kwargs or "repeat_rule" in kwargs
        r = self._store.update(reminder_id, **kwargs)
        if not r:
            return None
        if need_reschedule:
            self._unschedule(reminder_id)
            self._public_sigs.pop(reminder_id, None)
            r = self._store.get(reminder_id)
            if r and r.status == ReminderStatus.ACTIVE:
                self._schedule(r)
                if r.scope == "public":
                    self._public_sigs[r.id] = _signature(r)
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
            self._public_sigs.pop(reminder_id, None)
            event_bus.publish("reminder:reminder_deleted",
                              reminder_id=reminder_id)
            logger.info(f"已删除提醒: {reminder_id}")
        return deleted

    def pause(self, reminder_id: str) -> Reminder | None:
        """暂停提醒。"""
        r = self._store.update(reminder_id, status=ReminderStatus.PAUSED)
        if r:
            self._unschedule(reminder_id)
            self._public_sigs.pop(reminder_id, None)
            logger.info(f"已暂停提醒: {r.id}")
        return r

    def resume(self, reminder_id: str) -> Reminder | None:
        """恢复提醒。"""
        r = self._store.update(reminder_id, status=ReminderStatus.ACTIVE)
        if r:
            self._schedule(r)
            if r.scope == "public":
                self._public_sigs[r.id] = _signature(r)
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
            # 只清理本机私有提醒；公共数据不由个人实例按自己的配置删除
            if r.scope == "private" and r.status == ReminderStatus.CANCELLED and r.trigger_time < cutoff:
                self._store.delete(r.id)
                count += 1
        if count:
            logger.info(f"清理 {count} 条过期提醒（保留 {retention} 天）")
        return count

    # ------------------------------------------------------------------
    # 公共提醒同步（public:sync 定期触发）
    # ------------------------------------------------------------------

    def sync_public(self) -> int:
        """从公共库拉取公共提醒，让本实例的调度和公共库一致。返回本次变更的调度数。

        - 需要调度：active，且是周期提醒或触发时间还没到；
        - 已错过的一次性提醒不补发（和启动时"跳过过期提醒"一致），避免每次同步都重复推送；
        - 公共库里没了、暂停了、已触发的：撤销本机调度。
        """
        if not getattr(self._store, "has_public", False):
            return 0
        from src.core.db import DatabaseError
        try:
            reminders = self._store.list_public()
        except DatabaseError as e:
            logger.warning(f"公共提醒同步失败（下次再试）：{e}")
            return 0
        self._public_cache = {r.id: r for r in reminders}
        now = datetime.now()
        changed = 0
        seen = set()
        for r in reminders:
            seen.add(r.id)
            wanted = r.status == ReminderStatus.ACTIVE and (r.repeat_rule != RepeatRule.NONE or r.trigger_time > now)
            sig = _signature(r)
            if wanted and self._public_sigs.get(r.id) != sig:
                self._schedule(r)
                self._public_sigs[r.id] = sig
                changed += 1
            elif not wanted and r.id in self._public_sigs:
                self._unschedule(r.id)
                del self._public_sigs[r.id]
                changed += 1
        for rid in [rid for rid in self._public_sigs if rid not in seen]:
            self._unschedule(rid)
            del self._public_sigs[rid]
            changed += 1
        if changed:
            logger.info(f"公共提醒同步：{changed} 项调度变更")
        return changed

    # ------------------------------------------------------------------
    # 触发（供 SchedulerDomain 调用）
    # ------------------------------------------------------------------

    def trigger(self, reminder_id: str) -> None:
        """触发提醒（由 SchedulerDomain 调度回调）。"""
        reminder = self._store.get(reminder_id) or self._public_cache.get(reminder_id)
        if not reminder:
            logger.warning(f"触发失败，提醒不存在: {reminder_id}")
            return
        self._deliver(reminder)

    def _deliver(self, reminder: Reminder) -> bool:
        """推送提醒，并发布 reminder:triggered（webhook 通知等订阅者据此转发）。"""
        delivered = self._handler.handle(reminder)
        event_bus.publish("reminder:triggered",
                          reminder_id=reminder.id, title=reminder.title,
                          description=reminder.description,
                          trigger_time=reminder.trigger_time.isoformat(),
                          scope=reminder.scope,
                          channel=reminder.channel, session_id=reminder.session_id,
                          delivered=delivered)
        return delivered

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
                self._deliver(reminder)
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
    from src.core.db import is_team, public_enabled, instance_info
    from src.core.db.public_store import NoPrivate
    from .public_store import PublicReminderStore, RemoteReminderStore, ScopedReminderStore
    global _domain

    if is_team():
        private = NoPrivate()
        public = PublicReminderStore() if public_enabled() else None
    else:
        path = str(config.resolve_path(config.get("storage.reminders_file", "data/reminders.json")))
        private = ReminderStore(path)
        public = RemoteReminderStore() if public_enabled() else None
    store = ScopedReminderStore(private, public)
    handler = ReminderHandler(channels or [], store=store)
    _domain = ReminderDomain(store, handler)

    # 向 SchedulerDomain 注册 reminder handler
    from src.domains.scheduler import get_scheduler_domain
    scheduler = get_scheduler_domain()
    if scheduler:
        scheduler.register_handler(
            "reminder",
            lambda **kw: _domain.trigger(kw["reminder_id"]),
        )

    # 恢复本机私有提醒的调度；公共提醒由 sync_public 按公共库调度
    now = datetime.now()
    for r in private.list_active():
        if r.repeat_rule == RepeatRule.NONE and r.trigger_time <= now:
            private.update(r.id, status=ReminderStatus.CANCELLED)
            logger.info(f"跳过过期提醒: {r.id} - {r.title}")
        else:
            _domain._schedule(r)
    _domain.sync_public()
    logger.info(f"提醒域已初始化（{instance_info()['mode_label']}），本机私人提醒 {len(private.list_all())} 条，"
                f"公共数据{'可用' if public_enabled() else '未启用'}")


def _on_public_sync(**kwargs):
    domain = get_reminder_domain()
    if domain:
        domain.sync_public()


event_bus.subscribe("app:startup", _on_startup)
event_bus.subscribe("public:sync", _on_public_sync)


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
def _handled_by_team(scope) -> bool:
    """personal 服务里的公共日程：关联提醒由 team 服务处理，本机不重复创建/修改/删除。"""
    from src.core.db import is_team, PUBLIC
    return scope == PUBLIC and not is_team()


def _on_calendar_created(event_id=None, title=None, event_time_str=None,
                         channel="admin", session_id="", scope=None, **kwargs):
    domain = get_reminder_domain()
    if not domain or _handled_by_team(scope):
        return

    # 去重：已存在关联提醒则跳过
    if domain.find_by_event_id(event_id):
        logger.debug(f"日程 {event_id} 已有关联提醒，跳过")
        return

    try:
        event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
        reminder_time = event_datetime - timedelta(minutes=15)

        r = domain.create(
            title=f"{title} 即将开始",
            trigger_time=reminder_time,
            description=f"日程「{title}」将在15分钟后开始",
            event_id=event_id,
            channel=channel or "admin",
            session_id=session_id or "",
            scope=scope,           # 跟随日程：公共日程的提醒也是公共的
        )
        logger.info(f"已创建日程关联提醒: {r.id} @ {reminder_time}")
    except Exception as e:
        logger.error(f"创建日程关联提醒失败: {e}")


def _on_calendar_updated(event_id=None, title=None, event_time_str=None, scope=None, **kwargs):
    domain = get_reminder_domain()
    if not domain or _handled_by_team(scope):
        return

    for reminder in domain.find_by_event_id(event_id):
        try:
            event_datetime = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
            new_reminder_time = event_datetime - timedelta(minutes=15)
            new_title = f"{title} 即将开始"

            update_kwargs = {
                "trigger_time": new_reminder_time,
                "title": new_title,
            }
            if new_reminder_time > datetime.now():
                update_kwargs["status"] = ReminderStatus.ACTIVE
            domain.update(reminder.id, **update_kwargs)
            logger.info(f"已更新日程关联提醒: {reminder.id} @ {new_reminder_time}")
        except Exception as e:
            logger.error(f"更新日程关联提醒失败: {e}")


def _on_calendar_deleted(event_id=None, scope=None, **kwargs):
    domain = get_reminder_domain()
    if not domain or _handled_by_team(scope):
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
