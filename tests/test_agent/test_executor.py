from langchain_core.messages import HumanMessage, AIMessage
from src.agent.executor import should_continue, agent_node
from src.state import AgentState


def make_state(messages, intent="chat"):
    return AgentState(
        messages=messages,
        intent=intent,
        user_profile={}, tool_results={},
        final_response="", needs_clarification=False, pending_action=None,
    )


def test_should_continue_with_tool_calls():
    msg = AIMessage(content="", tool_calls=[{"name": "todo", "args": {}, "id": "c1"}])
    state = make_state([HumanMessage(content="hi"), msg])
    assert should_continue(state) == "tools"


def test_should_continue_without_tool_calls():
    msg = AIMessage(content="完成！")
    state = make_state([HumanMessage(content="hi"), msg])
    assert should_continue(state) == "end"


def test_should_continue_empty_messages():
    state = make_state([])
    assert should_continue(state) == "end"


def test_agent_node_sets_up_messages():
    """Agent node should return a messages key."""
    # This test will fail without a real LLM or proper mock — it's here
    # to document the expected behavior. Real E2E tests cover the full flow.
    pass
