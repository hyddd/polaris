import logging
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger("polaris.tools.reminder")


def create_default() -> "ReminderTool":
    """Factory for auto-discovery."""
    return ReminderTool()


class ReminderInput(BaseModel):
    action: Literal["list", "create", "update", "delete", "pause", "resume"] = Field(
        description="操作类型"
    )
    reminder_id: Optional[str] = Field(default=None, description="update/delete/pause/resume 时的提醒 ID")
    title: Optional[str] = Field(default=None, description="create 时的提醒标题")
    description: Optional[str] = Field(default=None, description="create 时的详细描述")
    trigger_time: Optional[str] = Field(default=None, description="create/update 时的触发时间，格式 ISO 8601")
    repeat_rule: Optional[str] = Field(default=None, description="create/update 时的重复规则：none/daily/weekly/monthly")
    event_id: Optional[str] = Field(default=None, description="create 时关联的日程 ID（可选）")


class ReminderTool(BaseTool):
    name: str = "reminder"
    description: str = "管理定时提醒：创建、查看、修改、删除、暂停、恢复提醒。"
    args_schema: type[BaseModel] = ReminderInput

    def _run(self, action: str, reminder_id: str | None = None, title: str | None = None,
             description: str | None = None, trigger_time: str | None = None,
             repeat_rule: str | None = None, event_id: str | None = None) -> str:
        from src.reminders.models import Reminder, RepeatRule, ReminderStatus
        from src.reminders.store import ReminderStore
        from src.config import REMINDERS_FILE
        from src.agent.executor import get_tool_context

        ctx = get_tool_context()
        _channel = ctx.get("channel", "")
        _session_id = ctx.get("session_id", "")

        store = ReminderStore(str(REMINDERS_FILE))

        if action == "list":
            reminders = store.list_active()
            if not reminders:
                return "没有活跃的提醒。"
            lines = []
            for r in reminders:
                lines.append(f"- [{r.id}] {r.title} @ {r.trigger_time.strftime('%Y-%m-%d %H:%M')}")
                if r.repeat_rule != RepeatRule.NONE:
                    lines[-1] += f" ({r.repeat_rule.value})"
            return "\n".join(lines)

        elif action == "create":
            if not title or not trigger_time:
                return "创建提醒需要提供标题和触发时间。"
            try:
                dt = datetime.fromisoformat(trigger_time)
            except ValueError:
                return "时间格式错误，请使用 ISO 8601 格式（如 2026-05-03T09:00:00）。"
            if dt < datetime.now():
                return "触发时间不能是过去。"
            logger.info(f"Creating reminder: channel={_channel}, session_id={_session_id}")
            r = Reminder(
                title=title,
                description=description or "",
                trigger_time=dt,
                repeat_rule=RepeatRule(repeat_rule or "none"),
                event_id=event_id,
                channel=_channel or "admin",
                session_id=_session_id or "",
            )
            store.create(r)
            return f"已创建提醒：{r.title} @ {dt.strftime('%Y-%m-%d %H:%M')} [{r.id}]"

        elif action == "update":
            if not reminder_id:
                return "修改提醒需要提供提醒 ID。"
            kwargs = {}
            if title:
                kwargs["title"] = title
            if description:
                kwargs["description"] = description
            if trigger_time:
                try:
                    kwargs["trigger_time"] = datetime.fromisoformat(trigger_time)
                except ValueError:
                    return "时间格式错误。"
            if repeat_rule:
                kwargs["repeat_rule"] = RepeatRule(repeat_rule)
            r = store.update(reminder_id, **kwargs)
            if not r:
                return f"未找到提醒：{reminder_id}"
            return f"已更新提醒：{r.title}"

        elif action == "delete":
            if not reminder_id:
                return "删除提醒需要提供提醒 ID。"
            if store.delete(reminder_id):
                return f"已删除提醒：{reminder_id}"
            return f"未找到提醒：{reminder_id}"

        elif action == "pause":
            if not reminder_id:
                return "暂停提醒需要提供提醒 ID。"
            r = store.update(reminder_id, status=ReminderStatus.PAUSED)
            if not r:
                return f"未找到提醒：{reminder_id}"
            return f"已暂停提醒：{r.title}"

        elif action == "resume":
            if not reminder_id:
                return "恢复提醒需要提供提醒 ID。"
            r = store.update(reminder_id, status=ReminderStatus.ACTIVE)
            if not r:
                return f"未找到提醒：{reminder_id}"
            return f"已恢复提醒：{r.title}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
