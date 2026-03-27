"""Polaris 飞书 Bot — WebSocket 长连接通道。

启动方式:
    source venv/bin/activate && python -m src.feishu_bot

需要 .env 中配置:
    FEISHU_APP_ID=xxx
    FEISHU_APP_SECRET=xxx
"""

import logging
import os
import sys
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

from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager
from src.tools.registry import ToolRegistry
from src.tools.todos import TodoTool
from src.tools.notes import NoteTool
from src.tools.calendar import GoogleCalendarTool
from src.tools.rag import RAGSearchTool
from src.config import CALENDAR_FILE, TODOS_FILE, NOTES_DIR, ARCHIVE_DIR, CHROMA_PERSIST_DIR

_user_memories: dict[str, MemoryManager] = {}
_tools_registered = False


def _register_tools():
    global _tools_registered
    if _tools_registered:
        return
    registry = ToolRegistry.get_instance()
    registry.register(TodoTool(data_file=str(TODOS_FILE)))
    registry.register(NoteTool(notes_dir=str(NOTES_DIR), archive_dir=str(ARCHIVE_DIR)))
    registry.register(GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True))
    registry.register(RAGSearchTool(persist_dir=CHROMA_PERSIST_DIR, collection_name="notes"))
    _tools_registered = True
    logger.info("Tools registered")


def _get_memory(user_id: str) -> MemoryManager:
    if user_id not in _user_memories:
        _user_memories[user_id] = MemoryManager(window_size=10)
    return _user_memories[user_id]


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

    def start(self):
        logger.info("Polaris 飞书 Bot 启动中...")

        _register_tools()

        self.client = lark.Client.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        logger.info("飞书客户端创建成功")

        event_handler = lark.EventDispatcherHandler.builder("", "", lark.LogLevel.DEBUG) \
            .register_p2_im_message_receive_v1(self._on_message) \
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

    def _on_message(self, data) -> None:
        try:
            if not data.event:
                return

            sender_id = data.event.sender.sender_id.open_id if data.event.sender.sender_id else "unknown"
            content_str = data.event.message.content
            message_type = data.event.message.message_type
            chat_id = data.event.message.chat_id

            logger.info(f"[{sender_id}] [{message_type}] {content_str}")

            # Parse content
            import json
            try:
                content_obj = json.loads(content_str)
                text = content_obj.get("text", "")
            except json.JSONDecodeError:
                text = content_str

            if not text.strip():
                return

            # Run agent
            response = self._process_message(sender_id, text)

            # Send reply
            if chat_id:
                self._send_message(chat_id, response)
            else:
                self._send_message_by_user(sender_id, response)

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    def _process_message(self, user_id: str, text: str) -> str:
        memory = _get_memory(user_id)
        agent = get_agent()

        memory.add_message(HumanMessage(content=text))
        state = AgentState(
            messages=memory.get_history(),
            intent="",
            user_profile=memory.get_profile(),
            tool_results={},
            final_response="",
            needs_clarification=False,
            pending_action=None,
        )

        try:
            result = agent.invoke(state)
            messages = result.get("messages", [])
            response = "抱歉，处理出错了。"
            for m in reversed(messages):
                if hasattr(m, "content") and m.content and not (
                    hasattr(m, "tool_calls") and m.tool_calls
                ):
                    response = m.content
                    break
        except Exception as e:
            logger.error(f"Agent 调用失败: {e}", exc_info=True)
            response = f"抱歉，出了点问题：{e}"

        memory.add_message(AIMessage(content=response))
        return response

    def _send_typing(self, message_id: str) -> None:
        try:
            request = CreateMessageReactionRequest.builder() \
                .message_id(message_id) \
                .request_body(CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type("Typing").build())
                    .build()) \
                .build()
            self.client.im.v1.message_reaction.create(request)
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
