"""CalendarEvent — 日程事件数据模型。"""

from dataclasses import dataclass, field


@dataclass
class CalendarEvent:
    id: str                              # "evt-{uuid8}"
    title: str
    time: str                            # "HH:MM"
    duration: int                        # 分钟
    attendees: list[str] = field(default_factory=list)
    date: str = ""                       # "YYYY-MM-DD" — 所属日期

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "time": self.time,
            "duration": self.duration,
            "attendees": self.attendees,
        }

    @classmethod
    def from_dict(cls, data: dict, date: str = "") -> "CalendarEvent":
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            time=data.get("time", "09:00"),
            duration=data.get("duration", 60),
            attendees=data.get("attendees", []),
            date=date or data.get("date", ""),
        )
