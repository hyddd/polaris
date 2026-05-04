"""Channel plugin system.

Each channel is an independent module under its own subdirectory.
Channels are loaded from YAML configuration at startup.
"""

from src.channels.base import ChannelPlugin
from src.channels.loader import discover_and_start, stop_all
