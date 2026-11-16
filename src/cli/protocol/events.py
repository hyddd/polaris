"""客户端内部事件。UI 只认这里的事件，不直接依赖服务端的 SSE 格式。

将来接 v2 协议时只需新增一个适配器，产出同样的事件。
"""
from dataclasses import dataclass, field

# 事件类型
TEXT_DELTA = "text_delta"            # 模型回复片段
MESSAGE = "message"                  # 一整块独立内容（命令输出、确认/取消结果）
TOOL_STARTED = "tool_started"
TOOL_FINISHED = "tool_finished"      # 工具返回了结果；不代表业务一定成功
WARNING = "warning"                  # 协议层的非致命问题（未知事件、坏帧）
FAILED = "failed"                    # 服务端报错；之后即使收到 done 也保持失败
TERMINAL = "terminal"                # 本次请求的唯一终态事件

# 终态 status
STATUS_UNKNOWN = "unknown"                    # 旧协议收到 done：回答接收完了，但业务提交未经确认
STATUS_FAILED = "failed"
STATUS_INTERRUPTED = "interrupted_unknown"    # 没收到 done 连接就断了
STATUS_CLIENT_INTERRUPTED = "client_interrupted"  # 用户在客户端中断等待


@dataclass
class Event:
    type: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, **self.data}
