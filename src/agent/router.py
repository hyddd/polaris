"""Intent router — keyword-only fast path, no LLM overhead."""

from src.state import AgentState

# Intents that get tool access; everything else defaults to chat
TOOL_INTENTS = ["daily_planning", "meeting_prep", "knowledge_search", "quick_capture", "manage"]


def classify_intent(state: AgentState) -> dict:
    """Keyword-based intent classification. No LLM — fast and cheap."""
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "chat"}

    last_message = messages[-1]
    content = last_message.content if hasattr(last_message, "content") else str(last_message)
    intent = _keyword_route(content)
    return {"intent": intent}


def _keyword_route(content: str) -> str:
    c = content.strip().lower()

    # quick_capture: adding/creating/recording
    if any(kw in c for kw in ["加个", "新建", "记一下", "添加", "创建", "帮我加", "帮我记",
                                "记录一下", "写个笔记", "做个笔记", "加一个", "建一个"]):
        return "quick_capture"

    # manage: modifying/deleting
    if any(kw in c for kw in ["取消", "删除", "改到", "改成", "更新", "标记为", "移除",
                                "清理", "删掉", "去掉", "修改一下", "改一下"]):
        return "manage"

    # knowledge_search: searching past notes
    if any(kw in c for kw in ["上次", "之前", "讨论过", "讨论了什么", "找一下", "搜索",
                                "查一下笔记", "有没有记", "查一下", "搜一下", "帮我找",
                                "之前记的", "有没有记录", "查笔记"]):
        return "knowledge_search"

    # daily_planning: checking schedule/todos
    if any(kw in c for kw in ["安排", "计划", "今天有什么", "今天干嘛", "日程", "有什么事情",
                                "今天要做", "今天要做什么", "今天忙", "今天安排", "今天的",
                                "有什么安排", "看看今天", "待办", "今天的事"]):
        return "daily_planning"

    # meeting_prep: preparing for meetings
    if any(kw in c for kw in ["准备", "会议材料", "帮我准备", "准备一下", "准备什么",
                                "开会", "会议准备", "要开会"]):
        return "meeting_prep"

    # Everything else is chat — no tools needed
    return "chat"


def route_condition(state: AgentState) -> str:
    return state.get("intent", "chat")
