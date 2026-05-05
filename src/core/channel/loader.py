"""YAML-driven channel discovery and lifecycle management."""

import importlib
import inspect
import logging
import threading

logger = logging.getLogger("polaris.channels")

_discovered_channels: list = []
_credentials: dict[str, dict] = {}  # channel name → credentials snapshot
_threads: dict[str, threading.Thread] = {}


def discover_and_start() -> list:
    """从 YAML 配置加载并启动所有 enabled 的 channel 插件。"""
    from src.core.config import config
    from src.core.channel.base import ChannelPlugin

    global _discovered_channels, _credentials
    channels = []

    for ch_name, ch_cfg in config.get("channels", {}).items():
        if not isinstance(ch_cfg, dict):
            continue
        if not ch_cfg.get("enabled", False):
            logger.info(f"[{ch_name}] 未启用，跳过")
            continue

        plugin_path = ch_cfg.get("plugin")
        if not plugin_path:
            logger.warning(f"[{ch_name}] 缺少 plugin 配置，跳过")
            continue

        try:
            mod = importlib.import_module(plugin_path)
            for _, obj in inspect.getmembers(mod, inspect.isclass):
                if issubclass(obj, ChannelPlugin) and obj is not ChannelPlugin:
                    ch = obj()
                    if not ch.is_configured():
                        logger.info(f"[{ch_name}] 未配置凭证，跳过启动")
                        channels.append(ch)
                        break
                    _start_one(ch_name, ch)
                    channels.append(ch)
                    _credentials[ch_name] = ch.get_credentials()
                    break
        except Exception as e:
            logger.error(f"[{ch_name}] 加载失败: {e}")

    _discovered_channels.clear()
    _discovered_channels.extend(channels)
    return channels


def stop_all() -> None:
    """Stop all discovered channels."""
    for ch in _discovered_channels:
        try:
            ch.stop()
            logger.info(f"[{ch.name}] 已停止")
        except Exception as e:
            logger.warning(f"[{ch.name}] 停止失败: {e}")


# ── Hot-reload ────────────────────────────────────────────────

def _on_config_reload(**kwargs):
    """检查 channel 凭证是否变更，自动重启。"""
    for ch in _discovered_channels:
        old_creds = _credentials.get(ch.name, {})
        new_creds = ch.get_credentials()
        if old_creds == new_creds:
            continue

        logger.info(f"[{ch.name}] 凭证已变更，重启中...")
        try:
            ch.stop()
        except Exception:
            pass
        _start_one(ch.name, ch)
        _credentials[ch.name] = new_creds
        logger.info(f"[{ch.name}] 已重启")


def _start_one(ch_name: str, ch) -> None:
    """Start a channel in a daemon thread."""
    t = threading.Thread(
        target=ch.start, daemon=True,
        name=f"channel-{ch_name}"
    )
    t.start()
    _threads[ch_name] = t


# ── Event subscription ────────────────────────────────────────

from src.core.infra import event_bus
event_bus.subscribe("config:reload", _on_config_reload)
