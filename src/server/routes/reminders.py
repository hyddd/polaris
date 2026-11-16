"""Admin API: Reminders management."""
from datetime import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain, admin_delivery_target, scope_errors

router = APIRouter()


def _require_reminder_domain():
    from src.domains.reminder import get_reminder_domain
    return require_domain(get_reminder_domain, "提醒")


class ReminderCreate(BaseModel):
    title: str
    description: str = ""
    trigger_time: str  # ISO format datetime string
    repeat_rule: str = "none"
    scope: str | None = None  # public / private；不传用默认
    event_id: str | None = None  # 关联的日程（personal 转发公共日程的提醒时带上）


class ReminderUpdate(BaseModel):
    """只传要改的字段。personal 服务改公共提醒时调这个接口。"""
    title: str | None = None
    description: str | None = None
    trigger_time: str | None = None
    repeat_rule: str | None = None
    status: str | None = None
    event_id: str | None = None


def _parse_time(value: str):
    try:
        return dt.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "Invalid trigger_time format, expected ISO datetime")


@router.get("/api/reminders")
def list_reminders():
    domain = _require_reminder_domain()
    reminders = domain.list_all()
    return {"items": [r.to_dict() for r in reminders], "public_error": domain.public_error}


@router.post("/api/reminders")
def create_reminder(req: ReminderCreate):
    domain = _require_reminder_domain()
    trigger_time = _parse_time(req.trigger_time)
    with scope_errors():
        reminder = domain.create(
            title=req.title,
            trigger_time=trigger_time,
            repeat_rule=req.repeat_rule,
            description=req.description,
            event_id=req.event_id,
            scope=req.scope,
            **admin_delivery_target(),
        )
    return reminder.to_dict()


@router.get("/api/reminders/{reminder_id}")
def get_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    with scope_errors():
        r = domain.get(reminder_id)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()


@router.put("/api/reminders/{reminder_id}")
def update_reminder(reminder_id: str, req: ReminderUpdate):
    from src.domains.reminder.models import ReminderStatus, RepeatRule
    domain = _require_reminder_domain()
    fields = req.model_dump(exclude_none=True)
    try:
        if "trigger_time" in fields:
            fields["trigger_time"] = _parse_time(fields["trigger_time"])
        if "repeat_rule" in fields:
            fields["repeat_rule"] = RepeatRule(fields["repeat_rule"])
        status = ReminderStatus(fields.pop("status")) if "status" in fields else None
    except ValueError as e:
        raise HTTPException(400, str(e))
    with scope_errors():
        r = domain.get(reminder_id)
        if not r:
            raise HTTPException(404, f"提醒不存在: {reminder_id}")
        if fields:
            r = domain.update(reminder_id, **fields)
        # 暂停/恢复要同时改本机调度，走专门的方法；cancelled（一次性提醒已送达）只改状态
        if status == ReminderStatus.PAUSED:
            r = domain.pause(reminder_id)
        elif status == ReminderStatus.ACTIVE:
            r = domain.resume(reminder_id)
        elif status is not None:
            r = domain.update(reminder_id, status=status)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()


@router.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    if not domain.delete(reminder_id):
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return {"ok": True}


@router.post("/api/reminders/{reminder_id}/pause")
def pause_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    r = domain.pause(reminder_id)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()


@router.post("/api/reminders/{reminder_id}/resume")
def resume_reminder(reminder_id: str):
    domain = _require_reminder_domain()
    r = domain.resume(reminder_id)
    if not r:
        raise HTTPException(404, f"提醒不存在: {reminder_id}")
    return r.to_dict()
