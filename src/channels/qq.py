"""QQ (Tencent Bot) channel plugin — botpy SDK integration."""

import asyncio
import os
import logging

import botpy
from botpy.message import GroupMessage, C2CMessage, Message, DirectMessage

from src.channels import ChannelPlugin

logger = logging.getLogger("polaris.channels.qq")


class _PolarisQQClient(botpy.Client):
    """QQ bot client that relays messages to the Polaris Agent Server."""

    async def on_ready(self):
        logger.info(f"[qq] robot 「{self.robot.name}」 online")

    async def on_group_at_message_create(self, message: GroupMessage):
        await self._handle(message.content, message)

    async def on_c2c_message_create(self, message: C2CMessage):
        await self._handle(message.content, message)

    async def on_at_message_create(self, message: Message):
        await self._handle(message.content, message)

    async def on_direct_message_create(self, message: DirectMessage):
        await self._handle(message.content, message)

    async def _handle(self, content: str, message) -> None:
        from src.server import process_message
        from src.session.manager import get_session_manager

        text = content.strip()
        if not text:
            return

        session_mgr = get_session_manager()
        loop = asyncio.get_running_loop()
        response_text, _ = await loop.run_in_executor(
            None, lambda: process_message(text, session_mgr, channel="qq")
        )

        if response_text:
            await self._reply(message, response_text[:2000])

    async def _reply(self, message, content: str) -> None:
        """Send markdown-rendered reply. msg_type=2 enables rich rendering on mobile."""
        md = {"content": content}
        try:
            if hasattr(message, "group_openid") and message.group_openid:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=2, markdown=md, msg_id=message.id,
                )
            elif hasattr(message, "author") and getattr(message.author, "user_openid", None):
                await message._api.post_c2c_message(
                    openid=message.author.user_openid,
                    msg_type=2, markdown=md, msg_id=message.id,
                )
            elif hasattr(message, "channel_id"):
                await message._api.post_message(
                    channel_id=message.channel_id,
                    markdown=md, msg_id=message.id,
                )
            else:
                await message.reply(content=content)
        except Exception:
            try:
                await message.reply(content=content)
            except Exception:
                pass


class QQChannel(ChannelPlugin):
    def __init__(self):
        self._client: _PolarisQQClient | None = None

    @property
    def name(self) -> str:
        return "qq"

    def is_configured(self) -> bool:
        appid = os.getenv("QQ_BOT_APPID", "")
        secret = os.getenv("QQ_BOT_SECRET", "")
        return bool(appid and secret)

    def get_credentials(self) -> dict:
        return {
            "appid": os.getenv("QQ_BOT_APPID", ""),
            "secret": os.getenv("QQ_BOT_SECRET", ""),
        }

    def start(self) -> None:
        appid = os.getenv("QQ_BOT_APPID", "")
        secret = os.getenv("QQ_BOT_SECRET", "")

        # botpy.Client.__init__ calls asyncio.get_event_loop(); ensure one exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        intents = botpy.Intents(
            public_guild_messages=True,
            public_messages=True,
            direct_message=True,
        )

        logger.info(f"[qq] 启动 QQ Bot (appid={appid[:8]}...)")
        self._client = _PolarisQQClient(intents=intents, is_sandbox=False)
        self._client.run(appid=appid, secret=secret)

    def stop(self) -> None:
        if self._client and not self._client.is_closed:
            try:
                asyncio.get_event_loop().run_until_complete(self._client.close())
            except Exception:
                pass
            self._client = None
            logger.info("[qq] 已停止")

    def rebuild(self) -> None:
        """Re-create client instance with latest credentials."""
        self._client = None
