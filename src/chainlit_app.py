"""Polaris Chainlit Web UI entry point.

Run with: source venv/bin/activate && chainlit run src/chainlit_app.py
"""

import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.session_manager import get_session_manager
from src.tools.registry import ToolRegistry
from src.tools.todos import TodoTool
from src.tools.notes import NoteTool
from src.tools.calendar import GoogleCalendarTool
from src.tools.rag import RAGSearchTool
from src.config import CALENDAR_FILE, TODOS_FILE, NOTES_DIR, ARCHIVE_DIR, CHROMA_PERSIST_DIR


def register_tools():
    registry = ToolRegistry.get_instance()
    if registry.list_tools():
        return
    registry.register(TodoTool(data_file=str(TODOS_FILE)))
    registry.register(NoteTool(notes_dir=str(NOTES_DIR), archive_dir=str(ARCHIVE_DIR)))
    registry.register(GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True))
    registry.register(RAGSearchTool(persist_dir=CHROMA_PERSIST_DIR, collection_name="notes"))


@cl.on_chat_start
async def start():
    register_tools()
    session_mgr = get_session_manager()
    cl.user_session.set("session_id", session_mgr._active_id)

    await cl.Message(
        content="你好！我是 Polaris，你的个人效率助手。\n\n"
        "我可以帮你：\n"
        "- 🗓 **查看日程**：今天有什么安排？\n"
        "- 📋 **会议准备**：下午3点的会帮我准备\n"
        "- 🔍 **搜索笔记**：上次RBAC讨论了什么\n"
        "- ✍️ **快速记录**：记一下，明天下午3点开会讨论权限方案\n"
        "- ✏️ **管理信息**：取消明天的晨会\n\n"
        "会话命令：\n"
        "• `/new <名称>` — 创建新会话\n"
        "• `/sessions` — 查看所有会话\n"
        "• `/session <id|名称>` — 切换会话\n"
        "• `/help` — 查看更多指令"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    session_mgr = get_session_manager()
    session = session_mgr.active_session
    memory = session.memory

    agent = get_agent()

    memory.add_message(HumanMessage(content=message.content))
    state = AgentState(
        messages=memory.get_history(),
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=None,
    )

    result = agent.invoke(state)

    messages = result.get("messages", [])
    response = result.get("final_response", "")
    if not response:
        for m in reversed(messages):
            if hasattr(m, "content") and m.content and not (
                hasattr(m, "tool_calls") and m.tool_calls
            ):
                response = m.content
                break
    if not response:
        response = "抱歉，处理出错了。"

    memory.add_message(AIMessage(content=response))
    session_mgr.record_message(message.content, response)

    await cl.Message(content=response).send()
