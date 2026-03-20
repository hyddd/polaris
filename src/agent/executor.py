"""ReAct agent executor — LLM with tool binding + tool execution loop."""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import ToolMessage, AIMessage
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
from src.tools.registry import ToolRegistry


SYSTEM_PROMPTS = {
    "daily_planning": (
        "你是个人效率助手 Polaris。用户想查看日程安排。\n\n"
        "请用中文回复。按以下步骤操作：\n"
        "1. 先调用 calendar 工具查询当日或用户指定日期的日历\n"
        "2. 再调用 todo 工具查询待办事项\n"
        "3. 综合两者结果，按时间线生成今日计划，标注冲突和优先级"
    ),
    "meeting_prep": (
        "你是个人效率助手 Polaris。用户需要会议准备。\n\n"
        "请用中文回复。按以下步骤操作：\n"
        "1. 调用 calendar 搜索找到对应会议\n"
        "2. 调用 rag_search 搜索会议相关的历史笔记\n"
        "3. 调用 todo 搜索关联待办\n"
        "4. 汇总生成会议准备清单"
    ),
    "knowledge_search": (
        "你是个人效率助手 Polaris。用户想搜索历史笔记。\n\n"
        "请用中文回复。调用 rag_search 进行语义搜索。\n"
        "如果搜索结果不够相关，追问用户更具体的关键词。"
    ),
    "quick_capture": (
        "你是个人效率助手 Polaris。用户想快速记录信息。\n\n"
        "请用中文回复。判断用户想记录的类型：\n"
        "- 日程（含时间/日期）：调用 calendar 创建\n"
        "- 笔记（想法/结论/信息）：调用 notes 创建\n"
        "- 待办（任务/事项）：调用 todo 创建\n\n"
        "将自然语言中的日期（明天、周五、下周一）转换为 YYYY-MM-DD 格式。\n"
        "创建成功后告知用户已完成。"
    ),
    "manage": (
        "你是个人效率助手 Polaris。用户想管理已有信息（修改/删除）。\n\n"
        "请用中文回复。按以下步骤操作：\n"
        "1. 先用 search 命令查找目标（如 calendar search <关键词> 或 todo search <关键词>）\n"
        "2. 找到后先告知用户将要执行的操作\n"
        "3. 最后执行修改/删除/标记完成\n\n"
        "删除操作要特别谨慎，确认无误后再执行。"
    ),
    "chat": (
        "你是个人效率助手 Polaris，一个聪明友好的 AI 助手。\n\n"
        "你可以帮用户：查看日程、准备会议、搜索笔记、记录信息、管理待办。\n"
        "对于普通闲聊，友好自然地回复。对于一般知识问题，基于你的知识回答。\n"
        "只在用户明确要求操作日程/笔记/待办时才调用工具。\n\n"
        "请用中文回复，简洁直接。"
    ),
    "clarify": (
        "你是个人效率助手 Polaris。用户的消息不够清晰。\n\n"
        "请用中文友好地追问，帮助用户明确意图。举例引导用户使用你的能力：\n"
        "查看日程、准备会议、搜索笔记、记录信息、管理待办。"
    ),
}

AGENT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    MessagesPlaceholder(variable_name="messages"),
])

INTENT_TOOLS = {
    "daily_planning": ["calendar", "todo"],
    "meeting_prep": ["calendar", "rag_search", "todo"],
    "knowledge_search": ["rag_search"],
    "quick_capture": ["calendar", "notes", "todo"],
    "manage": ["calendar", "todo"],
    "chat": [],
    "clarify": [],
}


def _get_tools(intent: str) -> list:
    registry = ToolRegistry.get_instance()
    tool_names = INTENT_TOOLS.get(intent, [])
    return [registry.get(name) for name in tool_names if registry.get(name)]


def agent_node(state: AgentState) -> dict:
    intent = state.get("intent", "chat")
    system_prompt = SYSTEM_PROMPTS.get(intent, SYSTEM_PROMPTS["chat"])
    tools = _get_tools(intent)

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
    if tools:
        llm = llm.bind_tools(tools)

    messages = state.get("messages", [])
    chain = AGENT_PROMPT | llm
    response = chain.invoke({"system_prompt": system_prompt, "messages": list(messages)})

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
