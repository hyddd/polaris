"""Application configuration — loaded from YAML files.

Default: data/config.yaml (tracked in git)
Override: data/config.local.yaml (gitignored, for local secrets)

Usage:
    from src.config import config

    model = config.get("llm.model", "gpt-4o")
    path = config.resolve_path(config.get("storage.calendar_file", "data/calendar.json"))
"""

import warnings
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_CONFIG_FILE = PROJECT_ROOT / "data/config.yaml"
_LOCAL_CONFIG_FILE = PROJECT_ROOT / "data/config.local.yaml"

# ---------------------------------------------------------------------------
# Backward compatibility migration map: old name -> (config key, default)
# ---------------------------------------------------------------------------
_MIGRATION_MAP: dict[str, tuple[str, object]] = {
    "LLM_MODEL": ("llm.model", "gpt-4o"),
    "LLM_API_KEY": ("llm.api_key", ""),
    "LLM_BASE_URL": ("llm.base_url", "https://api.openai.com/v1"),
    "ADMIN_TOKEN": ("server.admin_token", ""),
    "CHAT_TOKEN": ("server.chat_token", ""),
    "RATE_LIMIT_MAX_REQUESTS": ("server.rate_limit_max_requests", 30),
    "RATE_LIMIT_WINDOW_SECONDS": ("server.rate_limit_window_seconds", 60),
    "SEARCH_API_KEY": ("tools.web_search.api_key", ""),
    "SEARCH_API_BASE": ("tools.web_search.api_base", "https://api.tavily.com"),
    "CALENDAR_USE_MOCK": ("tools.calendar.use_mock", False),
    "GCAL_CREDENTIALS": ("tools.calendar.google_credentials", ""),
    "GCAL_ID": ("tools.calendar.google_calendar_id", "primary"),
    "EMBEDDING_API_KEY": ("embedding.api_key", ""),
    "EMBEDDING_BASE_URL": ("embedding.base_url", ""),
    "EMBEDDING_MODEL": ("embedding.model", "netease-youdao/bce-embedding-base_v1"),
    "FEISHU_APP_ID": ("channels.feishu.app_id", ""),
    "FEISHU_APP_SECRET": ("channels.feishu.app_secret", ""),
    "QQ_BOT_APPID": ("channels.qq.bot_appid", ""),
    "QQ_BOT_SECRET": ("channels.qq.bot_secret", ""),
    "DATA_DIR": ("storage.sessions_dir", "data"),
    "CHROMA_PERSIST_DIR": ("storage.vector_db_dir", "data/chroma"),
    "NOTES_DIR": ("storage.notes_dir", "data/notes"),
    "ARCHIVE_DIR": ("storage.notes_dir", "data/notes"),
    "CALENDAR_FILE": ("storage.calendar_file", "data/calendar.json"),
    "TODOS_FILE": ("storage.todos_file", "data/todos.json"),
    "REMINDERS_FILE": ("storage.reminders_file", "data/reminders.json"),
    "PROFILE_FILE": ("storage.profile_file", "data/user_profile.json"),
}

# Old module-level variables that returned resolved Path objects
_PATH_VARS: set[str] = {
    "DATA_DIR",
    "NOTES_DIR",
    "ARCHIVE_DIR",
    "CALENDAR_FILE",
    "TODOS_FILE",
    "REMINDERS_FILE",
    "PROFILE_FILE",
    "CHROMA_PERSIST_DIR",
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base dict."""
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def _load_yaml_config() -> dict:
    """Load config from YAML files (default + local override)."""
    config = {}
    if _CONFIG_FILE.exists():
        with open(_CONFIG_FILE) as f:
            config = yaml.safe_load(f) or {}
    if _LOCAL_CONFIG_FILE.exists():
        with open(_LOCAL_CONFIG_FILE) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    return config


class Config:
    """Configuration manager — loads from YAML, supports dot-separated access."""

    def __init__(self):
        self._data: dict = {}
        self._local_path = _LOCAL_CONFIG_FILE

    def load(self) -> None:
        """Load (or reload) configuration from YAML files."""
        self._data = _load_yaml_config()

    def get(self, key: str, default=None):
        """Get a value from config using dot-separated key path."""
        keys = key.split(".")
        val = self._data
        for k in keys:
            if not isinstance(val, dict) or k not in val:
                return default
            val = val[k]
        return val

    def resolve_path(self, val: str) -> Path:
        """Resolve a possibly-relative path against PROJECT_ROOT."""
        p = Path(val)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p

    def reload(self) -> dict:
        """Re-read YAML config files, publish config:reload event.

        Returns the full config snapshot dict.
        """
        self.load()
        from src.events import event_bus
        event_bus.publish("config:reload")
        return dict(self._data)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
config = Config()
config.load()


# ---------------------------------------------------------------------------
# Module-level convenience wrappers (compatible with old import style)
# ---------------------------------------------------------------------------
def reload() -> dict:
    """Reload config (module-level wrapper for config.reload)."""
    return config.reload()


# ---------------------------------------------------------------------------
# Backward compatibility: module-level __getattr__ for old-style imports
# ---------------------------------------------------------------------------
def __getattr__(name):
    """Provide deprecated access to old module-level config variables.

    Triggers DeprecationWarning on first access.
    """
    if name == "_MIGRATION_MAP":
        raise AttributeError(name)

    entry = _MIGRATION_MAP.get(name)
    if entry is not None:
        key, default = entry
        warnings.warn(
            f"'{name}' is deprecated, use config.get({key!r}) instead",
            DeprecationWarning,
            stacklevel=2,
        )
        value = config.get(key, default)

        if name == "ARCHIVE_DIR":
            # ARCHIVE_DIR was NOTES_DIR / "archive"
            notes_dir = config.resolve_path(
                config.get("storage.notes_dir", "data/notes")
            )
            return notes_dir / "archive"

        if name in _PATH_VARS:
            return config.resolve_path(value) if isinstance(value, str) else value

        return value

    if name in ("_PATH_VARS", "_CONFIG_FILE", "_LOCAL_CONFIG_FILE", "Config",
                "_deep_merge", "_load_yaml_config", "config", "reload",
                "PROJECT_ROOT", "_get", "_resolve_path"):
        raise AttributeError(name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
