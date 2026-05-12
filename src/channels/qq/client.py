"""QQ (Tencent Bot) channel plugin — botpy SDK integration."""

import asyncio
import logging
import re

import botpy
from botpy.message import GroupMessage, C2CMessage, Message, DirectMessage

from src.core.channel import ChannelPlugin

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
        from src.message import process_message
        from src.message.models import Attachment
        from src.session.manager import get_session_manager

        text = content.strip()

        # 提取图片附件 & 语音消息
        attachments = []
        voice_texts = []
        msg_attachments = getattr(message, 'attachments', None) or []
        for att in msg_attachments:
            url = getattr(att, 'url', None)
            content_type = getattr(att, 'content_type', '')
            if url and content_type.startswith('image/'):
                # 图片附件
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            import base64
                            b64 = base64.b64encode(resp.content).decode()
                            attachments.append(Attachment(
                                type="image",
                                data=b64,
                                mime_type=content_type,
                                filename=getattr(att, 'filename', 'image'),
                            ))
                except Exception as e:
                    logger.warning(f"下载图片失败: {e}")
            elif url and ('audio' in content_type or 'voice' in content_type):
                # 语音消息：下载 → STT → 拼接到文本
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            from src.domains.voice import get_voice_domain
                            domain = get_voice_domain()
                            recognized = domain.transcribe(resp.content) if domain else None
                            if recognized:
                                voice_texts.append(recognized)
                                logger.info(f"语音识别成功: {recognized[:50]}...")
                except Exception as e:
                    logger.warning(f"语音识别失败: {e}")

        # 将语音识别结果拼接到文本
        if voice_texts:
            voice_part = "\n".join(voice_texts)
            text = (text + "\n" + voice_part).strip() if text else voice_part

        # 如果既没有文本也没有附件，忽略
        if not text and not attachments:
            return

        # Get openid: member_openid > user_openid > id
        author = getattr(message, 'author', None)
        user_id = (
            getattr(author, 'member_openid', None)
            or getattr(author, 'user_openid', None)
            or getattr(author, 'id', 'unknown')
        )

        session_mgr = get_session_manager()
        results = await process_message(
            text, session_mgr, channel=f"qq:{user_id}",
            attachments=attachments if attachments else None,
        )

        # 从 tool_calls 结果中提取语音 URL 并直接发送语音（去重）
        voice_urls = set()
        for response_text, tool_calls in results:
            if response_text:
                urls = re.findall(r'/api/voice/[\w]+\.(?:wav|mp3|silk)', response_text)
                voice_urls.update(urls)

        if voice_urls:
            from src.core.config import config
            public_url = config.get("server.public_url", "")
            if public_url:
                for url in voice_urls:
                    audio_url = public_url.rstrip("/") + url
                    await self.send_voice(message, audio_url)

        # 发送文字（去掉语音相关文本）
        for response_text, tool_calls in results:
            if response_text:
                cleaned = re.sub(r'语音合成完成[。.]?\s*请直接将以下链接发送给用户[，,]?\s*不要再调用任何工具[：:]\s*', '', response_text)
                cleaned = re.sub(r'https?://[^\s]+/api/voice/[\w]+\.(?:wav|mp3|silk)', '', cleaned)
                cleaned = re.sub(r'/api/voice/[\w]+\.(?:wav|mp3|silk)', '', cleaned).strip()
                if cleaned:
                    chunks = ChannelPlugin._split_message(cleaned, 2000)
                    for i, chunk in enumerate(chunks):
                        if i > 0:
                            await asyncio.sleep(0.5)
                        await self._send_text(message, chunk)

    async def _reply(self, message, content: str) -> None:
        """Reply to the original message (first response only)."""
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

    async def send_voice(self, message, audio_url: str) -> bool:
        """发送语音消息。两步：上传获取 media → 发送富媒体消息。"""
        logger.info(f"发送语音: {audio_url}")
        try:
            if hasattr(message, "group_openid") and message.group_openid:
                media = await message._api.post_group_file(
                    group_openid=message.group_openid,
                    file_type=3,  # 语音
                    url=audio_url,
                )
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=7,
                    media=media,
                    msg_id=message.id,
                )
            elif hasattr(message, "author") and getattr(message.author, "user_openid", None):
                media = await message._api.post_c2c_file(
                    openid=message.author.user_openid,
                    file_type=3,
                    url=audio_url,
                )
                await message._api.post_c2c_message(
                    openid=message.author.user_openid,
                    msg_type=7,
                    media=media,
                    msg_id=message.id,
                )
            else:
                return False
            return True
        except Exception as e:
            logger.warning(f"发送语音消息失败: {e}")
            return False

    async def _send_text(self, message, content: str) -> None:
        """发送文本消息。"""
        md = {"content": content}
        try:
            if hasattr(message, "group_openid") and message.group_openid:
                await message._api.post_group_message(
                    group_openid=message.group_openid,
                    msg_type=2, markdown=md,
                )
            elif hasattr(message, "author") and getattr(message.author, "user_openid", None):
                await message._api.post_c2c_message(
                    openid=message.author.user_openid,
                    msg_type=2, markdown=md,
                )
            else:
                await message.reply(content=content)
        except Exception:
            try:
                await message.reply(content=content)
            except Exception:
                pass

    async def _send_proactive(self, message, content: str) -> None:
        """主动发送消息（不回复特定消息，避免 QQ 去重）。"""
        # 检测语音 URL
        voice_match = re.search(r'(/api/voice/[\w]+\.(?:wav|mp3|silk))', content)
        if voice_match:
            from src.core.config import config
            public_url = config.get("server.public_url", "")
            if public_url:
                audio_url = public_url.rstrip("/") + voice_match.group(1)
                success = await self.send_voice(message, audio_url)
                if success:
                    remaining = content.replace(voice_match.group(0), "").strip()
                    if remaining:
                        await self._send_text(message, remaining)
                    return

        await self._send_text(message, content)


class QQChannel(ChannelPlugin):
    def __init__(self):
        self._client: _PolarisQQClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def name(self) -> str:
        return "qq"

    def is_configured(self) -> bool:
        from src.core.config import config

        return bool(config.get("channels.qq.bot_appid") and config.get("channels.qq.bot_secret"))

    def get_credentials(self) -> dict:
        from src.core.config import config

        return {
            "appid": config.get("channels.qq.bot_appid", ""),
            "secret": config.get("channels.qq.bot_secret", ""),
        }

    def start(self) -> None:
        from src.core.config import config

        appid = config.get("channels.qq.bot_appid", "")
        secret = config.get("channels.qq.bot_secret", "")

        # botpy.Client.__init__ calls asyncio.get_event_loop(); ensure one exists
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        intents = botpy.Intents(
            public_guild_messages=True,
            public_messages=True,
            direct_message=True,
        )

        # botpy 自带 handler 格式不统一，清除后让它走 root logger 统一格式
        for name in ("botpy", "botpy.gateway", "botpy.connection", "botpy.http"):
            logging.getLogger(name).handlers.clear()
            logging.getLogger(name).propagate = True
        logging.getLogger("botpy.gateway").setLevel(logging.WARNING)

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
