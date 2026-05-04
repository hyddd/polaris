import json as _json
import logging
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from src.core.config import config

logger = logging.getLogger("polaris.tools.calendar")


def create_default() -> "GoogleCalendarTool":
    """Factory for auto-discovery. Creates a GoogleCalendarTool with default config."""
    from src.core.config import config
    return GoogleCalendarTool(
        data_file=str(config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))),
        use_mock=True,
    )


class CalendarInput(BaseModel):
    action: Literal["list", "search", "create", "update", "delete"] = Field(
        description="操作类型：list=查看日程, search=搜索事件, create=创建, update=修改, delete=删除"
    )
    date: Optional[str] = Field(default=None, description="list/create/update/delete 时的日期，格式 YYYY-MM-DD")
    keyword: Optional[str] = Field(default=None, description="search 时的搜索关键词")
    title: Optional[str] = Field(default=None, description="create/update/delete 时的事件标题（用于匹配）")
    time: Optional[str] = Field(default=None, description="create/update 时的事件时间，格式 HH:MM")
    attendees: Optional[list[str]] = Field(default=None, description="create 时的参与者列表")
    duration: Optional[int] = Field(default=60, description="create 时的事件时长（分钟），默认 60")
    event_id: Optional[str] = Field(default=None, description="update 或 delete 时的事件 ID（优先级高于 title+date）")
    updates: Optional[dict | str] = Field(default=None, description='update 时要修改的字段')

    @field_validator("updates", mode="before")
    @classmethod
    def _parse_updates(cls, v):
        if isinstance(v, str):
            return _json.loads(v)
        return v


class GoogleCalendarTool(BaseTool):
    name: str = "calendar"
    description: str = """管理日历事件。

规则：
1. 修改日程必须用 update，禁止 delete + create
2. 删除/修改前必须先 search 获取 event_id
3. 用户说"推迟""改到""换个时间""取消"等，都是修改意图，用 update

示例流程：
- "把明天晨会改到下午3点" → search(keyword="晨会") → update(event_id="xxx", updates={"time":"15:00"})
- "推迟会议1小时" → search(keyword="会议") → update(event_id="xxx", updates={"time":"原时间+1h"})"""
    args_schema: type[BaseModel] = CalendarInput
    data_file: str = ""
    use_mock: bool = config.get("tools.calendar.use_mock", False)

    def _resolve_event_id(self, domain, event_id: str | None,
                          title: str | None, date: str | None) -> str | None:
        """通过 event_id 或 title+date 搜索解析事件 ID。"""
        if event_id:
            return event_id
        if title:
            matches = domain.search(title)
            for d, ev in matches:
                if date and d != date:
                    continue
                return ev.id
        return None

    def _run(self, action: str, date: str | None = None, keyword: str | None = None,
             title: str | None = None, time: str | None = None, attendees: list[str] | None = None,
             duration: int = 60, event_id: str | None = None, updates: dict | None = None) -> str:
        from src.domains.calendar import get_calendar_domain
        from src.core.context import get_channel, get_session_id

        domain = get_calendar_domain()
        if not domain:
            return "日历服务未就绪，请稍后重试。"

        if action == "list":
            if not date:
                return "请提供要查询的日期（YYYY-MM-DD）。"
            events = domain.list_events(date)
            if not events:
                return f"{date} 没有日程安排。"
            return "\n".join(
                f"- [{ev.id}] {ev.time} {ev.title} ({ev.duration}分钟)"
                for ev in sorted(events, key=lambda e: e.time)
            )

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            matches = domain.search(keyword)
            if not matches:
                return f"没有找到包含「{keyword}」的日程。"
            return "\n".join(f"- [{ev.id}] {d} {ev.time} {ev.title}" for d, ev in matches)

        elif action == "create":
            if not title or not date:
                return "创建日程需要提供标题和日期。"
            ev = domain.create_event(
                date=date, title=title, time=time or "09:00",
                duration=duration, attendees=attendees or [],
                channel=get_channel() or "admin",
                session_id=get_session_id() or "",
            )
            return f"已添加日程：{date} {ev.time} {title}"

        elif action == "update":
            if not updates:
                updates = {}
                if time:
                    updates["time"] = time
                if not updates:
                    return "修改日程需要提供要修改的字段。请在 updates 中指定要修改的内容，例如 {\"time\": \"15:00\"}"

            resolved_id = self._resolve_event_id(domain, event_id, title, date)
            if not resolved_id:
                return f"未找到日程：{event_id or f'{date} {title}'}"

            result = domain.update_event(resolved_id, updates, date=date)
            if result:
                return f"已更新日程：{result.title}"
            return f"未找到日程：{resolved_id}"

        elif action == "delete":
            resolved_id = self._resolve_event_id(domain, event_id, title, date)
            if not resolved_id:
                return f"未找到日程：{event_id or f'{date} {title}'}"

            if domain.delete_event(resolved_id):
                return f"已删除日程：{resolved_id}"
            return f"未找到日程：{resolved_id}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
