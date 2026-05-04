"""Persona — 会话人设数据模型。"""

from dataclasses import dataclass


@dataclass
class Persona:
    """会话人设。"""
    name: str = ""           # 助手名称
    call_user: str = ""      # 称呼用户
    identity: str = ""       # 身份设定
    personality: str = ""    # 性格特点
    timezone: str = "Asia/Shanghai"
    notes: str = ""          # 备注

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "call_user": self.call_user,
            "identity": self.identity,
            "personality": self.personality,
            "timezone": self.timezone,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Persona":
        return cls(
            name=data.get("name", ""),
            call_user=data.get("call_user", ""),
            identity=data.get("identity", ""),
            personality=data.get("personality", ""),
            timezone=data.get("timezone", "Asia/Shanghai"),
            notes=data.get("notes", ""),
        )

    def update(self, updates: dict) -> None:
        """部分更新人设字段。"""
        for key in ("name", "call_user", "identity", "personality", "timezone", "notes"):
            if key in updates and updates[key] is not None:
                setattr(self, key, str(updates[key]).strip())

    def to_text(self) -> str:
        """格式化为可读文本。"""
        parts = []
        if self.name:
            parts.append(f"名称：{self.name}")
        if self.call_user:
            parts.append(f"称呼用户：{self.call_user}")
        if self.identity:
            parts.append(f"身份：{self.identity}")
        if self.personality:
            parts.append(f"性格：{self.personality}")
        if self.timezone and self.timezone != "Asia/Shanghai":
            parts.append(f"时区：{self.timezone}")
        if self.notes:
            parts.append(f"备注：{self.notes}")
        return "\n".join(parts) if parts else ""
