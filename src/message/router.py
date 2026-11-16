"""Message processing logic — synchronous entry point and internal implementation."""
import json
import logging
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import SessionManager
from src.core.infra import set_context as _set_ctx
from src.core.infra import hold_session_lock, SessionBusyError
from src.session.commands import _SEPARATOR
from src.message.models import Attachment
from src.message.file_parser import parse_file
from src.message.turn import TurnRecorder

# 等同一会话上一条消息处理完的最长时间。QQ/飞书消息会在这里排队。
LOCK_WAIT_SECONDS = 120
BUSY_REPLY = "该会话正在处理上一条消息，请稍后再试。"


def _build_message(text: str, attachments: list[Attachment] | None) -> HumanMessage:
    """构造 HumanMessage，支持文本+附件。"""
    if not attachments:
        return HumanMessage(content=text)

    content = []
    # 添加图片附件
    for att in attachments:
        if att.type == "image":
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{att.mime_type};base64,{att.data}"}
            })
        elif att.type == "file":
            # 文件解析为文本注入上下文
            file_text = parse_file(att)
            if file_text:
                content.append({
                    "type": "text",
                    "text": f"[文件: {att.filename}]\n{file_text}"
                })

    # 添加用户文本
    content.append({"type": "text", "text": text})
    return HumanMessage(content=content)


async def process_message(text: str, session_mgr: SessionManager, channel: str = "default", attachments: list[Attachment] | None = None) -> list[tuple[str, list[dict]]]:
    """统一消息处理入口。返回消息列表（可能多条）。per-session 锁保证同一会话串行处理，不同会话可并发。

    锁用 hold_session_lock 异步等待：这里跑在事件循环里，阻塞式 acquire 会卡死整个循环，
    而持锁的流式请求正需要这个循环才能结束并释放锁。
    """
    session, switched = session_mgr.resolve_session(channel)
    session_id = session.session_id
    try:
        async with hold_session_lock(session_id, timeout=LOCK_WAIT_SECONDS):
            # 在锁内设置 context，防止并发覆盖
            user_id = channel.split(":", 1)[-1] if ":" in channel else ""
            _set_ctx(channel=channel, session_id=session_id, user_id=user_id)

            results = []
            if switched:
                results.append(("⚠️ 你之前绑定的会话已被删除，已自动切换到 default 会话。", []))

            response_text, tool_calls = await _process_message_impl(
                text, session_mgr, channel, attachments, session_id=session_id)

            if _SEPARATOR in response_text:
                parts = response_text.split(_SEPARATOR, 1)
                results.append((parts[0], []))
                results.append((parts[1], []))
            else:
                results.append((response_text, tool_calls))
            return results
    except SessionBusyError:
        return [(BUSY_REPLY, [])]


async def _process_message_impl(text: str, session_mgr: SessionManager, channel: str = "default",
                                attachments: list[Attachment] | None = None,
                                session_id: str | None = None) -> tuple[str, list[dict]]:
    """统一消息处理入口。系统命令提前处理，不进 agent graph。

    session_id 是调用方已经加锁的会话。等锁期间 channel 的激活会话可能被切走，
    必须用它而不是重新按 channel 解析，否则会在没加锁的会话上读写。
    """
    # 系统命令提前处理，不进 agent graph、不残留记忆
    stripped = text.strip()
    if stripped.startswith("/"):
        from src.session.commands import handle_command
        response = handle_command(stripped, session_mgr, channel)
        if response:
            return (response, [])

    session = session_mgr.get(session_id) if session_id else None
    if session is None:
        session = session_mgr.active_session(channel)
    memory = session.memory
    agent = get_agent()

    # Save pre-invoke state for rollback on error
    previous_messages = memory.get_messages()

    # Create HumanMessage with ID for retry/edit support
    human_msg = _build_message(text, attachments)
    memory.add_message(human_msg)
    human_msg_id = memory.get_message_id(human_msg)
    turn_start = len(previous_messages) + 1

    state_messages = previous_messages + [human_msg]

    state = AgentState(
        messages=state_messages,
        intent="",
        user_profile=memory.get_profile(),
        tool_results={},
        final_response="",
        needs_clarification=False,
        pending_action=session.pending_action,
        channel=channel,
        session_id=session.session_id,
    )

    result = None
    try:
        # ainvoke：同步节点由 LangGraph 放进线程池跑，不阻塞事件循环
        result = await agent.ainvoke(state)
        response_text = _extract_response(result)
        tool_calls = _extract_tool_calls(result)
    except Exception as e:
        # 只在命令未修改内存时回滚（命令可能已清空/修改了内存）
        if not (result and result.get("final_response")):
            memory.replace_keeping_appended(turn_start, previous_messages)
        agent_logger = logging.getLogger("polaris.agent")

        # If agent.invoke succeeded (tools may have executed) but post-processing failed,
        # extract tool results from the result state for audit trail.
        tool_results = _extract_tool_results(result) if result is not None else []
        if tool_results:
            agent_logger.error(
                "LLM 处理失败但以下工具操作可能已生效，需手动检查：\n"
                f"{json.dumps(tool_results, ensure_ascii=False, indent=2)}\n"
                f"错误: {e}"
            )
        else:
            agent_logger.error(f"Agent 调用失败: {e}", exc_info=True)
        session_mgr.save_session(session.session_id)
        return (f"抱歉，处理请求时出错：{e}", [])

    turn = TurnRecorder(previous_messages, human_msg)
    turn.final_state = result
    session.pending_action = turn.pending_action()
    memory.replace_keeping_appended(turn_start, turn.history())

    if turn.notice:
        # confirm_node 返回的确认/取消结果，不残留记忆；pending_action 已清空，需要落盘
        session_mgr.save_session(session.session_id)
        return (response_text, tool_calls)

    session_mgr.record_message(text, response_text, channel, session_id=session.session_id)

    return (response_text, tool_calls)


# --- Helpers ---

def _extract_response(result: dict) -> str:
    """Extract the final text response from agent result."""
    response = result.get("final_response", "")
    if response:
        return response
    messages = result.get("messages", [])
    for m in reversed(messages):
        if (hasattr(m, "content") and m.content
            and m.type == "ai"
            and not (hasattr(m, "tool_calls") and m.tool_calls)):
            return m.content
    return "抱歉，处理出错了。"


def _extract_tool_results(state: dict) -> list[dict]:
    """Extract tool execution results from state for audit logging.

    Looks for ToolMessage-like objects (messages with tool_call_id) and
    returns their key info (tool_call_id, name, truncated content).
    Returns the most recent 10 tool results.
    """
    messages = state.get("messages", []) if isinstance(state, dict) else []
    results = []
    for msg in messages:
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            results.append({
                "tool_call_id": msg.tool_call_id,
                "name": getattr(msg, "name", "unknown"),
                "content": str(getattr(msg, "content", ""))[:200],
            })
    return results[-10:]


def _extract_tool_calls(result: dict) -> list[dict]:
    """Extract tool call summaries from agent result."""
    calls = []
    messages = result.get("messages", [])
    for m in messages:
        if hasattr(m, "tool_calls") and m.tool_calls:
            for tc in m.tool_calls:
                if isinstance(tc, dict):
                    calls.append({
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args") or {},
                    })
                else:
                    calls.append({
                        "tool": getattr(tc, "name", "unknown"),
                        "args": getattr(tc, "args", {}) or {},
                    })
    return calls
