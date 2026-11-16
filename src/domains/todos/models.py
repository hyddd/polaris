"""TodoItem — 待办事项数据模型。"""

from dataclasses import dataclass, field


@dataclass
class TodoItem:
    id: str                    # "todo-{uuid8}"
    title: str                 # 标题
    priority: str              # "high" / "medium" / "low"
    status: str                # "pending" / "in_progress" / "done"
    due: str                   # "YYYY-MM-DD" 或 ""
    tags: list[str] = field(default_factory=list)
    scope: str = "private"     # "public"（公共库）/ "private"（本机文件）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "status": self.status,
            "due": self.due,
            "tags": self.tags,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        return cls(
            id=data["id"],
            title=data.get("title", ""),
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            due=data.get("due", ""),
            tags=data.get("tags", []),
            scope=data.get("scope", "private"),
        )
