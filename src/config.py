"""Application configuration — loaded from YAML files.

Default: data/config.yaml (tracked in git)
Override: data/config.local.yaml (gitignored, for local secrets)
"""

import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_FILE = PROJECT_ROOT / "data/config.yaml"
LOCAL_CONFIG_FILE = PROJECT_ROOT / "data/config.local.yaml"


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
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = yaml.safe_load(f) or {}
    if LOCAL_CONFIG_FILE.exists():
        with open(LOCAL_CONFIG_FILE) as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    return config


# Module-level cache (loaded once at import time, re-read on reload())
_config = _load_yaml_config()


def _get(key: str, default=None):
    """Get a value from config using dot-separated key path."""
    keys = key.split(".")
    val = _config
    for k in keys:
        if not isinstance(val, dict) or k not in val:
            return default
        val = val[k]
    return val


def _resolve_path(val: str) -> Path:
    """Resolve a possibly-relative path against PROJECT_ROOT."""
    p = Path(val)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


# --- Project paths ---
DATA_DIR = PROJECT_ROOT / "data"

CHROMA_PERSIST_DIR = str(_resolve_path(_get("storage.vector_db_dir", "data/chroma")))
NOTES_DIR = _resolve_path(_get("storage.notes_dir", "data/notes"))
ARCHIVE_DIR = NOTES_DIR / "archive"
CALENDAR_FILE = _resolve_path(_get("storage.calendar_file", "data/calendar.json"))
TODOS_FILE = _resolve_path(_get("storage.todos_file", "data/todos.json"))
REMINDERS_FILE = _resolve_path(_get("storage.reminders_file", "data/reminders.json"))
PROFILE_FILE = _resolve_path(_get("storage.profile_file", "data/user_profile.json"))

# --- LLM ---
LLM_MODEL = _get("llm.model", "gpt-4o")
LLM_API_KEY = _get("llm.api_key", "")
LLM_BASE_URL = _get("llm.base_url", "https://api.openai.com/v1")

# --- Google Calendar ---
GCAL_CREDENTIALS = _get("tools.calendar.google_credentials", "")
GCAL_ID = _get("tools.calendar.google_calendar_id", "primary")

# --- Auth ---
ADMIN_TOKEN = _get("server.admin_token", "")
CHAT_TOKEN = _get("server.chat_token", "")

# --- Rate Limiting ---
RATE_LIMIT_MAX_REQUESTS = _get("server.rate_limit_max_requests", 30)
RATE_LIMIT_WINDOW_SECONDS = _get("server.rate_limit_window_seconds", 60)

# --- Web Search ---
SEARCH_API_KEY = _get("tools.web_search.api_key", "")
SEARCH_API_BASE = _get("tools.web_search.api_base", "https://api.tavily.com")

# --- Calendar tool ---
CALENDAR_USE_MOCK = _get("tools.calendar.use_mock", False)

# --- Embedding ---
EMBEDDING_API_KEY = _get("embedding.api_key", "")
EMBEDDING_BASE_URL = _get("embedding.base_url", "")
EMBEDDING_MODEL = _get("embedding.model", "netease-youdao/bce-embedding-base_v1")

# --- Channels ---
FEISHU_APP_ID = _get("channels.feishu.app_id", "")
FEISHU_APP_SECRET = _get("channels.feishu.app_secret", "")
QQ_BOT_APPID = _get("channels.qq.bot_appid", "")
QQ_BOT_SECRET = _get("channels.qq.bot_secret", "")

# --- Config reload event system ---

_listeners: list = []


def on_reload(callback) -> None:
    """Register a callback to be called when config is reloaded."""
    _listeners.append(callback)


def reload() -> dict:
    """Re-read YAML config files, update module-level vars, notify listeners.

    Returns a dict of changed values for display.
    """
    global _config
    global LLM_MODEL, LLM_API_KEY, LLM_BASE_URL, ADMIN_TOKEN, CHAT_TOKEN
    global RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
    global SEARCH_API_KEY, SEARCH_API_BASE, CALENDAR_USE_MOCK
    global EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
    global FEISHU_APP_ID, FEISHU_APP_SECRET
    global QQ_BOT_APPID, QQ_BOT_SECRET

    _config = _load_yaml_config()

    old = {
        "LLM_MODEL": LLM_MODEL,
        "LLM_API_KEY": LLM_API_KEY,
        "LLM_BASE_URL": LLM_BASE_URL,
        "ADMIN_TOKEN": ADMIN_TOKEN,
        "CHAT_TOKEN": CHAT_TOKEN,
        "SEARCH_API_KEY": SEARCH_API_KEY,
        "SEARCH_API_BASE": SEARCH_API_BASE,
        "CALENDAR_USE_MOCK": CALENDAR_USE_MOCK,
        "EMBEDDING_API_KEY": EMBEDDING_API_KEY,
        "EMBEDDING_BASE_URL": EMBEDDING_BASE_URL,
        "EMBEDDING_MODEL": EMBEDDING_MODEL,
        "FEISHU_APP_ID": FEISHU_APP_ID,
        "FEISHU_APP_SECRET": FEISHU_APP_SECRET,
        "QQ_BOT_APPID": QQ_BOT_APPID,
        "QQ_BOT_SECRET": QQ_BOT_SECRET,
    }

    LLM_MODEL = _get("llm.model", "gpt-4o")
    LLM_API_KEY = _get("llm.api_key", "")
    LLM_BASE_URL = _get("llm.base_url", "https://api.openai.com/v1")
    ADMIN_TOKEN = _get("server.admin_token", "")
    CHAT_TOKEN = _get("server.chat_token", "")
    RATE_LIMIT_MAX_REQUESTS = _get("server.rate_limit_max_requests", 30)
    RATE_LIMIT_WINDOW_SECONDS = _get("server.rate_limit_window_seconds", 60)
    SEARCH_API_KEY = _get("tools.web_search.api_key", "")
    SEARCH_API_BASE = _get("tools.web_search.api_base", "https://api.tavily.com")
    CALENDAR_USE_MOCK = _get("tools.calendar.use_mock", False)
    EMBEDDING_API_KEY = _get("embedding.api_key", "")
    EMBEDDING_BASE_URL = _get("embedding.base_url", "")
    EMBEDDING_MODEL = _get("embedding.model", "netease-youdao/bce-embedding-base_v1")
    FEISHU_APP_ID = _get("channels.feishu.app_id", "")
    FEISHU_APP_SECRET = _get("channels.feishu.app_secret", "")
    QQ_BOT_APPID = _get("channels.qq.bot_appid", "")
    QQ_BOT_SECRET = _get("channels.qq.bot_secret", "")

    changes = {}
    if old["LLM_MODEL"] != LLM_MODEL:
        changes["LLM_MODEL"] = f"{old['LLM_MODEL']} → {LLM_MODEL}"
    if old["LLM_API_KEY"] != LLM_API_KEY:
        changes["LLM_API_KEY"] = "已更新"
    if old["LLM_BASE_URL"] != LLM_BASE_URL:
        changes["LLM_BASE_URL"] = f"{old['LLM_BASE_URL']} → {LLM_BASE_URL}"
    if old["ADMIN_TOKEN"] != ADMIN_TOKEN:
        changes["ADMIN_TOKEN"] = "已更新"
    if old["CHAT_TOKEN"] != CHAT_TOKEN:
        changes["CHAT_TOKEN"] = "已更新"
    if old["SEARCH_API_KEY"] != SEARCH_API_KEY:
        changes["SEARCH_API_KEY"] = "已更新"
    if old["SEARCH_API_BASE"] != SEARCH_API_BASE:
        changes["SEARCH_API_BASE"] = f"{old['SEARCH_API_BASE']} → {SEARCH_API_BASE}"
    if old["CALENDAR_USE_MOCK"] != CALENDAR_USE_MOCK:
        changes["CALENDAR_USE_MOCK"] = f"{old['CALENDAR_USE_MOCK']} → {CALENDAR_USE_MOCK}"
    if old["EMBEDDING_API_KEY"] != EMBEDDING_API_KEY:
        changes["EMBEDDING_API_KEY"] = "已更新"
    if old["EMBEDDING_BASE_URL"] != EMBEDDING_BASE_URL:
        changes["EMBEDDING_BASE_URL"] = f"{old['EMBEDDING_BASE_URL']} → {EMBEDDING_BASE_URL}"
    if old["EMBEDDING_MODEL"] != EMBEDDING_MODEL:
        changes["EMBEDDING_MODEL"] = f"{old['EMBEDDING_MODEL']} → {EMBEDDING_MODEL}"
    if old["FEISHU_APP_ID"] != FEISHU_APP_ID:
        changes["FEISHU_APP_ID"] = "已更新"
    if old["FEISHU_APP_SECRET"] != FEISHU_APP_SECRET:
        changes["FEISHU_APP_SECRET"] = "已更新"
    if old["QQ_BOT_APPID"] != QQ_BOT_APPID:
        changes["QQ_BOT_APPID"] = "已更新"
    if old["QQ_BOT_SECRET"] != QQ_BOT_SECRET:
        changes["QQ_BOT_SECRET"] = "已更新"

    for callback in _listeners:
        try:
            callback()
        except Exception:
            pass

    return {
        "LLM_MODEL": LLM_MODEL,
        "LLM_BASE_URL": LLM_BASE_URL,
        "API_KEY_SET": bool(LLM_API_KEY),
        "changes": changes,
    }
