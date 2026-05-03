"""Channel plugin system — each channel is an independent, auto-discovered module.

Channels are loaded from YAML configuration at startup.  Each enabled channel
must specify a ``plugin`` module path (e.g. ``"src.channels.feishu"``)
that exports a ``ChannelPlugin`` subclass.
"""

import abc
import importlib
import inspect
import logging
from typing import Optional

logger = logging.getLogger("polaris.channels")

# Module-level list of started channel instances, populated by _discover_and_start().
# Imported by other modules (e.g., reminders/handlers) to enumerate active channels.
_discovered_channels: list["ChannelPlugin"] = []


class ChannelPlugin(abc.ABC):
    """Base class for chat channel integrations (Feishu, QQ, WeChat, etc.)."""

    @staticmethod
    def _split_message(text: str, max_length: int) -> list[str]:
        """按段落/句子边界智能分段，fallback 到硬截断。

        优先按段落（\\n\\n）边界拆分，其次按句子（。！？）边界拆分，
        若无可用的自然边界则按字符数硬截断。

        Args:
            text: 消息原文
            max_length: 单条消息最大字符数

        Returns:
            分段后的消息列表，每段不超过 max_length 字符
        """
        if not text:
            return []
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            # 候选块：取前 max_length 个字符
            chunk = remaining[:max_length]

            # 1. 尝试按段落边界（\\n\\n）拆分
            split_pos = chunk.rfind('\n\n')
            if split_pos > 0:
                chunks.append(remaining[:split_pos])
                remaining = remaining[split_pos:].lstrip('\n')
                continue

            # 2. 尝试按句子边界（。！？）拆分
            split_pos = -1
            for p in ('。', '！', '？'):
                pos = chunk.rfind(p)
                if pos > split_pos:
                    split_pos = pos
            if split_pos > 0:
                chunks.append(remaining[:split_pos + 1])
                remaining = remaining[split_pos + 1:]
                continue

            # 3. 硬截断
            chunks.append(chunk)
            remaining = remaining[max_length:]

        return chunks

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Channel name, e.g. 'feishu', 'qq'."""
        ...

    @abc.abstractmethod
    def is_configured(self) -> bool:
        """Check if this channel has the required credentials/config."""
        ...

    @abc.abstractmethod
    def start(self) -> None:
        """Start the channel (usually a blocking call — runs in a daemon thread)."""
        ...

    def send_message(self, session_id: str, message: str) -> bool:
        """发送消息到指定会话。返回是否成功。"""
        raise NotImplementedError(f"{self.name} 不支持主动发送消息")

    def stop(self) -> None:
        """Optional: clean shutdown."""
        pass

    def get_credentials(self) -> dict:
        """Return current credentials for change detection. Override in subclass."""
        return {}


def _discover_and_start() -> list[ChannelPlugin]:
    """从 YAML 配置加载并启动所有 enabled 的 channel 插件。

    遍历 config.get("channels", {})，对每个 enabled 且有 plugin 路径的：
    1. importlib.import_module(plugin) 动态加载
    2. 查找模块中的 ChannelPlugin 子类，实例化
    3. 调用 instance.start()
    """
    from src.config import config

    global _discovered_channels
    channels: list[ChannelPlugin] = []

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
            # 在模块中查找 ChannelPlugin 子类
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


def _stop_all() -> None:
    """Stop all discovered channels."""
    for ch in _discovered_channels:
        try:
            ch.stop()
            logger.info(f"[{ch.name}] 已停止")
        except Exception as e:
            logger.warning(f"[{ch.name}] 停止失败: {e}")
