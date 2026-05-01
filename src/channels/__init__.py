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

    def get_credentials(self) -> dict:
        """Return current credentials for change detection. Override in subclass."""
        return {}


class ChannelManager:
    """Discovers, validates, and starts channel plugins."""

    def __init__(self):
        self._channels: list[ChannelPlugin] = []
        self._threads: list[threading.Thread] = []
        self._credentials: dict[str, dict] = {}  # channel name -> credentials snapshot

    def register(self, channel: ChannelPlugin) -> None:
        self._channels.append(channel)

    def discover_and_start(self) -> None:
        """Auto-discover channel plugins by scanning channels/ directory."""
        import importlib
        import pkgutil
        import src.channels as channels_pkg

        for _, module_name, _ in pkgutil.iter_modules(channels_pkg.__path__):
            if module_name.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"src.channels.{module_name}")
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, ChannelPlugin) and attr is not ChannelPlugin:
                        self.register(attr())
            except Exception as e:
                logger.warning(f"Failed to load channel {module_name}: {e}")

        for channel in self._channels:
            if channel.is_configured():
                logger.info(f"[{channel.name}] 已配置，启动中...")
                self._credentials[channel.name] = channel.get_credentials()
                t = threading.Thread(target=channel.start, daemon=True, name=f"channel-{channel.name}")
                t.start()
                self._threads.append(t)
                logger.info(f"[{channel.name}] 已后台启动")
            else:
                logger.info(f"[{channel.name}] 未配置，跳过")

        # Register for config reload events
        from src.config import on_reload
        on_reload(self._on_config_reload)

    def _on_config_reload(self) -> None:
        """Check if channel credentials changed, restart affected channels."""
        for channel in self._channels:
            if not channel.is_configured():
                continue

            old_creds = self._credentials.get(channel.name, {})
            new_creds = channel.get_credentials()

            if old_creds == new_creds:
                continue

            logger.info(f"[{channel.name}] 凭证已变更，重启通道...")
            self._restart_channel(channel, new_creds)

    def _restart_channel(self, channel: ChannelPlugin, new_creds: dict) -> None:
        """Stop and restart a single channel."""
        # Stop old connection
        try:
            channel.stop()
        except Exception as e:
            logger.warning(f"[{channel.name}] 停止旧连接失败: {e}")

        # If the plugin has a rebuild method, use it to pick up new credentials
        if hasattr(channel, 'rebuild'):
            channel.rebuild()

        # Start in new daemon thread
        self._credentials[channel.name] = new_creds
        t = threading.Thread(target=channel.start, daemon=True, name=f"channel-{channel.name}")
        t.start()
        self._threads.append(t)
        logger.info(f"[{channel.name}] 已重启")

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
