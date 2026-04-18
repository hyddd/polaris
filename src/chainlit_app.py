"""Polaris Chainlit Web UI — HTTP client to Agent Server.

Run: source venv/bin/activate && chainlit run src/chainlit_app.py

Requires Agent Server running on AGENT_SERVER_URL (default http://localhost:8700).
"""

import os
import chainlit as cl
import httpx

AGENT_SERVER = os.getenv("AGENT_SERVER_URL", "http://localhost:8700")


@cl.on_chat_start
async def start():
    # Show active session info
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{AGENT_SERVER}/sessions")
            if r.status_code == 200:
                data = r.json()
                active = data.get("active_session_id", "")
                for s in data.get("sessions", []):
                    if s["session_id"] == active:
                        await cl.Message(
                            content=f"当前会话: **{s['name']}** ({active})\n\n"
                            "你好！我是 Polaris，你的个人效率助手。\n"
                            "• `/new <名称>` 创建新会话\n"
                            "• `/sessions` 查看所有会话\n"
                            "• `/session <id>` 切换会话\n"
                            "• `/help` 查看更多指令"
                        ).send()
                        return
    except Exception:
        pass

    await cl.Message(content="你好！我是 Polaris。发送 `/help` 查看指令。").send()


@cl.on_message
async def on_message(message: cl.Message):
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{AGENT_SERVER}/chat",
                json={"message": message.content, "channel": "web"},
            )
            if r.status_code == 200:
                data = r.json()
                await cl.Message(content=data["response"]).send()
            else:
                await cl.Message(content=f"Agent Server 错误: {r.status_code}").send()
    except httpx.ConnectError:
        await cl.Message(content="无法连接到 Agent Server。请先启动 `python run_server.py`").send()
    except Exception as e:
        await cl.Message(content=f"出错: {e}").send()
