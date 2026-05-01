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


async def _api_get(path: str) -> dict | None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{AGENT_SERVER}{path}")
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def _api_post(path: str, data: dict = None) -> dict | None:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{AGENT_SERVER}{path}", json=data or {})
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def _show_session_panel():
    """Display session list with action buttons."""
    data = await _api_get("/sessions")
    if not data:
        await cl.Message(content="无法获取会话列表").send()
        return

    active_id = data.get("active_session_id", "")
    sessions = data.get("sessions", [])

    if not sessions:
        await cl.Message(content="暂无会话").send()
        return

    elements = []
    for s in sessions:
        sid = s["session_id"]
        name = s["name"]
        is_active = sid == active_id
        msg_count = s.get("message_count", 0)
        summary = s.get("summary", "")[:50]
        marker = "🟢 " if is_active else ""

        card_content = f"{marker}**{name}**\n"
        card_content += f"消息: {msg_count}"
        if summary:
            card_content += f" | {summary}..."

        actions = []
        if not is_active:
            actions.append(cl.Action(name="switch_session", label="切换", payload={"sid": sid}))
        actions.append(cl.Action(name="rename_session", label="重命名", payload={"sid": sid}))
        if len(sessions) > 1:
            actions.append(cl.Action(name="delete_session", label="删除", payload={"sid": sid}))

        elements.append(
            cl.Text(name=sid, content=card_content, display="inline")
        )
        # Attach actions as separate elements
        for a in actions:
            elements.append(a)

    # Add "new session" action
    elements.append(cl.Action(name="new_session", label="➕ 新建会话", payload={}))

    await cl.Message(content="📋 **会话管理**", elements=elements).send()


@cl.on_chat_start
async def start():
    data = await _api_get("/sessions")
    if data:
        active_id = data.get("active_session_id", "")
        for s in data.get("sessions", []):
            if s["session_id"] == active_id:
                await cl.Message(
                    content=f"当前会话: **{s['name']}** ({active_id})\n\n"
                    "你好！我是 Polaris，你的个人效率助手。\n"
                    "• 发送消息直接对话\n"
                    "• 点击下方管理会话",
                    elements=[
                        cl.Action(name="show_sessions", label="📋 会话管理", payload={}),
                    ],
                ).send()
                return

    await cl.Message(
        content="你好！我是 Polaris。",
        elements=[cl.Action(name="show_sessions", label="📋 会话管理", payload={})],
    ).send()


@cl.action_callback("show_sessions")
async def on_show_sessions(action: cl.Action):
    await _show_session_panel()


@cl.action_callback("switch_session")
async def on_switch_session(action: cl.Action):
    sid = action.payload.get("sid", "")
    result = await _api_post(f"/sessions/{sid}/activate")
    if result and result.get("ok"):
        name = result.get("active_session", sid)
        await cl.Message(content=f"已切换到会话: **{name}**").send()
    else:
        await cl.Message(content="切换失败").send()


@cl.action_callback("new_session")
async def on_new_session(action: cl.Action):
    # Ask user for session name
    name_msg = await cl.AskUserMessage(content="请输入新会话名称:", timeout=60).send()
    if not name_msg or not name_msg.strip():
        return

    result = await _api_post("/sessions", {"name": name_msg.strip()})
    if result:
        sid = result.get("session_id", "")
        name = result.get("name", "")
        await cl.Message(content=f"已创建并切换到会话: **{name}** ({sid})").send()
    else:
        await cl.Message(content="创建失败").send()


@cl.action_callback("rename_session")
async def on_rename_session(action: cl.Action):
    sid = action.payload.get("sid", "")
    name_msg = await cl.AskUserMessage(content="输入新名称:", timeout=60).send()
    if not name_msg or not name_msg.strip():
        return

    # Use the /rename command through chat API
    result = await _api_post("/chat", {"message": f"/rename {name_msg.strip()}", "channel": "web"})
    if result:
        await cl.Message(content=f"已重命名: **{name_msg.strip()}**").send()
    else:
        await cl.Message(content="重命名失败").send()


@cl.action_callback("delete_session")
async def on_delete_session(action: cl.Action):
    sid = action.payload.get("sid", "")
    # Ask for confirmation
    confirm = await cl.AskUserMessage(content=f"确认删除会话 {sid}？输入「确认」继续:", timeout=30).send()
    if not confirm or confirm.strip() != "确认":
        await cl.Message(content="已取消删除").send()
        return

    # Use DELETE endpoint or send /delete command
    try:
        async with httpx.AsyncClient() as client:
            r = await client.delete(f"{AGENT_SERVER}/sessions/{sid}")
            if r.status_code == 200:
                await cl.Message(content="已删除会话").send()
            else:
                await cl.Message(content="删除失败").send()
    except Exception:
        await cl.Message(content="删除失败").send()


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
