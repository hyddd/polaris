"""ReAct agent executor — LLM with tool binding + tool execution loop.

LLM always gets ALL tools and decides autonomously whether to call them.
Supports token-level streaming via LangGraph get_stream_writer().
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage
from src.core.llm.openai import create_chat_model

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from src.agent.state import AgentState
from src.agent.interceptors import get_interceptors, init_default_interceptors
from src.core.config import config
from src.core.tools.registry import ToolRegistry
from src.session.manager import get_session_manager

logger = logging.getLogger("polaris.tools")

from src.core.infra import set_context as _set_ctx

# --- Cached LLM instance (rebuilds when config changes) ---

_llm_cache: ChatOpenAI | None = None
_llm_cache_key: tuple[str, str, str] = ("", "", "")  # (model, api_key, base_url)


def clear_llm_cache() -> None:
    """Clear cached LLM instance so next call rebuilds from current config."""
    global _llm_cache, _llm_cache_key
    _llm_cache = None
    _llm_cache_key = ("", "", "")


from src.core.infra import event_bus

# Auto-clear LLM cache when config is reloaded
event_bus.subscribe("config:reload", clear_llm_cache)


def _get_llm() -> ChatOpenAI:
    """Return a cached ChatOpenAI instance, rebuilding if config changed."""
    global _llm_cache, _llm_cache_key
    key = (
        config.get("llm.model", "gpt-4o"),
        config.get("llm.api_key", ""),
        config.get("llm.base_url", "https://api.openai.com/v1"),
    )
    if _llm_cache is None or _llm_cache_key != key:
        _llm_cache = create_chat_model(temperature=0.3, streaming=True)
        _llm_cache_key = key
    return _llm_cache

UNIFIED_SYSTEM_PROMPT = """你是个人效率助手 Polaris。

## 行为准则
- 你拥有若干工具，可以根据需要自主调用（具体工具及参数见函数定义）
- 用户询问"安排""计划""今天有什么事"等时，应同时查看日历日程和待办事项，善用日历、待办等图标
- 闲聊、打招呼、一般知识问答时不要调用工具，直接友好回复
- 结合对话历史理解上下文
- 删除操作先确认再执行
- 工具返回空结果时如实告知，不编造数据
- 信任工具返回的结果。工具返回成功消息（如"已更新""已添加""已删除"）时，直接告知用户操作成功，不要说"遇到了问题""无法完成"等。工具结果就是事实，不需要质疑
- 用中文回复，简洁直接
- 如果你需要知道当前时间，请调用 `get_current_time` 工具获取
"""

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

def _format_persona(persona: dict) -> str:
    """Format persona as character-card style text for the system prompt."""
    if not persona:
        return ""
    parts = []
    name = persona.get("name", "")
    call_user = persona.get("call_user", "")
    identity = persona.get("identity", "")
    personality = persona.get("personality", "")
    if name:
        parts.append(f"你是{name}。")
    if identity:
        parts.append(f"你的身份是{identity}。")
    if personality:
        parts.append(f"你的性格{personality}。")
    if call_user:
        parts.append(f"称呼用户为{call_user}。")
    notes = persona.get("notes", "")
    if notes:
        parts.append(notes)
    return "".join(parts)


def _get_all_tools() -> list:
    return ToolRegistry.get_instance().list_tools()


def agent_node(state: AgentState) -> dict:
    tools = _get_all_tools()
    messages = state.get("messages", [])

    session_mgr = get_session_manager()
    channel = state.get("channel", "default")
    compressor = session_mgr.active_session(channel).compressor
    summary, recent = compressor.process(list(messages))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session = session_mgr.active_session(channel)
    persona = session.persona
    system_prompt = ""
    persona_line = _format_persona(persona)
    if persona_line:
        system_prompt += f"[人设]\n{persona_line}\n\n"
    if summary:
        system_prompt += f"[对话摘要]\n{summary}\n\n"
    system_prompt += UNIFIED_SYSTEM_PROMPT

    # Time removed from system prompt to maximize cache hit rate; LLM calls get_current_time tool when needed
    llm_messages = list(recent)

    llm = _get_llm()
    if tools:
        llm = llm.bind_tools(tools)

    chain = AGENT_PROMPT | llm
    if state.get("streaming"):
        # Streaming path: accumulate AIMessageChunks for token-level SSE events
        full = None
        for chunk in chain.stream({"system_prompt": system_prompt, "messages": llm_messages}):
            full = full + chunk if full is not None else chunk
        response = full if full is not None else AIMessage(content="")
    else:
        response = chain.invoke({"system_prompt": system_prompt, "messages": llm_messages})

    # Update session cache stats from usage_metadata
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = response.usage_metadata
        input_tokens = usage.get("input_tokens", 0)
        cache_read = usage.get("input_token_details", {}).get("cache_read", 0)
        cache_miss = input_tokens - cache_read
        channel = state.get("channel", "default")
        try:
            session_mgr = get_session_manager()
            session = session_mgr.active_session(channel)
            session.cache_stats["hit"] += cache_read
            session.cache_stats["miss"] += cache_miss
            session.cache_stats["calls"] += 1
        except Exception:
            pass

    return {"messages": [response]}


def _parse_tool_call(tc, index: int) -> tuple[str, dict, str]:
    """Extract tool_name, tool_args, call_id from a tool call (dict or object)."""
    if isinstance(tc, dict):
        tool_name = tc.get("name", "")
        tool_args = tc.get("args") or {}
        raw_id = tc.get("id")
    else:
        tool_name = getattr(tc, "name", "")
        tool_args = getattr(tc, "args", None) or {}
        raw_id = getattr(tc, "id", None)
    call_id = raw_id or f"call_{tool_name}_{index}"
    return tool_name, tool_args, call_id


def _find_interception(tool_name: str, tool_args: dict, call_id: str):
    """Run registered interceptors; return InterceptResult or None."""
    for interceptor in get_interceptors():
        if interceptor.should_intercept(tool_name, tool_args):
            return interceptor.intercept(tool_name, tool_args, call_id)
    return None


def _summarize_args(args: dict) -> str:
    """摘要工具参数，避免日志过长"""
    items = []
    for k, v in args.items():
        v_str = str(v)
        if len(v_str) > 50:
            v_str = v_str[:50] + "..."
        items.append(f"{k}={v_str}")
    return " ".join(items)


def _summarize_result(result: str) -> str:
    """摘要工具结果"""
    if len(result) > 100:
        return result[:100] + "..."
    return result


def tool_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}

    init_default_interceptors()
    registry = ToolRegistry.get_instance()
    results = []
    pending_action = None

    session_mgr = get_session_manager()
    channel = state.get("channel", "default")
    current_session_id = session_mgr.active_session(channel).session_id

    parsed = []
    for i, tc in enumerate(last_message.tool_calls):
        if tc is None:
            continue
        parsed.append(_parse_tool_call(tc, i))

    # Skip interception if batch has non-interceptable calls (e.g., update with sub-deletes)
    has_non_interceptable = any(
        _find_interception(name, args, cid) is None
        for name, args, cid in parsed
    )

    for tool_name, tool_args, call_id in parsed:
        if not has_non_interceptable:
            result = _find_interception(tool_name, tool_args, call_id)
            if result:
                pending_action = result.pending_action
                results.append(ToolMessage(
                    content=result.tool_message_content,
                    tool_call_id=call_id,
                ))
                continue

        # Set tool context for tools that need channel/session info
        _set_ctx(channel=channel, session_id=current_session_id, user_id=channel.split(":", 1)[-1] if ":" in channel else "")

        start_time = time.time()
        logger.info(f"[tool] {tool_name} start args={_summarize_args(tool_args)}")

        tool = registry.get(tool_name)
        if tool:
            try:
                from src.core.observability import metrics
                metrics.inc(f"tool.calls.{tool_name}")
                with metrics.timer(f"tool.latency.{tool_name}"):
                    result = tool.invoke(tool_args)
                result_str = str(result) if not isinstance(result, str) else result
                duration_ms = (time.time() - start_time) * 1000
                logger.info(f"[tool] {tool_name} done duration={duration_ms:.0f}ms result={_summarize_result(result_str)}")
                if duration_ms > 5000:
                    logger.warning(f"[tool] {tool_name} slow query: {duration_ms:.0f}ms")
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                logger.error(f"[tool] {tool_name} failed duration={duration_ms:.0f}ms error={e}")
                from src.core.errors import format_tool_error
                result_str = format_tool_error(e)
        else:
            duration_ms = (time.time() - start_time) * 1000
            logger.warning(f"[tool] {tool_name} not_found duration={duration_ms:.0f}ms")
            from src.core.errors import NotFoundError, format_tool_error
            result_str = format_tool_error(NotFoundError(f"未找到工具：{tool_name}"))

        results.append(ToolMessage(content=result_str, tool_call_id=call_id))

    out = {"messages": results}
    if pending_action:
        out["pending_action"] = pending_action
    return out


def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"
