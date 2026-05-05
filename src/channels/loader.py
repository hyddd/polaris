"""兼容层 — re-export from core.channel."""
from src.core.channel.loader import discover_and_start, stop_all

__all__ = ["discover_and_start", "stop_all"]
