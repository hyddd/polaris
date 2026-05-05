"""Storage — 兼容层，re-export core.storage。"""
from src.core.storage import DataStore, JsonFileStore, _atomic_write

__all__ = ["DataStore", "JsonFileStore", "_atomic_write"]
