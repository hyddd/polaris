"""ReAct agent executor — LLM with tool binding + tool execution loop."""

import os
from datetime import date
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, AIMessage
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
from src.tools.registry import ToolRegistry
from src.memory.compressor import ConversationCompressor


UNIFIED_SYSTEM_PROMPT = """你是个人效率助手 Polaris，一个聪明友好的 AI 助手。

## 你的能力
你可以帮用户完成以下操作：

1. **查看日程** — 查询当天的日历事件和待办事项，生成今日计划
   - 使用 calendar 工具查询日历，使用 todo 工具查询待办
2. **会议准备** — 查找会议信息、搜索相关笔记、生成准备清单
   - 使用 calendar、rag_search、todo 工具
3. **搜索笔记** — 语义搜索历史笔记
   - 使用 rag_search 工具
4. **快速记录** — 一句话创建日程、笔记或待办
   - 创建日程用 calendar，记录笔记用 notes，添加待办用 todo
   - 将自然语言日期（明天、周五）转换为 YYYY-MM-DD 格式
5. **管理信息** — 修改或删除已有的日程和待办
   - 修改/删除：先搜索找到目标，确认后再执行

## 工具使用规则
- 用户消息明确属于上述 5 类操作时才调用工具
- 查询/列表类操作可以直接调用
- 创建类操作直接执行，成功后告知
- 删除类操作先搜索确认，再执行
- 普通闲聊、打招呼、一般知识问答时不要调用工具，友好自然地用中文回复
- 如果用户意图模糊，友好追问以明确意图

## 回复风格
- 用中文，简洁直接
- 日程按时间排列，待办按优先级排列
- 工具返回空结果时如实告知用户，而不是编造数据
"""

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

# Non-chat intents get ALL tools; agent decides which to use based on context
TOOL_INTENTS = {"daily_planning", "meeting_prep", "knowledge_search", "quick_capture", "manage"}
ALL_TOOLS = ["calendar", "todo", "notes", "rag_search"]


def _get_tools(intent: str) -> list:
    registry = ToolRegistry.get_instance()
    if intent in TOOL_INTENTS:
        return [registry.get(name) for name in ALL_TOOLS if registry.get(name)]
    return []


# Global compressor instance (in-process; summary persists across calls in same session)
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
    intent = state.get("intent", "chat")
    tools = _get_tools(intent)
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

    # Final answer — store it in final_response for the Chainlit layer
    content = last_message.content if hasattr(last_message, "content") else str(last_message)
    return "end"
