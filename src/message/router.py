"""Message processing logic — synchronous entry point and internal implementation."""
import json
import logging
from langchain_core.messages import HumanMessage, AIMessage

from src.agent.graph import get_agent
from src.agent.state import AgentState
from src.session.manager import SessionManager
from src.core.context import set_context as _set_ctx
from src.core.lock import get_session_lock


async def process_message(text: str, session_mgr: SessionManager, channel: str = "default") -> tuple[str, list[dict]]:
    """统一消息处理入口。per-session 锁保证同一会话串行处理，不同会话可并发。"""
    session, switched = session_mgr.resolve_session(channel)
    session_id = session.session_id
    with get_session_lock(channel, session_id):
        # 在锁内设置 context，防止并发覆盖
        user_id = channel.split(":", 1)[-1] if ":" in channel else ""
        _set_ctx(channel=channel, session_id=session_id, user_id=user_id)
        if switched:
            return ("你之前绑定的会话已被删除，已自动切换到 default 会话。", [])
        return await _process_message_impl(text, session_mgr, channel)


async def _process_message_impl(text: str, session_mgr: SessionManager, channel: str = "default") -> tuple[str, list[dict]]:
    """统一消息处理入口。

    系统命令由 Agent Graph 的 command_node 拦截，不经过 LLM，不残留记忆。
    """
    session = session_mgr.active_session(channel)
    memory = session.memory
    agent = get_agent()

    # Save pre-invoke state for rollback on error
    previous_messages = memory.get_messages()

    # Create HumanMessage with ID for retry/edit support
    human_msg = HumanMessage(content=text)
    memory.add_message(human_msg)
    human_msg_id = memory.get_message_id(human_msg)

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
    )

    result = None
    try:
        result = agent.invoke(state)
        response_text = _extract_response(result)
        tool_calls = _extract_tool_calls(result)
    except Exception as e:
        # Roll back memory and return error
        memory.set_messages(previous_messages)
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
        return (f"抱歉，处理请求时出错：{e}", [])

    # Save pending_action from result
    session.pending_action = result.get("pending_action")

    if result.get("final_response"):
        # 系统命令不残留记忆
        memory.set_messages(previous_messages)
        return (response_text, tool_calls)

    # Persist only user msg + final AI reply. Strip intermediate tool messages.
    # Keep the original human message with its ID
    memory.set_messages(previous_messages + [
        human_msg,
        AIMessage(content=response_text),
    ])
    session_mgr.record_message(text, response_text, channel)

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
