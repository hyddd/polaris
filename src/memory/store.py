from langchain_core.messages import BaseMessage
from pathlib import Path
from typing import Optional


class MemoryManager:
    def __init__(self, profile_path: Optional[str] = None):
        self._messages: list[BaseMessage] = []
        self.profile_path = Path(profile_path) if profile_path else None
        self._profile: dict = {}

    def add_message(self, message: BaseMessage) -> None:
        self._messages.append(message)

    def get_history(self) -> list[BaseMessage]:
        return list(self._messages)

    def get_profile(self) -> dict:
        if not self._profile and self.profile_path and self.profile_path.exists():
            import json
            self._profile = json.loads(self.profile_path.read_text(encoding="utf-8"))
        return self._profile

    def update_profile(self, updates: dict) -> None:
        self._profile.update(updates)
        if self.profile_path:
            import json
            self.profile_path.write_text(json.dumps(self._profile, ensure_ascii=False, indent=2), encoding="utf-8")

    def format_history_as_string(self) -> str:
        lines = []
        for msg in self.get_history():
            role = "用户" if msg.type == "human" else "助手"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)
