import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class RepeatRule(str, Enum):
    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ReminderStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class Reminder:
    id: str = field(default_factory=lambda: f"rmd-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    trigger_time: datetime = field(default_factory=datetime.now)
    repeat_rule: RepeatRule = RepeatRule.NONE
    event_id: str | None = None
    channel: str = ""
    session_id: str = ""
    user_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: ReminderStatus = ReminderStatus.ACTIVE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "trigger_time": self.trigger_time.isoformat(),
            "repeat_rule": self.repeat_rule.value,
            "event_id": self.event_id,
            "channel": self.channel,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Reminder":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            trigger_time=datetime.fromisoformat(data["trigger_time"]),
            repeat_rule=RepeatRule(data.get("repeat_rule", "none")),
            event_id=data.get("event_id"),
            channel=data.get("channel", ""),
            session_id=data.get("session_id", ""),
            user_id=data.get("user_id", ""),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            status=ReminderStatus(data.get("status", "active")),
        )
