"""Core channel framework."""
from .base import ChannelPlugin
from .loader import discover_and_start, stop_all

__all__ = ["ChannelPlugin", "discover_and_start", "stop_all"]
