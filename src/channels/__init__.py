"""Channel plugin system — each channel is an independent, auto-discovered module."""

import abc
import logging
import threading
from typing import Optional

logger = logging.getLogger("polaris.channels")


class ChannelPlugin(abc.ABC):
    """Base class for chat channel integrations (Feishu, QQ, WeChat, etc.)."""

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

    def stop(self) -> None:
        """Optional: clean shutdown."""
        pass


class ChannelManager:
    """Discovers, validates, and starts channel plugins."""

    def __init__(self):
        self._channels: list[ChannelPlugin] = []
        self._threads: list[threading.Thread] = []

    def register(self, channel: ChannelPlugin) -> None:
        self._channels.append(channel)

    def discover_and_start(self) -> None:
        """Import known channel modules, check config, start enabled ones."""
        self._try_import("src.channels.feishu", "FeishuChannel")

        for channel in self._channels:
            if channel.is_configured():
                logger.info(f"[{channel.name}] 已配置，启动中...")
                t = threading.Thread(target=channel.start, daemon=True, name=f"channel-{channel.name}")
                t.start()
                self._threads.append(t)
                logger.info(f"[{channel.name}] 已后台启动")
            else:
                logger.info(f"[{channel.name}] 未配置，跳过")

    def _try_import(self, module_path: str, class_name: str) -> Optional[ChannelPlugin]:
        try:
            import importlib
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            instance = cls()
            self.register(instance)
            return instance
        except ImportError as e:
            logger.debug(f"Channel module not found: {module_path} ({e})")
        except Exception as e:
            logger.warning(f"Failed to load channel {module_path}: {e}")
        return None
