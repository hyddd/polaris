"""Polaris Chainlit Web UI entry point.

Run with: source venv/bin/activate && chainlit run src/chainlit_app.py
"""

import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage
from src.agent.graph import get_agent
from src.state import AgentState
from src.memory.store import MemoryManager


@cl.on_chat_start
async def start():
    cl.user_session.set("memory", MemoryManager(window_size=10))

    await cl.Message(
        content="你好！我是 Polaris，你的个人效率助手。\n\n"
        "目前已支持：\n"
        "- 🗓 **查看日程**：今天有什么安排？\n"
        "- 📋 **会议准备**：下午的会帮我准备（开发中）\n"
        "- 🔍 **搜索笔记**：上次RBAC讨论了什么（开发中）\n"
        "- ✍️ **快速记录**：记一下，明天开会要讨论权限方案（开发中）\n"
        "- ✏️ **管理信息**：取消明天的晨会（开发中）\n\n"
        "试试跟我说：**今天有什么安排？**"
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
    response = result.get("final_response", "抱歉，处理出错了。")
    memory.add_message(AIMessage(content=response))

    await cl.Message(content=response).send()
