"""YAML-driven channel discovery and lifecycle management."""

import importlib
import inspect
import logging

logger = logging.getLogger("polaris.channels")

_discovered_channels: list = []


def discover_and_start() -> list:
    """从 YAML 配置加载并启动所有 enabled 的 channel 插件。

    遍历 config.get("channels", {})，对每个 enabled 且有 plugin 路径的：
    1. importlib.import_module(plugin) 动态加载
    2. 查找模块中的 ChannelPlugin 子类，实例化
    3. 调用 instance.start()
    """
    from src.config import config
    from src.channels.base import ChannelPlugin

    global _discovered_channels
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
                    ch.start()
                    channels.append(ch)
                    logger.info(f"[{ch_name}] 已启动")
                    break
        except Exception as e:
            logger.error(f"[{ch_name}] 加载失败: {e}")

    _discovered_channels = channels
    return channels


def stop_all() -> None:
    """Stop all discovered channels."""
    for ch in _discovered_channels:
        try:
            ch.stop()
            logger.info(f"[{ch.name}] 已停止")
        except Exception as e:
            logger.warning(f"[{ch.name}] 停止失败: {e}")
