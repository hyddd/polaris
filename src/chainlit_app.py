"""Polaris Chainlit Web UI entry point.

Run with: source venv/bin/activate && chainlit run src/chainlit_app.py
"""

import chainlit as cl
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


def register_tools():
    registry = ToolRegistry.get_instance()
    registry.register(TodoTool(data_file=str(TODOS_FILE)))
    registry.register(NoteTool(notes_dir=str(NOTES_DIR), archive_dir=str(ARCHIVE_DIR)))
    registry.register(GoogleCalendarTool(data_file=str(CALENDAR_FILE), use_mock=True))
    registry.register(RAGSearchTool(persist_dir=CHROMA_PERSIST_DIR, collection_name="notes"))


@cl.on_chat_start
async def start():
    cl.user_session.set("memory", MemoryManager(window_size=10))
    register_tools()

    await cl.Message(
        content="你好！我是 Polaris，你的个人效率助手。\n\n"
        "我可以帮你：\n"
        "- 🗓 **查看日程**：今天有什么安排？\n"
        "- 📋 **会议准备**：下午3点的会帮我准备\n"
        "- 🔍 **搜索笔记**：上次RBAC讨论了什么\n"
        "- ✍️ **快速记录**：记一下，明天下午3点开会讨论权限方案\n"
        "- ✏️ **管理信息**：取消明天的晨会\n\n"
        "试试跟我说句话吧！"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    memory: MemoryManager = cl.user_session.get("memory")

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

    # Extract final response from the last AI message in the conversation
    messages = result.get("messages", [])
    response = "抱歉，处理出错了。"
    for m in reversed(messages):
        if hasattr(m, "content") and m.content and not hasattr(m, "tool_calls"):
            response = m.content
            break
        if hasattr(m, "content") and m.content and hasattr(m, "tool_calls") and not m.tool_calls:
            response = m.content
            break

    memory.add_message(AIMessage(content=response))
    await cl.Message(content=response).send()
