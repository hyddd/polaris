"""ReAct agent executor — LLM with tool binding + tool execution loop.

LLM always gets ALL tools and decides autonomously whether to call them.
Supports token-level streaming via LangGraph get_stream_writer().
"""

from datetime import date
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, AIMessage
from src.agent.state import AgentState
import src.config as _cfg  # Read at call time for hot-reload support
from src.tools.registry import ToolRegistry
from src.session.manager import get_session_manager

UNIFIED_SYSTEM_PROMPT = """你是个人效率助手 Polaris。

## 行为准则
- 你拥有若干工具，可以根据需要自主调用（具体工具及参数见函数定义）
- 用户询问"安排""计划""今天有什么事"等时，应同时查看日历日程和待办事项
- 闲聊、打招呼、一般知识问答时不要调用工具，直接友好回复
- 结合对话历史理解上下文
- 删除操作先确认再执行
- 工具返回空结果时如实告知，不编造数据
- 用中文回复，简洁直接
"""

PERSONA_PATH = _cfg.DATA_DIR / "persona.md"


def _load_persona() -> str:
    """Load persona from data/persona.md. Returns empty string if missing."""
    try:
        return PERSONA_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

def _get_all_tools() -> list:
    return ToolRegistry.get_instance().list_tools()


def agent_node(state: AgentState) -> dict:
    tools = _get_all_tools()
    messages = state.get("messages", [])

    session_mgr = get_session_manager()
    compressor = session_mgr.active_session.compressor
    summary, recent = compressor.process(list(messages))

    today = date.today().isoformat()
    persona = _load_persona()
    system_prompt = f"今天是 {today}。\n\n"
    if persona:
        system_prompt += f"[人设]\n{persona}\n\n"
    if summary:
        system_prompt += f"[对话摘要]\n{summary}\n\n"
    system_prompt += UNIFIED_SYSTEM_PROMPT

    llm = ChatOpenAI(model=_cfg.LLM_MODEL, api_key=_cfg.LLM_API_KEY, base_url=_cfg.LLM_BASE_URL, temperature=0.3)
    if tools:
        llm = llm.bind_tools(tools)

    chain = AGENT_PROMPT | llm
    if state.get("streaming"):
        # Streaming path: accumulate AIMessageChunks for token-level SSE events
        full = None
        for chunk in chain.stream({"system_prompt": system_prompt, "messages": recent}):
            full = full + chunk if full is not None else chunk
        response = full
    else:
        response = chain.invoke({"system_prompt": system_prompt, "messages": recent})

    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}

    registry = ToolRegistry.get_instance()
    results = []
    pending_action = None

    for i, tc in enumerate(last_message.tool_calls):
        if tc is None:
            continue
        if isinstance(tc, dict):
            tool_name = tc.get("name", "")
            tool_args = tc.get("args") or {}
        else:
            tool_name = getattr(tc, "name", "")
            tool_args = getattr(tc, "args", None) or {}

        raw_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        fallback_id = f"call_{tool_name}_{i}"
        call_id = raw_id or fallback_id

        # Intercept delete operations — set pending_action instead of executing
        if tool_args.get("action") == "delete":
            target_id = tool_args.get("event_id") or tool_args.get("todo_id") or tool_args.get("filename", "")
            pending_action = {
                "action_type": "delete",
                "target_tool": tool_name,
                "target_id": target_id,
                "description": f"删除 {tool_name} {target_id}",
                "params": tool_args,
                "tool_call_id": call_id,
            }
            results.append(ToolMessage(
                content=f"操作需要确认：删除 {tool_name}「{target_id}」。回复「确认」执行，「取消」放弃。",
                tool_call_id=call_id,
            ))
            continue

        tool = registry.get(tool_name)
        if tool:
            try:
                result = tool.invoke(tool_args)
                result_str = str(result) if not isinstance(result, str) else result
            except Exception as e:
                result_str = f"工具执行出错：{e}"
        else:
            result_str = f"未找到工具：{tool_name}"

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
