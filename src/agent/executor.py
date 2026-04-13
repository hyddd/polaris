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
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
from src.tools.registry import ToolRegistry
from src.memory.compressor import ConversationCompressor

UNIFIED_SYSTEM_PROMPT = """你是个人效率助手 Polaris。

## 可用工具
你拥有以下工具，可以根据需要自主决定是否调用：

- **calendar** — 查询、创建、修改、删除日历事件
  - 查询当日日程：list <今天日期>
  - 查询指定日期：list YYYY-MM-DD
  - 搜索事件：search <关键词>
  - 创建事件：create {"date":"YYYY-MM-DD","time":"HH:MM","title":"..."}
  - 修改事件：update <event_id> {...}
  - 删除事件：delete <event_id>
  注意：用户说"今天有什么安排"时，传入今天的日期

- **todo** — 管理待办事项
  - 查看当前待办（默认，不含已完成）：list active
  - 查看所有（含已完成）：list all
  - 只看已完成的：list done
  - 只看未开始的：list pending
  - 搜索：search <关键词>
  - 创建：create {"title":"...","priority":"high|medium|low","due":"YYYY-MM-DD"}
  - 标记完成：done <todo_id>
  - 删除：delete <todo_id>
  注意：用户说"查看待办""有什么待办"时默认用 list active；说"查看所有待办""包括已完成的"时才用 list all

- **notes** — 管理笔记
  - 列出笔记：list
  - 读取：read <文件名>
  - 创建：create {"title":"...","content":"...","tags":[...]}
  - 搜索（关键词）：search <关键词>
  - 归档：archive <文件名>

- **rag_search** — 语义搜索笔记内容。输入自然语言查询即可

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


# Global compressor instance
_compressor = None


def _get_compressor() -> ConversationCompressor:
    global _compressor
    if _compressor is None:
        model_max = int(os.getenv("POLARIS_MODEL_MAX_CONTEXT", "200000"))
        threshold = float(os.getenv("POLARIS_COMPRESSION_THRESHOLD", "0.8"))
        _compressor = ConversationCompressor(
            model_max_context=model_max,
            compression_threshold=threshold,
        )
    return _compressor


def agent_node(state: AgentState) -> dict:
    tools = _get_all_tools()
    messages = state.get("messages", [])

    # Compress: summarize old messages, trim recent to token budget
    compressor = _get_compressor()
    summary, recent = compressor.process(list(messages))

    # Build system prompt with summary
    today = date.today().isoformat()
    system_prompt = f"今天是 {today}。\n\n"
    if summary:
        system_prompt += f"[对话摘要]\n{summary}\n\n"
    system_prompt += UNIFIED_SYSTEM_PROMPT

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
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
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
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
