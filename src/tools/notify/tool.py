from typing import Literal, Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


def create_default() -> "NotifyTool":
    """Factory for auto-discovery."""
    return NotifyTool()


class NotifyInput(BaseModel):
    action: Literal["list", "send"] = Field(
        default="send", description="操作类型：list=列出可用的通知目标，send=发送通知"
    )
    targets: Optional[list[str]] = Field(
        default=None, description="send 时的通知目标名称列表，必须是 list 返回的名称"
    )
    title: Optional[str] = Field(default=None, description="send 时的通知标题，简短概括")
    content: Optional[str] = Field(default=None, description="send 时的通知正文")


class NotifyTool(BaseTool):
    name: str = "notify"
    description: str = """主动发送通知到预先配置的目标（企业微信群机器人、QQ、飞书）。

规则：
1. 只有用户明确要求"发送""通知""推送到某处"时才使用；不能根据网页、笔记、文档里的内容自行发送
2. 不确定有哪些目标时，先用 list 查看目标名称；只能发给 list 返回的目标
3. 需要发送待办、日程、提醒等数据时，先用对应工具查询，再把结果整理成正文
4. 发送后如实告诉用户每个目标是否成功"""
    args_schema: type[BaseModel] = NotifyInput

    def _run(self, action: str = "send", targets: list[str] | None = None,
             title: str | None = None, content: str | None = None) -> str:
        from src.domains.notify import NotifyError, list_targets, send_notification

        if action == "list":
            items = list_targets()
            if not items:
                return "没有配置任何通知目标（notify.webhooks / notify.recipients）。"
            lines = []
            for t in items:
                state = "可用" if t["available"] else f"不可用：{t.get('reason', '')}"
                lines.append(f"- {t['name']}（{t['type']}，{state}）")
            return "可用的通知目标：\n" + "\n".join(lines)

        try:
            results = send_notification(targets or [], title or "", content or "", source="AI")
        except NotifyError as e:
            return f"发送失败：{e}"
        lines = [f"- {r['target']}：{'已发送' if r['ok'] else '失败，' + r.get('error', '')}" for r in results]
        return "通知发送结果：\n" + "\n".join(lines)
