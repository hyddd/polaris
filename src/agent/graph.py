from langgraph.graph import StateGraph, END
from src.state import AgentState
from src.agent.router import classify_intent, route_condition
from src.agent.confirm import confirm_node
from src.agent.executor import agent_node, tool_node, should_continue


def build_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("router", classify_intent)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("confirm", confirm_node)

    builder.set_entry_point("router")

    # Router → Agent (skip intermediate skill nodes — logic in executor)
    builder.add_edge("router", "agent")

    # ReAct loop: Agent ⇄ Tools
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )
    builder.add_edge("tools", "agent")

    return builder.compile()


def get_agent():
    return build_agent_graph()
