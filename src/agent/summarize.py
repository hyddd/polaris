from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是个人效率助手 Polaris，一个聪明、友好的 AI 助手。

你的能力包括：
- 查看日程安排
- 会议准备
- 搜索笔记
- 快速记录日程/笔记/待办
- 管理已有信息（修改/删除）

回复规则：
- 用中文回复
- 简洁直接，不要啰嗦
- 注意对话历史中的上下文（用户之前说过什么、你之前回过什么）
- 如果用户在闲聊，友好自然地回应
- 如果工具返回了结果（tool_results 中有实际数据），基于数据回答
- 如果 tool_results 只有 mode 标记，说明工具暂未接入，基于自身知识回答

工具执行结果：{tool_results}"""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{message}"),
])


def summarize_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    # Last 2 messages as the current exchange, rest as history
    if len(messages) >= 2:
        history = messages[:-2]
        current = messages[-2:]
    else:
        history = []
        current = messages

    tool_results = state.get("tool_results", {})

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
    chain = SUMMARIZE_PROMPT | llm

    # Build input: put the last user message as the human input, the rest as history
    last_user_msg = ""
    for m in reversed(current):
        if m.type == "human":
            last_user_msg = m.content
            break
    if not last_user_msg and current:
        last_user_msg = current[-1].content

    result = chain.invoke({
        "tool_results": str(tool_results),
        "history": history,
        "message": last_user_msg,
    })

    return {"final_response": result.content.strip()}
