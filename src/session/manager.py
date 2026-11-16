"""Session Manager — multi-session support with persistence."""

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.core.memory import MemoryManager
from src.core.storage import _atomic_write
from src.session.compressor import ConversationCompressor
from src.core.config import config

logger = logging.getLogger("polaris.session")

# sessions_dir from config is the sessions storage directory (e.g. "data/sessions")
SESSIONS_DIR = config.resolve_path(config.get("storage.sessions_dir", "data/sessions"))
ACTIVE_FILE = SESSIONS_DIR / "active.json"
DATA_DIR = SESSIONS_DIR.parent  # data root for old-format migration


@dataclass
class Session:
    session_id: str
    name: str
    memory: MemoryManager
    compressor: ConversationCompressor
    created_at: str
    last_active: str
    metadata: dict = field(default_factory=dict)  # {message_count, summary, source_channel}
    persona: dict = field(default_factory=lambda: {
        "name": "", "call_user": "", "identity": "",
        "personality": "", "timezone": "Asia/Shanghai", "notes": "",
    })
    pending_action: dict | None = None
    cache_stats: dict = field(default_factory=lambda: {"hit": 0, "miss": 0, "calls": 0})

    def get_message(self, message_id: str):
        """Get a message by ID from memory."""
        return self.memory.get_message_by_id(message_id)

    def update_message(self, message_id: str, new_content: str) -> bool:
        """Update a message's content by ID."""
        return self.memory.update_message(message_id, new_content)

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        all_messages = self.memory.get_history()

        # Serialize what's in memory (already compacted if needed)
        serialized = []
        for m in all_messages:
            msg_dict = {"type": m.type, "content": m.content if hasattr(m, "content") else ""}
            if hasattr(m, "tool_calls") and m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            if hasattr(m, "tool_call_id") and m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if hasattr(m, "tool_calls") and m.tool_calls:
                rc = getattr(m, "additional_kwargs", {}).get("reasoning_content")
                if rc:
                    msg_dict["reasoning_content"] = rc
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
            "persona": self.persona,
            "pending_action": self.pending_action,
            "cache_stats": self.cache_stats,
        }

    @staticmethod
    def _parse_persona(raw) -> dict:
        """Normalize persona from persisted data. Handles old string and old dict formats."""
        default = {"name": "", "call_user": "", "identity": "", "personality": "", "timezone": "Asia/Shanghai", "notes": ""}
        if isinstance(raw, str):
            if raw.strip():
                default["notes"] = raw.strip()
            return default
        if isinstance(raw, dict):
            # New format — pass through with defaults for missing keys
            if "notes" in raw or "call_user" in raw or "identity" in raw:
                for k in default:
                    if k not in raw:
                        raw[k] = default[k]
                return raw
            # Old format (role/traits/style/language/extra) — migrate into notes
            notes_parts = []
            if raw.get("role"):
                notes_parts.append(f"角色：{raw['role']}")
            if raw.get("traits"):
                notes_parts.append(f"性格：{'、'.join(raw['traits'])}")
            if raw.get("style"):
                notes_parts.append(f"沟通风格：{raw['style']}")
            if raw.get("language") and raw["language"] != "中文":
                notes_parts.append(f"语言：{raw['language']}")
            if raw.get("extra"):
                notes_parts.append(raw["extra"])
            default["name"] = raw.get("name", "")
            default["notes"] = "\n".join(notes_parts)
            return default
        return default

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
                if m.get("reasoning_content"):
                    kwargs["additional_kwargs"] = {"reasoning_content": m["reasoning_content"]}
                restored_messages.append(AIMessage(content=content, **kwargs))
            elif msg_type == "tool":
                restored_messages.append(ToolMessage(
                    content=content,
                    tool_call_id=m.get("tool_call_id", ""),
                ))
        memory.set_messages(restored_messages)

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
            persona=Session._parse_persona(data.get("persona", {})),
            pending_action=data.get("pending_action"),
            cache_stats=data.get("cache_stats", {"hit": 0, "miss": 0, "calls": 0}),
        )


class SessionManager:

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._active_ids: dict[str, str] = {}  # channel -> session_id
        # 会话文件会被多个线程同时写（主事件循环、QQ/飞书线程、提醒线程），写盘串行化
        self._io_lock = threading.RLock()
        self._load()

    def active_session(self, channel: str = "default") -> Session:
        sid = self._active_ids.get(channel)
        if sid and sid in self._sessions:
            return self._sessions[sid]
        # Fallback to first session
        if self._sessions:
            sid = next(iter(self._sessions))
            self._active_ids[channel] = sid
            return self._sessions[sid]
        raise RuntimeError("No sessions available")

    def resolve_session(self, channel: str = "default") -> tuple[Session, bool]:
        """返回 (session, is_switched)。is_switched=True 表示原会话已失效，自动切到 default。"""
        sid = self._active_ids.get(channel)
        if sid and sid in self._sessions:
            return self._sessions[sid], False

        # 原会话已失效，切到 default
        default = self._ensure_default_session()
        self._active_ids[channel] = default.session_id
        self.save()
        return default, True

    def _ensure_default_session(self) -> Session:
        """确保 default 会话存在，不存在则创建。"""
        for s in self._sessions.values():
            if s.name == "default":
                return s
        # 不存在，创建
        return self.create(name="default")

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def create(self, name: str | None = None, source_channel: str = "") -> Session:
        from src.core.config import config
        max_sessions = config.get("server.max_sessions", 100)
        if len(self._sessions) >= max_sessions:
            raise RuntimeError(
                f"会话数已达上限（{max_sessions}），请先删除旧会话。"
                f"输入 /sessions 查看所有会话。"
            )
        # 重名检查
        if name:
            for s in self._sessions.values():
                if s.name == name:
                    raise RuntimeError(f"已存在同名会话「{name}」，请使用其他名称。")
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
        # Set as active for the source channel
        if source_channel:
            self._active_ids[source_channel] = sid
        self.save()
        return session

    def switch(self, session_id: str, channel: str = "default") -> Session | None:
        """Switch to a session. Supports ID prefix matching and name matching."""
        # Exact match
        if session_id in self._sessions:
            self._active_ids[channel] = session_id
            self._touch(channel)
            return self._sessions[session_id]

        # Prefix match
        matches = [s for sid, s in self._sessions.items() if sid.startswith(session_id)]
        if len(matches) == 1:
            self._active_ids[channel] = matches[0].session_id
            self._touch(channel)
            return matches[0]

        # Name match (contains)
        name_matches = [s for s in self._sessions.values() if session_id.lower() in s.name.lower()]
        if len(name_matches) == 1:
            self._active_ids[channel] = name_matches[0].session_id
            self._touch(channel)
            return name_matches[0]

        return None

    def list_sessions(self) -> list[Session]:
        return sorted(self._sessions.values(), key=lambda s: s.last_active, reverse=True)

    def rename(self, session_id: str, name: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._sessions[session_id].name = name
        self.save_session(session_id)
        return True

    def delete(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        if self._sessions[session_id].name == "default":
            return False
        if len(self._sessions) <= 1:
            return False
        del self._sessions[session_id]
        # Delete session file（连同原子写入留下的备份，否则"已删除"的内容还留在磁盘上）
        path = SESSIONS_DIR / f"{session_id}.json"
        with self._io_lock:
            path.unlink(missing_ok=True)
            path.with_suffix(".json.bak").unlink(missing_ok=True)
        self._save_active()
        return True

    def reset_active(self, channel: str = "default"):
        session = self.active_session(channel)
        session.memory.clear_messages()
        session.compressor.summary = ""
        session.compressor._summary_tokens = 0
        session.metadata["message_count"] = 0
        session.cache_stats = {"hit": 0, "miss": 0, "calls": 0}
        self.save_session(session.session_id)

    def record_message(self, user_msg: str, assistant_msg: str, channel: str = "default",
                       session_id: str | None = None):
        """Called after each agent interaction to update metadata.

        传 session_id 时记到这个会话上；不传才退回到 channel 当前激活的会话。
        一轮对话跑的过程中 channel 的激活会话可能被切走，按激活会话记会记错。
        """
        session = self._sessions.get(session_id) if session_id else None
        if session is None:
            session = self.active_session(channel)
        session.metadata["message_count"] = session.metadata.get("message_count", 0) + 2
        session.last_active = datetime.now(timezone.utc).isoformat()
        self.save_session(session.session_id)

    def save_session(self, session_id: str) -> None:
        """Save a single session to disk (atomic: temp file + rename, keeps .bak)."""
        with self._io_lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            # 先完整序列化再落盘：序列化失败不会留下半截文件
            content = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
            _atomic_write(SESSIONS_DIR / f"{session_id}.json", content)

    def save(self):
        """Save all sessions to disk."""
        with self._io_lock:
            for sid in list(self._sessions):
                self.save_session(sid)
            self._save_active()

    def _save_active(self) -> None:
        """Save active session IDs per channel."""
        with self._io_lock:
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            _atomic_write(ACTIVE_FILE, json.dumps(self._active_ids, ensure_ascii=False, indent=2))

    def _load_session_file(self, path: Path) -> tuple[Session | None, bool]:
        """读一个会话文件。返回 (session, 是否从备份恢复)。

        主文件坏了就试 .bak（原子写入保留的上一版）；都坏了返回 None。
        坏文件改名成 *.corrupt-<时间> 留在原目录供人工恢复，不删除、也不会被后续写入覆盖。
        """
        try:
            return Session.from_dict(json.loads(path.read_text(encoding="utf-8"))), False
        except Exception as e:
            logger.error(f"会话文件损坏，无法解析: {path.name} ({e})")

        backup = path.with_suffix(".json.bak")
        session = None
        if backup.exists():
            try:
                session = Session.from_dict(json.loads(backup.read_text(encoding="utf-8")))
                logger.warning(f"已从备份恢复会话 {session.session_id}，备份之后的最后一次写入丢失")
            except Exception as e:
                logger.error(f"会话备份同样无法解析: {backup.name} ({e})")

        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        quarantined = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            path.rename(quarantined)
            logger.error(f"损坏的会话文件已保留为 {quarantined.name}")
        except OSError as e:
            logger.error(f"无法隔离损坏的会话文件 {path.name}: {e}")
        return session, session is not None

    def _load(self):
        if not SESSIONS_DIR.exists():
            # Migrate from old format or create default
            old_file = DATA_DIR / "sessions.json"
            if old_file.exists():
                self._migrate_from_old(old_file)
            else:
                self.create(name="default", source_channel="system")
            return

        # Load active session IDs (per-channel or legacy single)
        if ACTIVE_FILE.exists():
            try:
                content = ACTIVE_FILE.read_text(encoding="utf-8").strip()
                if content.startswith("{"):
                    self._active_ids = json.loads(content)
                else:
                    # Legacy format: single session ID
                    self._active_ids = {"default": content}
            except Exception as e:
                logger.error(f"激活会话映射文件损坏，各渠道将回到默认会话: {e}")
                self._active_ids = {}

        # Load all session files
        recovered = []
        for path in SESSIONS_DIR.glob("sess_*.json"):
            session, from_backup = self._load_session_file(path)
            if session is None:
                continue
            self._sessions[session.session_id] = session
            if from_backup:
                recovered.append(session.session_id)
        # 主文件已被隔离，立刻用恢复出的内容重写，否则下次启动只剩 .bak 会被漏读
        for sid in recovered:
            self.save_session(sid)

        # Validate active sessions exist
        for ch, sid in list(self._active_ids.items()):
            if sid not in self._sessions:
                self._active_ids[ch] = next(iter(self._sessions)) if self._sessions else ""

        # Ensure at least one session
        if not self._sessions:
            self.create(name="default", source_channel="system")

        # 确保 default 会话存在
        self._ensure_default_session()

    def _migrate_from_old(self, old_file: Path):
        """Migrate from single sessions.json to individual files."""
        try:
            with open(old_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            self.create(name="默认", source_channel="system")
            return

        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        for sdata in data.get("sessions", []):
            session = Session.from_dict(sdata)
            self._sessions[session.session_id] = session
            path = SESSIONS_DIR / f"{session.session_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sdata, f, ensure_ascii=False, indent=2)

        active = data.get("active_session")
        if active and active in self._sessions:
            self._active_ids["default"] = active
        elif self._sessions:
            self._active_ids["default"] = next(iter(self._sessions))

        if self._active_ids:
            ACTIVE_FILE.write_text(
                json.dumps(self._active_ids, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        # Rename old file as backup
        old_file.rename(old_file.with_suffix(".json.bak"))

    def _touch(self, channel: str = "default"):
        """Update last_active on the active session.

        只写这一个会话和激活映射。以前这里调 save() 重写全部会话文件，
        每次切换会话都会和其他线程正在写的会话文件撞车。
        """
        session = self.active_session(channel)
        session.last_active = datetime.now(timezone.utc).isoformat()
        self.save_session(session.session_id)
        self._save_active()


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
