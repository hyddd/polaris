"""Feishu (Lark) channel plugin."""

import os
import logging

from src.channels import ChannelPlugin

logger = logging.getLogger("polaris.channels.feishu")


class FeishuChannel(ChannelPlugin):
    @property
    def name(self) -> str:
        return "feishu"

    def is_configured(self) -> bool:
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        return bool(app_id and app_secret)

    def start(self) -> None:
        from src.feishu_bot import PolarisFeishuBot

        bot = PolarisFeishuBot()
        bot.start()

    def stop(self) -> None:
        pass  # WebSocket will be torn down with process
