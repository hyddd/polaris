"""Admin API: Data management (calendar/todos)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ._deps import require_domain, admin_delivery_target, scope_errors

router = APIRouter()


def _require_calendar_domain():
    from src.domains.calendar import get_calendar_domain
    return require_domain(get_calendar_domain, "日历")


def _require_todo_domain():
    from src.domains.todos import get_todo_domain
    return require_domain(get_todo_domain, "待办")


class DataUpdate(BaseModel):
    data: list | dict


@router.get("/api/data/{data_type}")
def list_data(data_type: str):
    """列出日程/待办：本机私有 + 公共库合并，每项带 scope。公共库读失败时 public_error 说明原因。"""
    if data_type == "calendar":
        domain = _require_calendar_domain()
        items = [e.to_dict() for e in domain.list_events()]
    elif data_type == "todos":
        domain = _require_todo_domain()
        items = [t.to_dict() for t in domain.list_todos("all")]
    else:
        raise HTTPException(400, f"Unknown type: {data_type}")
    return {"items": items, "public_error": domain.public_error}


@router.post("/api/data/{data_type}")
def create_data(data_type: str, req: DataUpdate):
    """创建日程/待办。data.scope 可选 public/private（不传用默认）。返回 {"ok": true, "item": {...}}。"""
    d = req.data if isinstance(req.data, dict) else {}
    with scope_errors():
        if data_type == "calendar":
            domain = _require_calendar_domain()
            item = domain.create_event(
                date=d.get("date", ""),
                title=d.get("title", ""),
                time=d.get("time", "09:00"),
                duration=d.get("duration", 60),
                attendees=d.get("attendees"),
                scope=d.get("scope"),
                # 自动关联的提前提醒要知道投给谁
                **admin_delivery_target(),
            )
        elif data_type == "todos":
            domain = _require_todo_domain()
            item = domain.create_todo(
                title=d.get("title", ""),
                priority=d.get("priority", "medium"),
                due=d.get("due", ""),
                scope=d.get("scope"),
            )
        else:
            raise HTTPException(400, f"Unknown type: {data_type}")
    return {"ok": True, "item": item.to_dict()}


@router.put("/api/data/{data_type}/{item_id}")
def update_data(data_type: str, item_id: str, req: DataUpdate):
    """修改日程/待办，data 里只放要改的字段（日程可带 date 换日期）。返回 {"ok": true, "item": {...}}。"""
    updates = dict(req.data) if isinstance(req.data, dict) else {}
    updates.pop("scope", None)      # 公共/私人不能改
    with scope_errors():
        if data_type == "calendar":
            result = _require_calendar_domain().update_event(item_id, updates)
        elif data_type == "todos":
            result = _require_todo_domain().update_todo(item_id, updates)
        else:
            raise HTTPException(400, f"Update not supported for {data_type}")
    if result is None:
        raise HTTPException(404, f"Item not found: {item_id}")
    return {"ok": True, "item": result.to_dict()}


@router.delete("/api/data/{data_type}/{item_id}")
def delete_data(data_type: str, item_id: str):
    with scope_errors():
        if data_type == "calendar":
            if not _require_calendar_domain().delete_event(item_id):
                raise HTTPException(404, "日程不存在")
        elif data_type == "todos":
            if not _require_todo_domain().delete_todo(item_id):
                raise HTTPException(404, f"Item not found: {item_id}")
        else:
            raise HTTPException(400, f"Delete not supported for {data_type}")
    return {"ok": True}
