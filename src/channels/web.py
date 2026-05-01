"""Chainlit Web UI channel — SSE streaming client to Agent Server.

Run: source venv/bin/activate && chainlit run src/chainlit_app.py

The actual @cl decorators live here so Chainlit picks them up at import time.
chainlit_app.py is a thin entry point that imports from this module.
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
    msg = cl.Message(content="")
    await msg.send()

    thinking_text = ""
    response_text = ""
    has_tool_calls = False
    tool_steps = {}

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

                        if event_type == "tool_call":
                            has_tool_calls = True
                            if thinking_text.strip():
                                think_step = cl.Step(name="💭 思考推理", type="thought")
                                think_step.output = thinking_text.strip()
                                await think_step.send()
                                thinking_text = ""

                            tool_name = data.get("tool", "unknown")
                            tool_args = data.get("args", {})
                            call_id = data.get("call_id", tool_name)
                            step = cl.Step(name=f"🔧 调用工具: {tool_name}", type="tool")
                            step.input = json.dumps(tool_args, ensure_ascii=False, indent=2)
                            step.output = "执行中..."
                            await step.send()
                            tool_steps[call_id] = step

                        elif event_type == "tool_result":
                            tool_name = data.get("tool", "unknown")
                            result = data.get("result", "")
                            call_id = data.get("call_id", tool_name)
                            if call_id in tool_steps:
                                step = tool_steps[call_id]
                                step.output = result
                                await step.update()
                                del tool_steps[call_id]

                        elif event_type == "message":
                            response_text = data.get("content", "")

                        elif event_type == "error":
                            response_text = f"❌ {data.get('error', '未知错误')}"

                        elif not event_type:
                            token = data.get("token", "")
                            if token:
                                if has_tool_calls:
                                    response_text += token
                                else:
                                    thinking_text += token

                        display = response_text or thinking_text or "处理中..."
                        msg.content = display
                        await msg.update()

    except httpx.ConnectError:
        msg.content = "无法连接到 Agent Server。请先启动 `python run.py`"
        await msg.update()
    except Exception as e:
        msg.content = f"出错: {e}"
        await msg.update()
