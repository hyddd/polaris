"""Polaris Chainlit Web UI — SSE streaming client to Agent Server.

Run: source venv/bin/activate && chainlit run src/chainlit_app.py

Requires Agent Server running on AGENT_SERVER_URL (default http://localhost:8700).
"""

import os
import json
import chainlit as cl
import httpx

AGENT_SERVER = os.getenv("AGENT_SERVER_URL", "http://localhost:8700")


@cl.on_chat_start
async def start():
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
    # Create an empty message to stream into
    msg = cl.Message(content="")
    await msg.send()

    tool_calls_shown = []
    full_response = ""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{AGENT_SERVER}/chat/stream",
                json={"message": message.content, "channel": "web"},
            ) as response:
                if response.status_code != 200:
                    msg.content = f"Agent Server 错误: {response.status_code}"
                    await msg.update()
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk

                    # Parse SSE events from buffer
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)

                        event_type = ""
                        data_str = ""
                        for line in event_text.split("\n"):
                            if line.startswith("event: "):
                                event_type = line[7:]
                            elif line.startswith("data: "):
                                data_str = line[6:]

                        if not data_str:
                            continue

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        if not isinstance(data, dict):
                            continue

                        if event_type == "node":
                            pass  # Internal progress, skip showing

                        elif event_type == "tool_call":
                            tool_name = data.get("tool", "")
                            if tool_name not in tool_calls_shown:
                                tool_calls_shown.append(tool_name)
                                full_response += f"\n🔧 调用工具: {tool_name}..."

                        elif event_type == "message":
                            content = data.get("content", "")
                            if content:
                                # Strip tool_call placeholder text from earlier
                                if full_response:
                                    # Replace tool placeholders with clean response
                                    full_response = content
                                else:
                                    full_response = content

                        elif event_type == "done":
                            pass

                        elif event_type == "error":
                            full_response = f"❌ {data.get('error', '未知错误')}"

                    # Update the message with latest content
                    msg.content = full_response or "处理中..."
                    await msg.update()

    except httpx.ConnectError:
        msg.content = "无法连接到 Agent Server。请先启动 `python run.py`"
        await msg.update()
    except Exception as e:
        msg.content = f"出错: {e}"
        await msg.update()
