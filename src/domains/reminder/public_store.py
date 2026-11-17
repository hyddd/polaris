"""提醒的公共存储和公私组合存储。

- PublicReminderStore：team 服务用，直接读写 MySQL；
- RemoteReminderStore：personal 服务用，调 team 服务的 /api/reminders 接口；
- ScopedReminderStore：组合存储。

公共提醒的特殊点：
- team 服务和每个 personal 服务都会调度并推给**自己的用户**（投递目标不入库）；
- 一次性提醒触发后改成 cancelled 用条件更新（只改 active 的），多处同时触发结果一样；
- 本机没送达不改共享状态（别处可能送达了），只记本地日志；
- 公共提醒的新增/修改/删除靠 public:sync 定期拉取后重新调度（ReminderDomain.sync_public）。
"""
import logging
from datetime import datetime

from src.core.db import PUBLIC, PRIVATE
from src.core.db.public_store import PrivateOnly, PublicStoreBase, MergedReadMixin, now
from src.core.db.remote import RemoteError, get_remote
from .models import Reminder, ReminderStatus, RepeatRule
from .store import ReminderStore

logger = logging.getLogger("polaris.reminder.public")

_UPDATABLE = {"title", "description", "trigger_time", "repeat_rule", "status", "event_id"}


class RemoteReminderStore:
    """personal → team：公共提醒通过 HTTP 读写。"""

    def __init__(self, client_getter=get_remote):
        self._client_getter = client_getter

    def _c(self):
        c = self._client_getter()
        if c is None:
            raise RemoteError("没有连接团队服务")
        return c

    def _item(self, d: dict) -> Reminder:
        r = Reminder.from_dict(d)
        r.scope, r.channel, r.session_id = PUBLIC, "admin", ""   # 推给本机用户
        return r

    def create(self, reminder: Reminder) -> Reminder:
        body = {"title": reminder.title, "description": reminder.description,
                "trigger_time": reminder.trigger_time.isoformat(), "repeat_rule": reminder.repeat_rule.value,
                "event_id": reminder.event_id, "scope": PUBLIC}
        return self._item(self._c().post("/api/reminders", body))

    def get(self, reminder_id: str) -> Reminder | None:
        try:
            return self._item(self._c().get(f"/api/reminders/{reminder_id}"))
        except RemoteError as e:
            if e.status == 404:
                return None
            raise

    def list_all(self) -> list[Reminder]:
        return [self._item(d) for d in self._c().get("/api/reminders").get("items", [])]

    def list_active(self) -> list[Reminder]:
        return [r for r in self.list_all() if r.status == ReminderStatus.ACTIVE]

    def find_by_event_id(self, event_id: str) -> list[Reminder]:
        return [r for r in self.list_all() if r.event_id == event_id]

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        fields = {k: v for k, v in kwargs.items() if k in _UPDATABLE}
        if fields.get("status") == ReminderStatus.FAILED:
            fields.pop("status")      # 本机没送达：不改共享状态
            logger.warning(f"公共提醒 {reminder_id} 在本机未送达，共享状态保持不变")
        if not fields:
            return self.get(reminder_id)
        body = {}
        for k, v in fields.items():
            if isinstance(v, datetime):
                v = v.isoformat()
            elif hasattr(v, "value"):
                v = v.value
            body[k] = v
        try:
            return self._item(self._c().put(f"/api/reminders/{reminder_id}", body))
        except RemoteError as e:
            if e.status == 404:
                return None
            raise

    def delete(self, reminder_id: str) -> bool:
        try:
            self._c().delete(f"/api/reminders/{reminder_id}")
            return True
        except RemoteError as e:
            if e.status == 404:
                return False
            raise


class PublicReminderStore(PublicStoreBase):

    def _row(self, r: dict) -> Reminder:
        return Reminder(
            id=r["id"], title=r["title"], description=r["description"] or "",
            trigger_time=r["trigger_time"], repeat_rule=RepeatRule(r["repeat_rule"]),
            event_id=r["event_id"], channel="admin", session_id="",   # 推给本机用户
            created_at=r["created_at"], status=ReminderStatus(r["status"]), scope=PUBLIC,
        )

    def create(self, reminder: Reminder) -> Reminder:
        db = self.db()
        ts = now()
        db.execute(f"INSERT INTO {db.t('reminders')} (id, title, description, trigger_time, repeat_rule, status, "
                   f"event_id, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (reminder.id, reminder.title, reminder.description, reminder.trigger_time,
                    reminder.repeat_rule.value, reminder.status.value, reminder.event_id, reminder.created_at, ts))
        reminder.scope, reminder.channel, reminder.session_id = PUBLIC, "admin", ""
        return reminder

    def get(self, reminder_id: str) -> Reminder | None:
        db = self.db()
        r = db.fetchone(f"SELECT * FROM {db.t('reminders')} WHERE id=%s", (reminder_id,))
        return self._row(r) if r else None

    def _list(self, where: str = "", args=()) -> list[Reminder]:
        db = self.db()
        rows = db.fetchall(f"SELECT * FROM {db.t('reminders')} {where} ORDER BY trigger_time", args)
        return [self._row(r) for r in rows]

    def list_active(self) -> list[Reminder]:
        return self._list("WHERE status='active'")

    def list_all(self) -> list[Reminder]:
        return self._list()

    def find_by_event_id(self, event_id: str) -> list[Reminder]:
        return self._list("WHERE event_id=%s", (event_id,))

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        fields = {k: v for k, v in kwargs.items() if k in _UPDATABLE}
        if fields.get("status") == ReminderStatus.FAILED:
            # 本机没送达；别的实例可能送达了，不改共享状态
            fields.pop("status")
            logger.warning(f"公共提醒 {reminder_id} 在本机未送达，共享状态保持不变")
        db = self.db()
        if fields:
            sets, args = [], []
            for k, v in fields.items():
                sets.append(f"{k}=%s")
                args.append(v.value if hasattr(v, "value") else v)
            sets.append("updated_at=%s")
            args += [now(), reminder_id]
            where = "WHERE id=%s"
            if fields == {"status": ReminderStatus.CANCELLED}:
                where += " AND status='active'"     # 多个实例同时触发：只有第一个真正改，其余是空操作
            db.execute(f"UPDATE {db.t('reminders')} SET {', '.join(sets)} {where}", args)
        return self.get(reminder_id)

    def delete(self, reminder_id: str) -> bool:
        db = self.db()
        return db.execute(f"DELETE FROM {db.t('reminders')} WHERE id=%s", (reminder_id,)) > 0


class ScopedReminderStore(MergedReadMixin):
    def __init__(self, private: ReminderStore, public: PublicReminderStore | None):
        self._private = PrivateOnly(private)
        self._public = public

    @property
    def has_public(self) -> bool:
        return self._public is not None

    def create(self, reminder: Reminder) -> Reminder:
        if reminder.scope == PUBLIC:
            if self._public is None:
                raise RuntimeError("公共库未启用，不能创建公共提醒")
            return self._public.create(reminder)
        reminder.scope = PRIVATE
        return self._private.create(reminder)

    def get(self, reminder_id: str) -> Reminder | None:
        return self._private.get(reminder_id) or self._public_read(lambda: self._public.get(reminder_id), None)

    def list_active(self) -> list[Reminder]:
        return self._private.list_active() + self._public_read(self._public.list_active if self._public else None, [])

    def list_all(self) -> list[Reminder]:
        return self._private.list_all() + self._public_read(self._public.list_all if self._public else None, [])

    def list_public(self) -> list[Reminder]:
        """同步用：直接读公共数据（数据库或 team 接口），出错时抛出（由调用方决定怎么处理）。"""
        return self._public.list_all() if self._public else []

    def find_by_event_id(self, event_id: str) -> list[Reminder]:
        return self._private.find_by_event_id(event_id) + \
            self._public_read(lambda: self._public.find_by_event_id(event_id), [])

    def _owner(self, reminder_id: str):
        if self._private.get(reminder_id):
            return self._private
        if self._public is not None and self._public.get(reminder_id):
            return self._public
        return None

    def update(self, reminder_id: str, **kwargs) -> Reminder | None:
        owner = self._owner(reminder_id)
        return owner.update(reminder_id, **kwargs) if owner else None

    def delete(self, reminder_id: str) -> bool:
        owner = self._owner(reminder_id)
        return owner.delete(reminder_id) if owner else False
