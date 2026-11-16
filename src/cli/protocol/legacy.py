"""旧聊天协议（POST /api/chat/stream）到内部事件的适配。

旧协议没有 run ID、事件 ID、结构化终态，所以：
- 收到 done 只表示"服务端发送结束"，终态 status 一律是 unknown（业务提交未确认）；
- error 之后即使再收到 done，终态也保持 failed；
- 没收到 done 连接就断了 → interrupted_unknown，绝不自动重发。
"""
import json

from .events import (
    Event, TEXT_DELTA, MESSAGE, TOOL_STARTED, TOOL_FINISHED, WARNING, FAILED, TERMINAL,
    STATUS_UNKNOWN, STATUS_FAILED, STATUS_INTERRUPTED,
)
from .sse import SSEFrame


class LegacyAdapter:
    def __init__(self):
        self.session_id: str | None = None
        self._failed: str | None = None
        self._terminated = False
        self._anon_calls = 0

    @property
    def terminated(self) -> bool:
        return self._terminated

    def handle(self, frame: SSEFrame) -> list[Event]:
        if self._terminated:
            return [Event(WARNING, {"message": f"终态之后又收到事件：{frame.event or 'data'}"})]
        try:
            payload = json.loads(frame.data) if frame.data else {}
        except json.JSONDecodeError:
            return [Event(WARNING, {"message": f"无法解析的事件数据（{frame.event or 'data'}）"})]
        if not isinstance(payload, dict):
            return [Event(WARNING, {"message": "事件数据不是对象"})]

        kind = frame.event
        if kind is None:
            token = payload.get("token")
            if isinstance(token, str) and token:
                return [Event(TEXT_DELTA, {"text": token})]
            return []
        if kind == "message":
            return [Event(MESSAGE, {"content": str(payload.get("content", ""))})]
        if kind == "tool_call":
            return [Event(TOOL_STARTED, {
                "call_id": self._call_id(payload),
                "tool": str(payload.get("tool", "unknown")),
                "args": payload.get("args", {}),
            })]
        if kind == "tool_result":
            return [Event(TOOL_FINISHED, {
                "call_id": self._call_id(payload, finishing=True),
                "tool": str(payload.get("tool", "unknown")),
                "result": str(payload.get("result", "")),
            })]
        if kind == "error":
            # 只保留 error 文本；服务端附带的 traceback 不往终端上展示
            self._failed = str(payload.get("error", "服务端错误"))
            return [Event(FAILED, {"error": self._failed})]
        if kind == "done":
            self._terminated = True
            self.session_id = payload.get("session_id") or self.session_id
            return [self._terminal(STATUS_FAILED if self._failed else STATUS_UNKNOWN)]
        return [Event(WARNING, {"message": f"未知事件类型：{kind}"})]

    def finish(self) -> list[Event]:
        """连接结束时调用；没收到 done 就补一个 interrupted 终态。"""
        if self._terminated:
            return []
        self._terminated = True
        return [self._terminal(STATUS_FAILED if self._failed else STATUS_INTERRUPTED)]

    def _terminal(self, status: str) -> Event:
        return Event(TERMINAL, {
            "status": status,
            "session_id": self.session_id,
            "durability": "unverified",
            "error": self._failed,
        })

    def _call_id(self, payload: dict, finishing: bool = False) -> str:
        cid = payload.get("call_id")
        if cid:
            return str(cid)
        # 缺 ID 时只能在本次流内按顺序降级关联
        if not finishing:
            self._anon_calls += 1
        return f"anon-{self._anon_calls}"
