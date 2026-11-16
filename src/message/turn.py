"""一轮对话结束后，决定往会话里写回什么。

流式接口（chat.py）和统一消息入口（router.py）共用这里的规则，保证两条路径落盘语义一致：

- 正常完成：写回 LangGraph 顶层终态里的完整消息链。
  注意节点（agent/tools）的 on_chain_end 只带本步增量，不能当完整历史用。
- 确认/取消（confirm 节点直接给出 final_response）：不残留记忆，历史回到本轮开始前；
  final_response 要单独回给客户端，它不是模型 token，流里不会出现。
- 中断或出错：工具可能已经生效，历史里必须留下痕迹，否则下一轮模型不知道做过什么、可能重做。
  已经发出但没拿到结果的工具调用补一条“结果未知”的 ToolMessage，保证消息序列对模型 API 合法。
  如果本轮什么都还没发生（没有工具调用、没有输出），整轮回滚，相当于没发过。
"""
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

UNKNOWN_TOOL_RESULT = "（本轮被中断，这个工具调用的执行结果未知；可能已经生效，请先核对再决定是否重做）"
INTERRUPTED_NOTE = "（本轮回复被中断，未完成）"


def _call_id(call) -> str | None:
    return call.get("id") if isinstance(call, dict) else getattr(call, "id", None)


def close_dangling_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """给没有对应 ToolMessage 的工具调用补上“结果未知”的 ToolMessage。"""
    out: list[BaseMessage] = []
    waiting: list[str] = []

    def flush():
        out.extend(ToolMessage(content=UNKNOWN_TOOL_RESULT, tool_call_id=cid) for cid in waiting)
        waiting.clear()

    for m in messages:
        if isinstance(m, ToolMessage):
            if m.tool_call_id in waiting:
                waiting.remove(m.tool_call_id)
            out.append(m)
            continue
        flush()
        out.append(m)
        if isinstance(m, AIMessage) and m.tool_calls:
            waiting.extend(cid for cid in (_call_id(c) for c in m.tool_calls) if cid)
    flush()
    return out


class TurnRecorder:
    """记录一轮运行的产出，结束时给出要写回的历史。

    base: 本轮开始前的历史；human: 本轮用户消息（已在 base 之后追加进内存）。
    """

    def __init__(self, base: list[BaseMessage], human: BaseMessage):
        self.base = list(base)
        self.human = human
        self.final_state: dict | None = None   # 顶层终态，正常跑完才有
        self.deltas: list[BaseMessage] = []    # 各节点按顺序产生的消息增量
        self.segment_text = ""                 # 最近一次模型调用里已流出、还没结束的文本
        self.error: BaseException | None = None
        self._pending_action = None
        self._pending_seen = False

    # --- 流式事件 ---

    def feed(self, event: dict) -> str:
        """吃一条 astream_events(v2) 事件；若是模型 token 则返回该 token 文本。"""
        kind = event.get("event", "")
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            text = getattr(chunk, "content", "") if chunk is not None else ""
            if isinstance(text, str) and text:
                self.segment_text += text
                return text
            return ""
        if kind == "on_chain_end":
            output = event.get("data", {}).get("output")
            if not isinstance(output, dict):
                return ""
            if not event.get("parent_ids"):
                # 顶层图结束：完整终态
                self.final_state = output
            elif event.get("name") == event.get("metadata", {}).get("langgraph_node"):
                # 图节点本身结束（不是节点内部的子链）：消息增量
                self.deltas.extend(output.get("messages") or [])
                if "pending_action" in output:
                    self._pending_action = output["pending_action"]
                    self._pending_seen = True
                if event.get("name") == "agent":
                    self.segment_text = ""
        return ""

    # --- 结果 ---

    @property
    def completed(self) -> bool:
        return self.final_state is not None

    @property
    def notice(self) -> str:
        """确认/取消节点直接给出的结果文本；没有则为空串。"""
        return (self.final_state or {}).get("final_response") or ""

    @property
    def reply_text(self) -> str:
        """正常完成时最后一条 AI 文本回复。"""
        if self.notice:
            return self.notice
        for m in reversed((self.final_state or {}).get("messages") or []):
            if isinstance(m, AIMessage) and m.content and not m.tool_calls:
                return m.content if isinstance(m.content, str) else str(m.content)
        return ""

    def pending_action(self):
        if self.final_state is not None:
            return self.final_state.get("pending_action")
        return self._pending_action if self._pending_seen else None

    def history(self) -> list[BaseMessage]:
        """本轮结束后会话应有的完整历史。"""
        if self.final_state is not None:
            if self.notice:
                return list(self.base)
            msgs = self.final_state.get("messages")
            if msgs:
                return list(msgs)
            return self.base + [self.human]

        produced = close_dangling_tool_calls(self.deltas)
        if not produced and not self.segment_text:
            return list(self.base)
        note = f"（本轮处理出错：{self.error}）" if self.error else INTERRUPTED_NOTE
        tail = f"{self.segment_text}\n\n{note}" if self.segment_text else note
        return self.base + [self.human] + produced + [AIMessage(content=tail)]
