"""ScheduledJob — 调度任务数据模型。"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScheduledJob:
    id: str                          # 唯一标识，如 "reminder:xxx" 或 "heartbeat"
    name: str                        # 人类可读名称
    trigger_type: str                # "cron" / "interval" / "date"
    trigger_kwargs: dict             # cron: {hour, minute, day_of_week}; interval: {seconds}; date: {run_date} (ISO格式字符串)
    handler_type: str                # "reminder" / "heartbeat" / "workflow" / "daily" / "custom"
    handler_kwargs: dict             # 传给 handler 的参数
    enabled: bool = True
    created_at: str = ""             # ISO格式
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "trigger_type": self.trigger_type,
            "trigger_kwargs": self.trigger_kwargs,
            "handler_type": self.handler_type,
            "handler_kwargs": self.handler_kwargs,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledJob":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            trigger_type=data["trigger_type"],
            trigger_kwargs=data.get("trigger_kwargs", {}),
            handler_type=data["handler_type"],
            handler_kwargs=data.get("handler_kwargs", {}),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", ""),
            last_run=data.get("last_run"),
            next_run=data.get("next_run"),
            run_count=data.get("run_count", 0),
        )
