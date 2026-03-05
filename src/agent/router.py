from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

INTENT_OPTIONS = ["daily_planning", "meeting_prep", "knowledge_search", "quick_capture", "manage", "clarify"]


def classify_intent(state: AgentState) -> dict:
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "clarify"}

    last_message = messages[-1]
    content = last_message.content if hasattr(last_message, "content") else str(last_message)

    intent = _keyword_route(content)
    if intent:
        return {"intent": intent}

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一个意图分类器。分析用户消息，输出一个意图标签。

意图说明：
- daily_planning: 询问今日/某天的日程安排、待办、计划
- meeting_prep: 为某个会议做准备、整理材料
- knowledge_search: 搜索历史笔记、查找之前记录的信息
- quick_capture: 快速记录/创建日程、笔记、待办（用户想添加/记录新东西）
- manage: 修改、取消、删除已有的日程或待办（用户想改动现有东西）
- clarify: 消息信息不足，无法判断意图

区分 quick_capture 和 manage 的关键：
- "加个"、"新建"、"记一下"、"创建"、"添加" → quick_capture
- "取消"、"删除"、"修改"、"改到"、"改成"、"标记为" → manage

只输出意图标签，不要解释。"""),
        ("human", "{message}"),
    ])
    chain = prompt | llm
    result = chain.invoke({"message": content})
    intent = result.content.strip().lower()

    return {"intent": intent if intent in INTENT_OPTIONS else "clarify"}


def _keyword_route(content: str) -> str | None:
    """Fast keyword-based routing — cheap and reliable for obvious cases."""
    c = content.strip().lower()

    if any(kw in c for kw in ["加个", "新建", "记一下", "添加", "创建", "帮我加", "帮我记", "记录一下"]):
        return "quick_capture"
    if any(kw in c for kw in ["取消", "删除", "改到", "改成", "更新", "标记为", "移除"]):
        return "manage"
    if any(kw in c for kw in ["上次", "之前", "讨论过", "讨论了什么", "找一下", "搜索", "查一下笔记"]):
        return "knowledge_search"
    if any(kw in c for kw in ["安排", "计划", "今天有什么", "今天干嘛", "日程", "有什么事情", "今天要做"]):
        return "daily_planning"
    if any(kw in c for kw in ["准备", "会议材料", "帮我准备"]):
        return "meeting_prep"

    return None


def route_condition(state: AgentState) -> str:
    return state.get("intent", "clarify")
