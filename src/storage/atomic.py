"""兼容层 — re-export from core.storage."""
from src.core.storage.atomic import _atomic_write

__all__ = ["_atomic_write"]
