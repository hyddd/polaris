from langchain_core.messages import HumanMessage
from src.agent.skills.search import search_node
from src.state import AgentState


def test_search_node():
    state = AgentState(
        messages=[HumanMessage(content="RBAC讨论结果")],
        intent="knowledge_search", user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )
    result = search_node(state)
    assert "knowledge_search" in str(result["tool_results"]["mode"])
    assert "rag_search" in str(result["tool_results"]["tools_available"])
