"""Channels — 兼容层，re-export core.channel。"""
from src.core.channel import ChannelPlugin, discover_and_start, stop_all

__all__ = ["ChannelPlugin", "discover_and_start", "stop_all"]
