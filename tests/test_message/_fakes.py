"""对话链路测试用的替身：真实编译的 LangGraph，只把 agent/tools 两个节点换成脚本。

这样 astream_events 的事件结构、token 流、顶层终态都和线上一致，
测试验证的是路由层真实的保存逻辑，而不是对事件格式的假设。
"""
import json
import threading
from typing import Any
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

import src.agent.graph as graph_mod


def tool_call(name="todo", call_id="call_1", args=None) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": call_id}])


class Script:
    """按顺序给出每次 agent 节点的输出；tools 节点记录调用，可选阻塞到 release 被 set。"""

    def __init__(self, replies, tool_result="工具执行成功", block_tools=False):
        self.replies = list(replies)
        self.calls = 0
        self.tool_runs = []
        self.tool_result = tool_result
        self.tool_started = threading.Event()
        self.tool_release = threading.Event()
        if not block_tools:
            self.tool_release.set()

    def agent_node(self, state):
        msg = self.replies[self.calls]
        self.calls += 1
        if msg.tool_calls:
            return {"messages": [msg]}
        # 走真实的流式模型调用，产生 on_chat_model_stream 事件
        llm = GenericFakeChatModel(messages=iter([msg]))
        full = None
        for chunk in llm.stream("x"):
            full = chunk if full is None else full + chunk
        return {"messages": [AIMessage(content=full.content)]}

    def tool_node(self, state):
        # 和线上 executor.tool_node 一样调用真正的 LangChain 工具，才会产生 on_tool_start/on_tool_end 事件
        last = state["messages"][-1]
        out = []
        for tc in last.tool_calls:
            self.tool_runs.append(tc["name"])
            result = _ScriptTool(name=tc["name"], script=self).invoke(tc.get("args") or {})
            out.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        return {"messages": out}

    def build(self):
        with patch.object(graph_mod, "agent_node", self.agent_node), \
                patch.object(graph_mod, "tool_node", self.tool_node):
            return graph_mod.build_agent_graph()


class _ScriptTool(BaseTool):
    """开始执行后才阻塞，客户端能先看到 tool_call 事件，再在"工具运行中"中断。"""
    description: str = "测试用工具"
    script: Any = None

    def _run(self, *args, **kwargs):
        self.script.tool_started.set()
        self.script.tool_release.wait(10)
        return self.script.tool_result


class FakeRequest:
    async def is_disconnected(self):
        return False


def parse_sse(chunk: str) -> list[tuple[str | None, dict]]:
    frames = []
    for block in chunk.split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        frames.append((event, data))
    return frames


async def open_stream(graph, message, channel="admin", session_id=None):
    """调用真实的 chat_stream 路由，返回 SSE 的 body_iterator。"""
    import src.server.routes.chat as chat
    with patch.object(chat, "get_agent", lambda: graph):
        resp = await chat.chat_stream(
            chat.ChatRequest(message=message, channel=channel, session_id=session_id),
            FakeRequest(),
        )
    return resp.body_iterator


async def run_stream(graph, message, channel="admin", session_id=None, on_frame=None):
    """完整消费一次流式请求，返回全部 (event, data) 帧。"""
    frames = []
    body = await open_stream(graph, message, channel, session_id)
    async for chunk in body:
        for frame in parse_sse(chunk):
            frames.append(frame)
            if on_frame:
                on_frame(frame)
    return frames


def contents(messages) -> list[str]:
    return [m.content for m in messages]
