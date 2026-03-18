import json
import uuid
from langchain_core.tools import BaseTool
from pathlib import Path


class GoogleCalendarTool(BaseTool):
    name: str = "calendar"
    description: str = (
        "Manage calendar events. Commands: list <date YYYY-MM-DD>, "
        "create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}, "
        "search <keyword>, update <id> <json>, delete <id>"
    )
    data_file: str = ""
    use_mock: bool = True

    def _run(self, command: str) -> str:
        from src.data_layer.loader import load_json, save_json

        path = Path(self.data_file)
        data = load_json(path) if isinstance(load_json(path), list) else []
        cmd = command.strip().lower()

        if cmd.startswith("list"):
            date_str = command.split("list", 1)[1].strip()
            for day in data:
                if day.get("date") == date_str:
                    events = day.get("events", [])
                    if not events:
                        return f"{date_str} 没有日程安排。"
                    return "\n".join(
                        f"- {ev['time']} {ev['title']} ({ev.get('duration', 60)}分钟) [ID: {ev['id']}]"
                        for ev in sorted(events, key=lambda e: e.get("time", ""))
                    )
            return f"{date_str} 没有日程安排。"

        elif cmd.startswith("create"):
            try:
                new_event = json.loads(command.split("create", 1)[1].strip())
            except (json.JSONDecodeError, IndexError):
                return "创建日程需要 JSON：create {\"date\":\"...\",\"time\":\"...\",\"title\":\"...\"}"
            new_event["id"] = f"evt-{uuid.uuid4().hex[:8]}"
            new_event.setdefault("duration", 60)
            new_event.setdefault("attendees", [])
            date_str = new_event.pop("date")

            for day in data:
                if day.get("date") == date_str:
                    day.setdefault("events", []).append(new_event)
                    save_json(path, data)
                    return f"已添加日程：{date_str} {new_event.get('time','')} {new_event['title']} [ID: {new_event['id']}]"
            data.append({"date": date_str, "events": [new_event]})
            save_json(path, data)
            return f"已添加日程：{date_str} {new_event.get('time','')} {new_event['title']} [ID: {new_event['id']}]"

        elif cmd.startswith("search"):
            keyword = cmd.replace("search", "").strip()
            matches = []
            for day in data:
                for ev in day.get("events", []):
                    if keyword.lower() in ev.get("title", "").lower():
                        matches.append((day["date"], ev))
            if not matches:
                return f"没有找到包含「{keyword}」的日程。"
            return "\n".join(
                f"- {date}: {ev['time']} {ev['title']} [ID: {ev['id']}]"
                for date, ev in matches
            )

        elif cmd.startswith("update"):
            parts = command.split(None, 2)
            if len(parts) < 3:
                return "用法: update <event_id> {\"date\":\"...\",\"time\":\"...\"}"
            event_id, json_data = parts[1], parts[2]
            try:
                updates = json.loads(json_data)
            except json.JSONDecodeError:
                return "更新数据需要 JSON 格式"
            for day in data:
                for ev in day.get("events", []):
                    if ev["id"] == event_id:
                        ev.update(updates)
                        save_json(path, data)
                        return f"已更新日程：{ev.get('title', event_id)}"
            return f"未找到日程 ID: {event_id}"

        elif cmd.startswith("delete"):
            event_id = cmd.replace("delete", "").strip()
            for day in data:
                events = day.get("events", [])
                for i, ev in enumerate(events):
                    if ev["id"] == event_id:
                        title = ev["title"]
                        events.pop(i)
                        save_json(path, data)
                        return f"已删除日程：{title}"
            return f"未找到日程 ID: {event_id}"

        return "可用命令：list <date>, create <json>, search <keyword>, update <id> <json>, delete <id>"

    async def _arun(self, command: str) -> str:
        return self._run(command)
