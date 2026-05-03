"""Channel plugin system — each channel is an independent, auto-discovered module."""

import abc
import logging
import threading
from typing import Optional

logger = logging.getLogger("polaris.channels")


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
        from src.config import config
        config.on_reload(self._on_config_reload)

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
