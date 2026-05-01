"""Session Manager — multi-session support with persistence."""

import json
import threading
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage
from src.memory.store import MemoryManager
from src.memory.compressor import ConversationCompressor
from src.config import DATA_DIR


@dataclass
class Session:
    session_id: str
    name: str
    memory: MemoryManager
    compressor: ConversationCompressor
    created_at: str
    last_active: str
    metadata: dict = field(default_factory=dict)  # {message_count, summary, source_channel}

    def to_dict(self) -> dict:
        """Serialize for persistence. Only clean conversation messages (human + ai without tool_calls)."""
        all_messages = self.memory.get_history()
        # Only keep clean conversation messages — no ToolMessage, no AIMessage with tool_calls
        clean = [m for m in all_messages
                 if m.type in ("human", "ai")
                 and not (hasattr(m, "tool_calls") and m.tool_calls)]
        if clean:
            _, recent = self.compressor.process(list(clean))
        else:
            recent = []

        serialized = []
        for m in recent:
            msg_dict = {"type": m.type, "content": m.content if hasattr(m, "content") else ""}
            if hasattr(m, "tool_calls") and m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            elif hasattr(m, "tool_call_id") and m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            serialized.append(msg_dict)

        return {
            "id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "message_count": self.metadata.get("message_count", 0),
            "messages": serialized,
            "summary": self.compressor.summary,
            "summary_tokens": self.compressor._summary_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Restore from persisted dict."""
        memory = MemoryManager()
        restored_messages = []
        for m in data.get("messages", []):
            msg_type = m["type"]
            content = m.get("content", "")
            if msg_type == "human":
                restored_messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                kwargs = {}
                if m.get("tool_calls"):
                    kwargs["tool_calls"] = m["tool_calls"]
                restored_messages.append(AIMessage(content=content, **kwargs))
        memory._messages = restored_messages

        compressor = ConversationCompressor()
        compressor.summary = data.get("summary", "")
        compressor._summary_tokens = data.get("summary_tokens", 0)

        return cls(
            session_id=data["id"],
            name=data["name"],
            memory=memory,
            compressor=compressor,
            created_at=data.get("created_at", ""),
            last_active=data.get("last_active", ""),
            metadata={"message_count": data.get("message_count", 0)},
        )


class SessionManager:
    PERSIST_FILE = DATA_DIR / "sessions.json"

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._active_id: str | None = None
        self._load()

    @property
    def active_session(self) -> Session:
        return self._sessions[self._active_id]

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def create(self, name: str | None = None, source_channel: str = "") -> Session:
        sid = f"sess_{uuid.uuid4().hex[:8]}"
        session = Session(
            session_id=sid,
            name=name or f"对话 {len(self._sessions) + 1}",
            memory=MemoryManager(),
            compressor=ConversationCompressor(),
            created_at=datetime.now(timezone.utc).isoformat(),
            last_active=datetime.now(timezone.utc).isoformat(),
            metadata={"message_count": 0, "source_channel": source_channel},
        )
        self._sessions[sid] = session
        self._active_id = sid
        self.save()
        return session

    def switch(self, session_id: str) -> Session | None:
        """Switch to a session. Supports ID prefix matching and name matching."""
        # Exact match
        if session_id in self._sessions:
            self._active_id = session_id
            self._touch()
            return self._sessions[session_id]

        # Prefix match
        matches = [s for sid, s in self._sessions.items() if sid.startswith(session_id)]
        if len(matches) == 1:
            self._active_id = matches[0].session_id
            self._touch()
            return matches[0]

        # Name match (contains)
        name_matches = [s for s in self._sessions.values() if session_id.lower() in s.name.lower()]
        if len(name_matches) == 1:
            self._active_id = name_matches[0].session_id
            self._touch()
            return name_matches[0]

        return None

    def list_sessions(self) -> list[Session]:
        return sorted(self._sessions.values(), key=lambda s: s.last_active, reverse=True)

    def rename(self, session_id: str, name: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._sessions[session_id].name = name
        self.save()
        return True

    def delete(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        if len(self._sessions) <= 1:
            return False
        del self._sessions[session_id]
        if self._active_id == session_id:
            self._active_id = next(iter(self._sessions))
        self.save()
        return True

    def reset_active(self):
        self.active_session.memory._messages.clear()
        self.active_session.compressor.summary = ""
        self.active_session.compressor._summary_tokens = 0
        self.active_session.metadata["message_count"] = 0
        self.save()

    def record_message(self, user_msg: str, assistant_msg: str):
        """Called after each agent interaction to update metadata."""
        session = self.active_session
        session.metadata["message_count"] = session.metadata.get("message_count", 0) + 2
        session.last_active = datetime.now(timezone.utc).isoformat()
        self.save()

    def save(self):
        data = {
            "active_session": self._active_id,
            "sessions": [s.to_dict() for s in self._sessions.values()],
        }
        self.PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.PERSIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if not self.PERSIST_FILE.exists():
            # First run — create default session
            self.create(name="默认", source_channel="system")
            return

        with open(self.PERSIST_FILE, encoding="utf-8") as f:
            data = json.load(f)

        for sdata in data.get("sessions", []):
            session = Session.from_dict(sdata)
            self._sessions[session.session_id] = session

        active = data.get("active_session")
        if active and active in self._sessions:
            self._active_id = active
        elif self._sessions:
            self._active_id = next(iter(self._sessions))

        # Ensure at least one session
        if not self._sessions:
            self.create(name="默认", source_channel="system")

    def _touch(self):
        """Update last_active on the active session."""
        self.active_session.last_active = datetime.now(timezone.utc).isoformat()
        self.save()


# Global singleton
_session_manager: SessionManager | None = None
_session_lock = threading.Lock()


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        with _session_lock:
            if _session_manager is None:
                _session_manager = SessionManager()
    return _session_manager
