"""QQ (Tencent Bot) channel plugin — botpy SDK integration."""

import asyncio
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
        from src.handler import process_message
        from src.session.manager import get_session_manager

        text = content.strip()
        if not text:
            return

        # Get openid: member_openid > user_openid > id
        author = getattr(message, 'author', None)
        user_id = (
            getattr(author, 'member_openid', None)
            or getattr(author, 'user_openid', None)
            or getattr(author, 'id', 'unknown')
        )

        session_mgr = get_session_manager()
        response_text, _ = await process_message(text, session_mgr, channel=f"qq:{user_id}")

        if response_text:
            chunks = ChannelPlugin._split_message(response_text, 2000)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)
                await self._reply(message, chunk)

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
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def name(self) -> str:
        return "qq"

    def is_configured(self) -> bool:
        from src.config import QQ_BOT_APPID, QQ_BOT_SECRET

        return bool(QQ_BOT_APPID and QQ_BOT_SECRET)

    def get_credentials(self) -> dict:
        from src.config import QQ_BOT_APPID, QQ_BOT_SECRET

        return {
            "appid": QQ_BOT_APPID,
            "secret": QQ_BOT_SECRET,
        }

    def start(self) -> None:
        from src.config import QQ_BOT_APPID, QQ_BOT_SECRET

        appid = QQ_BOT_APPID
        secret = QQ_BOT_SECRET

        # botpy.Client.__init__ calls asyncio.get_event_loop(); ensure one exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

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

    def send_message(self, session_id: str, message: str, channel: str = "") -> bool:
        """主动发送消息给用户。

        Args:
            session_id: 会话 ID（未使用）
            message: 消息内容
            channel: 渠道标识，格式 "qq:{openid}"
        """
        try:
            if not self._client:
                logger.warning("QQ Bot 未启动")
                return False

            # 直接从 channel 提取 openid
            if not channel or not channel.startswith("qq:"):
                logger.warning(f"无效的 QQ channel: {channel}")
                return False

            openid = channel.split(":", 1)[1]
            if not openid:
                logger.warning("openid 为空")
                return False

            if not self._loop:
                logger.warning("QQ 事件循环未初始化")
                return False

            # 分段发送长消息
            chunks = ChannelPlugin._split_message(message, 2000)

            async def _send_all():
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        await asyncio.sleep(0.5)
                    md = {"content": chunk}
                    await self._client.api.post_c2c_message(
                        openid=openid,
                        msg_type=2,
                        markdown=md,
                    )

            # 在事件循环中执行异步任务
            future = asyncio.run_coroutine_threadsafe(_send_all(), self._loop)
            # 等待完成，超时 10 秒每段
            future.result(timeout=max(10, 10 * len(chunks)))

            logger.info(f"QQ 消息已发送到 {openid}")
            return True
        except Exception as e:
            logger.warning(f"QQ发送消息失败: {e}")
            return False

    def rebuild(self) -> None:
        """Re-create client instance with latest credentials."""
        self._client = None
