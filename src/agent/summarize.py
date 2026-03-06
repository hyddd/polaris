from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from src.state import AgentState
from src.config import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL

SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是个人效率助手 Polaris。根据用户的问题和工具执行结果，生成自然、有帮助的回复。

规则：
- 用中文回复
- 简洁直接，不要啰嗦
- 如果是日程列表，按时间排列
- 如果工具没有返回结果（tool_results 为空或只有 mode），基于自身知识直接回答用户问题

用户最后说：{message}

工具结果：{tool_results}

请生成回复："""),
])


def summarize_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    tool_results = state.get("tool_results", {})

    llm = ChatOpenAI(model=LLM_MODEL, api_key=LLM_API_KEY, base_url=LLM_BASE_URL, temperature=0.3)
    chain = SUMMARIZE_PROMPT | llm
    result = chain.invoke({
        "message": last_msg,
        "tool_results": str(tool_results),
    })

    return {"final_response": result.content.strip()}
