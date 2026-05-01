"""Feishu (Lark) channel plugin — WebSocket bot integration.

Lark SDK caches event loop at module import time — all lark imports are deferred
to function scope so they execute in the daemon thread, not the main thread.
"""

import json
import hashlib
import time
import os
import logging
from collections import OrderedDict

from src.channels import ChannelPlugin

logger = logging.getLogger("polaris.channels.feishu")


class PolarisFeishuBot:
    """Feishu WebSocket bot that relays messages to the Polaris Agent Server."""

    def __init__(self):
        app_id = os.getenv("FEISHU_APP_ID")
        app_secret = os.getenv("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("请在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

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

            if message_type != "text":
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

            try:
                text = json.loads(content_str).get("text", "")
            except json.JSONDecodeError:
                text = content_str

            if not text.strip():
                return

            reaction_id = self._send_typing(msg_id)
            response = self._process_message(sender_id, text)
            if reaction_id:
                self._delete_typing(msg_id, reaction_id)
            if chat_id:
                self._send_message(chat_id, response)
            else:
                self._send_message_by_user(sender_id, response)

        except Exception as e:
            logger.error(f"[feishu] 处理消息失败: {e}", exc_info=True)

    def _process_message(self, user_id: str, text: str) -> str:
        from src.session.manager import get_session_manager
        from src.server import process_message

        session_mgr = get_session_manager()
        response_text, _ = process_message(text, session_mgr)
        return response_text

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

    def _send_message(self, chat_id: str, content: str) -> None:
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        content_json = json.dumps({"text": content}, ensure_ascii=False)
        try:
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content_json)
                    .build()) \
                .build()
            self.client.im.v1.message.create(request)
        except Exception as e:
            logger.error(f"[feishu] 发送消息异常: {e}")

    def _send_message_by_user(self, user_id: str, content: str) -> None:
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        content_json = json.dumps({"text": content}, ensure_ascii=False)
        try:
            request = CreateMessageRequest.builder() \
                .receive_id_type("open_id") \
                .request_body(CreateMessageRequestBody.builder()
                    .receive_id(user_id)
                    .msg_type("text")
                    .content(content_json)
                    .build()) \
                .build()
            self.client.im.v1.message.create(request)
        except Exception as e:
            logger.error(f"[feishu] 发送消息异常: {e}")


class FeishuChannel(ChannelPlugin):
    def __init__(self):
        self._bot: PolarisFeishuBot | None = None

    @property
    def name(self) -> str:
        return "feishu"

    def is_configured(self) -> bool:
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        return bool(app_id and app_secret)

    def get_credentials(self) -> dict:
        return {
            "app_id": os.getenv("FEISHU_APP_ID", ""),
            "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
        }

    def start(self) -> None:
        self._bot = PolarisFeishuBot()
        self._bot.start()

    def stop(self) -> None:
        if self._bot:
            self._bot.stop()
            self._bot = None

    def rebuild(self) -> None:
        """Re-create bot instance with latest credentials."""
        self._bot = None
