import uuid
from typing import Optional, Literal
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from pathlib import Path


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
    updates: Optional[dict] = Field(default=None, description="update 时要修改的字段")


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
    use_mock: bool = True

    def _run(self, action: str, date: str | None = None, keyword: str | None = None,
             title: str | None = None, time: str | None = None, attendees: list[str] | None = None,
             duration: int = 60, event_id: str | None = None, updates: dict | None = None) -> str:
        from src.data_layer.loader import load_json, save_json

        path = Path(self.data_file)
        raw = load_json(path)
        data = raw if isinstance(raw, list) else []

        if action == "list":
            if not date:
                return "请提供要查询的日期（YYYY-MM-DD）。"
            for day in data:
                if day.get("date") == date:
                    events = day.get("events", [])
                    if not events:
                        return f"{date} 没有日程安排。"
                    return "\n".join(
                        f"- {ev['time']} {ev['title']} ({ev.get('duration', 60)}分钟)"
                        for ev in sorted(events, key=lambda e: e.get("time", ""))
                    )
            return f"{date} 没有日程安排。"

        elif action == "search":
            if not keyword:
                return "请提供搜索关键词。"
            matches = []
            for day in data:
                for ev in day.get("events", []):
                    if keyword.lower() in ev.get("title", "").lower():
                        matches.append((day["date"], ev))
            if not matches:
                return f"没有找到包含「{keyword}」的日程。"
            return "\n".join(f"- {date}: {ev['time']} {ev['title']}" for date, ev in matches)

        elif action == "create":
            if not title or not date:
                return "创建日程需要提供标题和日期。"
            new_event = {
                "id": f"evt-{uuid.uuid4().hex[:8]}",
                "title": title,
                "time": time or "09:00",
                "duration": duration,
                "attendees": attendees or [],
            }
            for day in data:
                if day.get("date") == date:
                    day.setdefault("events", []).append(new_event)
                    save_json(path, data)
                    return f"已添加日程：{date} {new_event['time']} {title}"
            data.append({"date": date, "events": [new_event]})
            save_json(path, data)
            return f"已添加日程：{date} {new_event['time']} {title}"

        elif action == "update":
            if not updates:
                return "修改日程需要提供要修改的字段。"
            new_date = updates.get("date")
            # Find by event_id or title (with optional date filter)
            for day in data:
                if date and day.get("date") != date:
                    continue
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    matched = False
                    if event_id and ev["id"] == event_id:
                        matched = True
                    elif title and title.lower() in ev.get("title", "").lower():
                        matched = True
                    if matched:
                        if new_date and new_date != day.get("date"):
                            # Date changed: move event to new date
                            events.pop(i)
                            ev.update({k: v for k, v in updates.items() if k != "date"})
                            moved = False
                            for d in data:
                                if d.get("date") == new_date:
                                    d.setdefault("events", []).append(ev)
                                    moved = True
                                    break
                            if not moved:
                                data.append({"date": new_date, "events": [ev]})
                        else:
                            ev.update(updates)
                        save_json(path, data)
                        return f"已更新日程：{ev.get('title', event_id)}"
            return f"未找到日程：{event_id or f'{date} {title}'}"

        elif action == "delete":
            # Find by event_id or title (with optional date filter)
            for day in data:
                if date and day.get("date") != date:
                    continue
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    matched = False
                    if event_id and ev["id"] == event_id:
                        matched = True
                    elif title and title.lower() in ev.get("title", "").lower():
                        matched = True
                    if matched:
                        title = ev["title"]
                        events.pop(i)
                        save_json(path, data)
                        return f"已删除日程：{title}"
            return f"未找到日程：{event_id or f'{date} {title}'}"

        return "未知操作。"

    async def _arun(self, **kwargs) -> str:
        return self._run(**kwargs)
