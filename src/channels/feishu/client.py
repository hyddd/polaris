"""Feishu (Lark) channel plugin — WebSocket bot integration.

Lark SDK caches event loop at module import time — all lark imports are deferred
to function scope so they execute in the daemon thread, not the main thread.
"""

import json
import hashlib
import time
import logging
from collections import OrderedDict

from src.channels import ChannelPlugin

logger = logging.getLogger("polaris.channels.feishu")

MAX_MESSAGE_LENGTH = 28 * 1024  # 28KB — 飞书限制 30KB，留 2KB 余量
# 保守字符限制：按最坏情况 4 字节/字符（如 emoji）计算
_CHAR_LIMIT = MAX_MESSAGE_LENGTH // 4


class PolarisFeishuBot:
    """Feishu WebSocket bot that relays messages to the Polaris Agent Server."""

    def __init__(self):
        from src.core.config import config

        app_id = config.get("channels.feishu.app_id", "")
        app_secret = config.get("channels.feishu.app_secret", "")
        if not app_id or not app_secret:
            raise ValueError("请在 config.yaml 中配置 channels.feishu.app_id 和 app_secret")

        self.app_id = app_id
        self.app_secret = app_secret
        self.client = None
        self.ws_client = None
        self._seen_messages: OrderedDict[str, float] = OrderedDict()
        self._recent_hashes: dict[str, float] = {}

    def start(self):
        import lark_oapi as lark  # Deferred: runs in daemon thread, clean event loop

        logger.info("[feishu] 启动中...")

        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()

        event_handler = lark.EventDispatcherHandler.builder("", "", lark.LogLevel.DEBUG) \
            .register_p2_im_message_receive_v1(self._on_message) \
            .register_p2_im_message_reaction_created_v1(self._on_reaction) \
            .register_p2_im_message_reaction_deleted_v1(self._on_reaction) \
            .build()

        self.ws_client = lark.ws.Client(
            app_id=self.app_id,
            app_secret=self.app_secret,
            log_level=lark.LogLevel.INFO,
            event_handler=event_handler,
            domain=lark.FEISHU_DOMAIN,
            auto_reconnect=True,
        )

        logger.info("[feishu] 开始 WebSocket 连接...")
        self.ws_client.start()

    def stop(self):
        """Attempt to stop the Feishu WebSocket connection."""
        self.ws_client = None
        self.client = None
        # lark ws.Client has no stop() — the daemon thread will be abandoned
        logger.info("[feishu] 已标记停止（旧连接将在 daemon 线程中自然退出）")

    def _on_reaction(self, data) -> None:
        pass

    def _on_message(self, data) -> None:
        try:
            if not data.event:
                return

            msg_id = data.event.message.message_id
            message_type = data.event.message.message_type
            sender_id = data.event.sender.sender_id.open_id if data.event.sender.sender_id else "unknown"

            if message_type not in ("text", "image"):
                return

            if msg_id in self._seen_messages:
                return

            now = time.time()
            self._seen_messages[msg_id] = now

            content_str = data.event.message.content
            content_hash = hashlib.md5(f"{sender_id}:{content_str}".encode()).hexdigest()
            if content_hash in self._recent_hashes:
                if now - self._recent_hashes[content_hash] < 10:
                    return
            self._recent_hashes[content_hash] = now

            # LRU-style cleanup: remove seen_messages older than 1 hour
            cutoff = now - 3600
            while self._seen_messages:
                oldest_id, oldest_time = next(iter(self._seen_messages.items()))
                if oldest_time < cutoff:
                    self._seen_messages.popitem(last=False)
                else:
                    break

            if len(self._recent_hashes) > 1000:
                self._recent_hashes = {k: v for k, v in self._recent_hashes.items() if now - v < 10}

            chat_id = data.event.message.chat_id

            # 提取文本和附件
            text = ""
            attachments = []

            if message_type == "text":
                try:
                    text = json.loads(content_str).get("text", "")
                except json.JSONDecodeError:
                    text = content_str
            elif message_type == "image":
                try:
                    image_key = json.loads(content_str).get("image_key", "")
                    if image_key:
                        image_data = self._download_image(image_key)
                        if image_data:
                            from src.message.models import Attachment
                            import base64

                            b64 = base64.b64encode(image_data).decode()
                            attachments.append(
                                Attachment(
                                    type="image",
                                    data=b64,
                                    mime_type="image/png",
                                    filename=f"{image_key}.png",
                                )
                            )
                except Exception as e:
                    logger.warning(f"[feishu] 处理图片消息失败: {e}")

            if not text.strip() and not attachments:
                return

            reaction_id = self._send_typing(msg_id)
            results = self._process_message(sender_id, text, attachments=attachments or None)
            if reaction_id:
                self._delete_typing(msg_id, reaction_id)
            for response_text, tool_calls in results:
                if response_text:
                    if chat_id:
                        self._send_message(chat_id, response_text)
                    else:
                        self._send_message_by_user(sender_id, response_text)

        except Exception as e:
            logger.error(f"[feishu] 处理消息失败: {e}", exc_info=True)

    def _download_image(self, image_key: str) -> bytes | None:
        """通过飞书 API 下载图片。"""
        try:
            import requests

            # 获取 tenant_access_token
            token_resp = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            token = token_resp.json().get("tenant_access_token")
            if not token:
                logger.warning("[feishu] 获取 tenant_access_token 失败")
                return None

            # 下载图片
            resp = requests.get(
                f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                return resp.content
            logger.warning(f"[feishu] 下载图片失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[feishu] 下载飞书图片失败: {e}")
        return None

    def _process_message(self, user_id: str, text: str, attachments=None) -> list:
        import asyncio
        import threading
        from src.session.manager import get_session_manager
        from src.message import process_message

        session_mgr = get_session_manager()

        result = None
        error = None

        def _run():
            nonlocal result, error
            try:
                result = asyncio.run(process_message(text, session_mgr, channel=f"feishu:{user_id}", attachments=attachments))
            except Exception as e:
                error = e

        # 飞书 SDK 的 WebSocket 回调运行在自有事件循环中，asyncio.run()
        # 不能从已运行的事件循环中调用。用独立线程获取全新事件循环。
        t = threading.Thread(target=_run, name=f"feishu-msg-{user_id[:8]}")
        t.start()
        t.join(timeout=120)

        if error:
            raise error
        if result is None:
            return [("抱歉，处理超时。", [])]
        return result

    def _send_typing(self, message_id: str) -> str | None:
        from lark_oapi.api.im.v1 import CreateMessageReactionRequest, CreateMessageReactionRequestBody, Emoji
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type("Typing").build())
                    .build()) \
                .build()
            response = self.client.im.v1.message_reaction.create(request)
            if response.code == 0:
                return response.data.reaction_id
        except Exception:
            pass
        return None

    def _delete_typing(self, message_id: str, reaction_id: str) -> None:
        from lark_oapi.api.im.v1 import DeleteMessageReactionRequest
        try:
            request = DeleteMessageReactionRequest.builder() \
                .message_id(message_id) \
                .reaction_id(reaction_id) \
                .build()
            self.client.im.v1.message_reaction.delete(request)
        except Exception:
            pass

    def _do_send(self, receive_id: str, receive_id_type: str, content: str) -> None:
        """Send a single message via Feishu API."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        content_json = json.dumps({"text": content}, ensure_ascii=False)
        request = CreateMessageRequest.builder() \
            .receive_id_type(receive_id_type) \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(receive_id)
                .msg_type("text")
                .content(content_json)
                .build()) \
            .build()
        self.client.im.v1.message.create(request)

    def _send_message(self, chat_id: str, content: str) -> None:
        try:
            if len(content.encode('utf-8')) <= MAX_MESSAGE_LENGTH:
                self._do_send(chat_id, "chat_id", content)
            else:
                chunks = ChannelPlugin._split_message(content, _CHAR_LIMIT)
                logger.info(f"[feishu] 消息过长，分 {len(chunks)} 段发送")
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        time.sleep(0.5)
                    self._do_send(chat_id, "chat_id", chunk)
        except Exception as e:
            logger.error(f"[feishu] 发送消息异常: {e}")

    def _send_message_by_user(self, user_id: str, content: str) -> None:
        try:
            if len(content.encode('utf-8')) <= MAX_MESSAGE_LENGTH:
                self._do_send(user_id, "open_id", content)
            else:
                chunks = ChannelPlugin._split_message(content, _CHAR_LIMIT)
                logger.info(f"[feishu] 消息过长，分 {len(chunks)} 段发送")
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        time.sleep(0.5)
                    self._do_send(user_id, "open_id", chunk)
        except Exception as e:
            logger.error(f"[feishu] 发送消息异常: {e}")


class FeishuChannel(ChannelPlugin):
    def __init__(self):
        self._bot: PolarisFeishuBot | None = None

    @property
    def name(self) -> str:
        return "feishu"

    def is_configured(self) -> bool:
        from src.core.config import config

        return bool(config.get("channels.feishu.app_id") and config.get("channels.feishu.app_secret"))

    def get_credentials(self) -> dict:
        from src.core.config import config

        return {
            "app_id": config.get("channels.feishu.app_id", ""),
            "app_secret": config.get("channels.feishu.app_secret", ""),
        }

    def start(self) -> None:
        self._bot = PolarisFeishuBot()
        self._bot.start()

    def stop(self) -> None:
        if self._bot:
            self._bot.stop()
            self._bot = None

    def send_message(self, session_id: str, message: str, channel: str = "") -> bool:
        try:
            if self._bot:
                # channel 格式 "feishu:ou_xxx"，提取用户 ID 发私聊
                if channel and ":" in channel:
                    user_id = channel.split(":", 1)[1]
                    self._bot._send_message_by_user(user_id, message)
                else:
                    self._bot._send_message(session_id, message)
                return True
            logger.warning("飞书 bot 未初始化，无法发送消息")
            return False
        except Exception as e:
            logger.warning(f"飞书发送消息失败: {e}")
            return False

    def rebuild(self) -> None:
        """Re-create bot instance with latest credentials."""
        self._bot = None
