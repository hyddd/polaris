"""兼容层 — re-export from core.storage."""
from src.core.storage.store import DataStore, JsonFileStore

__all__ = ["DataStore", "JsonFileStore"]
