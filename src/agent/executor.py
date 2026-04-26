"""ReAct agent executor — LLM with tool binding + tool execution loop.

LLM always gets ALL tools and decides autonomously whether to call them.
No intent-based routing — the LLM self-determines intent from context.
"""

import os
from datetime import date
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, AIMessage
from src.state import AgentState
import src.config as _cfg  # Read at call time for hot-reload support
from src.tools.registry import ToolRegistry
from src.session_manager import get_session_manager

UNIFIED_SYSTEM_PROMPT = """你是个人效率助手 Polaris。

## 可用工具
你拥有以下工具，可以根据需要自主决定是否调用。每个工具都有明确的参数类型，直接填入即可，不需要拼字符串。

- **calendar** — 管理日历事件
  参数：action(list/search/create/update/delete), date(日期), title, time, keyword, event_id
  - 查看当日日程 → action="list", date="今天日期"
  - 搜索事件 → action="search", keyword="关键词"
  - 创建事件 → action="create", date, title, time, attendees, duration
  - 修改事件 → action="update", event_id, updates={...}
  - 删除事件 → action="delete", event_id

- **todo** — 管理待办事项
  参数：action(list/search/create/done/delete), status(active/all/pending/done), title, priority(high/medium/low), due, keyword, todo_id
  - 查看当前待办（默认）→ action="list", status="active"
  - 查看所有含已完成 → action="list", status="all"
  - 创建 → action="create", title, priority, due
  - 标记完成 → action="done", todo_id
  - 删除 → action="delete", todo_id

- **notes** — 管理笔记
  参数：action(list/read/create/search/archive), title, content, tags, keyword, filename
  - 列出笔记 → action="list"
  - 读取 → action="read", filename
  - 创建 → action="create", title, content, tags
  - 搜索（关键词）→ action="search", keyword
  - 归档 → action="archive", filename

- **rag_search** — 语义搜索笔记。参数：query(自然语言查询)

## 行为准则
- 根据用户消息自主判断是否需要调用工具
- 闲聊、打招呼、一般知识问答时不要调用工具，直接友好回复
- 用户明确要求操作日程/笔记/待办时才调用对应工具
- 结合对话历史理解上下文。比如用户之前提到某个会议，后续说"帮我准备一下"，应理解指的是那个会议
- 删除操作先确认再执行
- 工具返回空结果时如实告知，不编造数据
- 用中文回复，简洁直接
"""

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

ALL_TOOLS = ["calendar", "todo", "notes", "rag_search"]


def _get_all_tools() -> list:
    registry = ToolRegistry.get_instance()
    return [registry.get(name) for name in ALL_TOOLS if registry.get(name)]


def agent_node(state: AgentState) -> dict:
    tools = _get_all_tools()
    messages = state.get("messages", [])

    # Use the active session's compressor
    session_mgr = get_session_manager()
    compressor = session_mgr.active_session.compressor
    summary, recent = compressor.process(list(messages))

    # Build system prompt with summary
    today = date.today().isoformat()
    system_prompt = f"今天是 {today}。\n\n"
    if summary:
        system_prompt += f"[对话摘要]\n{summary}\n\n"
    system_prompt += UNIFIED_SYSTEM_PROMPT

    llm = ChatOpenAI(model=_cfg.LLM_MODEL, api_key=_cfg.LLM_API_KEY, base_url=_cfg.LLM_BASE_URL, temperature=0.3)
    if tools:
        llm = llm.bind_tools(tools)

    chain = AGENT_PROMPT | llm
    response = chain.invoke({"system_prompt": system_prompt, "messages": recent})

    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_message = messages[-1]

    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {}

    registry = ToolRegistry.get_instance()
    results = []
    for tc in last_message.tool_calls:
        if tc is None:
            continue
        if isinstance(tc, dict):
            tool_name = tc.get("name", "")
            tool_args = tc.get("args") or {}
        else:
            tool_name = getattr(tc, "name", "")
            tool_args = getattr(tc, "args", None) or {}
        tool = registry.get(tool_name)

        if tool:
            try:
                result = tool.invoke(tool_args)
                result_str = str(result) if not isinstance(result, str) else result
            except Exception as e:
                result_str = f"工具执行出错：{e}"
        else:
            result_str = f"未找到工具：{tool_name}"

        results.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    return {"messages": results}


def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"
