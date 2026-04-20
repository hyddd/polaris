"""Polaris 飞书 Bot — WebSocket 长连接通道。

启动方式:
    source venv/bin/activate && python -m src.feishu_bot

需要 .env 中配置:
    FEISHU_APP_ID=xxx
    FEISHU_APP_SECRET=xxx
"""

import logging
import os
import hashlib
import time
from datetime import datetime

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from dotenv import load_dotenv

load_dotenv()

# Logging setup
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"logs/feishu_{datetime.now().strftime('%Y%m%d')}.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("polaris.feishu")


class PolarisFeishuBot:
    def __init__(self):
        app_id = os.getenv("FEISHU_APP_ID")
        app_secret = os.getenv("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            raise ValueError("请在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

        self.app_id = app_id
        self.app_secret = app_secret
        self.client = None
        self.ws_client = None
        self._seen_messages: set[str] = set()
        self._recent_hashes: dict[str, float] = {}  # content_hash → timestamp

    def start(self):
        logger.info("Polaris 飞书 Bot 启动中...")


        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        logger.info("飞书客户端创建成功")

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

        logger.info("开始 WebSocket 连接...")
        self.ws_client.start()

    def _on_reaction(self, data) -> None:
        """Silently consume reaction events (triggered by typing indicator)."""
        pass

    def _on_message(self, data) -> None:
        try:
            if not data.event:
                return

            msg_id = data.event.message.message_id
            message_type = data.event.message.message_type
            sender_id = data.event.sender.sender_id.open_id if data.event.sender.sender_id else "unknown"

            # Only process user text messages; skip bot's own messages and non-text
            if message_type != "text":
                logger.debug(f"[{sender_id}] 跳过非文本消息: {message_type}")
                return

            # Dedup by message_id
            if msg_id in self._seen_messages:
                logger.debug(f"[{sender_id}] 跳过重复消息 (msg_id): {msg_id[:20]}...")
                return
            self._seen_messages.add(msg_id)

            # Also dedup by content hash within 10s window (catches cross-event dupes)
            content_str = data.event.message.content
            content_hash = hashlib.md5(f"{sender_id}:{content_str}".encode()).hexdigest()
            now = time.time()
            if content_hash in self._recent_hashes:
                elapsed = now - self._recent_hashes[content_hash]
                if elapsed < 10:
                    logger.debug(f"[{sender_id}] 跳过重复消息 (content, {elapsed:.1f}s ago)")
                    return
            self._recent_hashes[content_hash] = now

            # Cleanup stale hashes
            if len(self._recent_hashes) > 1000:
                self._recent_hashes = {k: v for k, v in self._recent_hashes.items() if now - v < 10}
            if len(self._seen_messages) > 10000:
                self._seen_messages.clear()

            chat_id = data.event.message.chat_id
            logger.info(f"[{sender_id}] {content_str}")

            # Parse text content
            import json
            try:
                content_obj = json.loads(content_str)
                text = content_obj.get("text", "")
            except json.JSONDecodeError:
                text = content_str

            if not text.strip():
                return

            # Show typing indicator
            reaction_id = self._send_typing(data.event.message.message_id)

            # Run agent
            response = self._process_message(sender_id, text)

            # Remove typing indicator, then send reply
            if reaction_id:
                self._delete_typing(data.event.message.message_id, reaction_id)
            if chat_id:
                self._send_message(chat_id, response)
            else:
                self._send_message_by_user(sender_id, response)

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    def _process_message(self, user_id: str, text: str) -> str:
        import urllib.request, json as _json

        agent_url = os.getenv("AGENT_SERVER_URL", "http://localhost:8700")
        try:
            req = urllib.request.Request(
                f"{agent_url}/chat",
                data=_json.dumps({
                    "message": text,
                    "channel": f"feishu:{user_id}"
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = _json.loads(resp.read())
                return data.get("response", "抱歉，处理出错了。")
        except Exception as e:
            logger.error(f"Agent Server 调用失败: {e}")
            return f"Agent Server 连接失败: {e}"

    def _send_typing(self, message_id: str) -> str | None:
        """发送 typing 表情，返回 reaction_id 用于后续删除。"""
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
        """删除 typing 表情。"""
        try:
            request = DeleteMessageReactionRequest.builder() \
                .message_id(message_id) \
                .reaction_id(reaction_id) \
                .build()
            self.client.im.v1.message_reaction.delete(request)
        except Exception:
            pass

    def _send_message(self, chat_id: str, content: str) -> None:
        import json
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
            response = self.client.im.v1.message.create(request)
            if response.code == 0:
                logger.info(f"回复发送成功 → {chat_id}")
            else:
                logger.error(f"回复发送失败: {response.code} {response.msg}")
        except Exception as e:
            logger.error(f"发送消息异常: {e}")

    def _send_message_by_user(self, user_id: str, content: str) -> None:
        import json
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
            response = self.client.im.v1.message.create(request)
            if response.code == 0:
                logger.info(f"回复发送成功 → {user_id}")
            else:
                logger.error(f"回复发送失败: {response.code} {response.msg}")
        except Exception as e:
            logger.error(f"发送消息异常: {e}")


def main():
    bot = PolarisFeishuBot()
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出")
    except Exception as e:
        logger.error(f"Bot 启动失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
