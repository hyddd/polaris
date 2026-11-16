import threading
import uuid
from langchain_core.messages import BaseMessage
from pathlib import Path
from typing import Optional


class MemoryManager:
    def __init__(self, profile_path: Optional[str] = None):
        self._messages: list[BaseMessage] = []
        self._message_ids: dict[str, int] = {}  # message_id -> index
        self.profile_path = Path(profile_path) if profile_path else None
        self._profile: dict = {}
        # 提醒推送在 APScheduler 线程里追加消息，与对话线程并发；读改写必须互斥
        self._lock = threading.RLock()

    def add_message(self, message: BaseMessage, message_id: str | None = None) -> str:
        """Add a message and return its ID."""
        mid = message_id or f"msg_{uuid.uuid4().hex[:12]}"
        # Store ID as metadata on the message
        if not hasattr(message, '_polaris_id'):
            message._polaris_id = mid
        with self._lock:
            self._message_ids[mid] = len(self._messages)
            self._messages.append(message)
        return mid

    def get_message_by_id(self, message_id: str) -> BaseMessage | None:
        """Get a message by its ID."""
        idx = self._message_ids.get(message_id)
        if idx is not None and idx < len(self._messages):
            return self._messages[idx]
        return None

    def get_message_id(self, message: BaseMessage) -> str | None:
        """Get the ID of a message."""
        return getattr(message, '_polaris_id', None)

    def update_message(self, message_id: str, new_content: str) -> bool:
        """Update the content of a message by ID. Returns True if found."""
        idx = self._message_ids.get(message_id)
        if idx is not None and idx < len(self._messages):
            msg = self._messages[idx]
            # Create a new message with updated content
            msg.__class__ = msg.__class__
            msg.content = new_content
            return True
        return False

    def get_messages(self) -> list[BaseMessage]:
        """Return a copy of all messages."""
        with self._lock:
            return list(self._messages)

    # Backward-compatible alias
    get_history = get_messages

    def set_messages(self, messages: list[BaseMessage]) -> None:
        """Replace all messages with the given list."""
        with self._lock:
            self._messages = list(messages)

    def replace_keeping_appended(self, start: int, messages: list[BaseMessage]) -> None:
        """用 messages 替换历史，但保留第 start 条之后由其他写入方追加的消息。

        一轮对话持有会话锁运行期间，提醒推送这类不走会话锁的写入方仍可能往内存追加消息。
        本轮结束时如果直接 set_messages，这些消息会被整体覆盖掉。
        start 是本轮开始时自己写入的最后一条之后的位置（即 len(历史) + 1 条用户消息）。
        """
        with self._lock:
            appended = self._messages[start:]
            self._messages = list(messages) + appended

    def clear_messages(self) -> None:
        """Remove all messages."""
        with self._lock:
            self._messages.clear()

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
