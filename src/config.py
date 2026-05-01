import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma"))
NOTES_DIR = DATA_DIR / "notes"
ARCHIVE_DIR = NOTES_DIR / "archive"
CALENDAR_FILE = DATA_DIR / "calendar.json"
TODOS_FILE = DATA_DIR / "todos.json"
PROFILE_FILE = DATA_DIR / "user_profile.json"

LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

GCAL_CREDENTIALS = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH")
GCAL_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# --- Config reload event system ---

_listeners: list = []


def on_reload(callback) -> None:
    """Register a callback to be called when config is reloaded."""
    _listeners.append(callback)


def reload() -> dict:
    """Re-read .env, update module-level vars, notify listeners.

    Returns a dict of changed values for display.
    """
    global LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

    load_dotenv(override=True)

    old = {
        "LLM_MODEL": LLM_MODEL,
        "LLM_BASE_URL": LLM_BASE_URL,
    }

    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    LLM_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
    LLM_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    changes = {}
    if old["LLM_MODEL"] != LLM_MODEL:
        changes["LLM_MODEL"] = f"{old['LLM_MODEL']} → {LLM_MODEL}"
    if old["LLM_BASE_URL"] != LLM_BASE_URL:
        changes["LLM_BASE_URL"] = f"{old['LLM_BASE_URL']} → {LLM_BASE_URL}"

    # Notify listeners (each module handles its own update)
    for callback in _listeners:
        try:
            callback()
        except Exception:
            pass

    return {
        "LLM_MODEL": LLM_MODEL,
        "LLM_BASE_URL": LLM_BASE_URL,
        "API_KEY_SET": bool(LLM_API_KEY and LLM_API_KEY != "sk-placeholder"),
        "changes": changes,
    }
