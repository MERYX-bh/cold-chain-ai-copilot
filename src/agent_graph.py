from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

# Tools that change the outside world: they never run without a human decision.
SENSITIVE_TOOLS = {"create_incident_ticket"}


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def route_after_reasoner(state: AgentState) -> str:
    tool_calls = getattr(state["messages"][-1], "tool_calls", None)
    if not tool_calls:
        return END
    if any(call["name"] in SENSITIVE_TOOLS for call in tool_calls):
        return "approval"
    return "tools"


def approval_node(state: AgentState) -> Command[Literal["tools", "reasoner"]]:
    """Pauses the graph. Resume value: {"action": "approve"|"edit"|"reject", "args": {call_id: args}, "reason": str}."""
    last = state["messages"][-1]
    pending = [call for call in last.tool_calls if call["name"] in SENSITIVE_TOOLS]

    decision = interrupt({
        "type": "approval_request",
        "tool_calls": [{"id": c["id"], "name": c["name"], "args": c["args"]} for c in pending],
    })

    action = decision.get("action") if isinstance(decision, dict) else None

    if action == "approve":
        return Command(goto="tools")

    if action == "edit":
        edited_args = decision.get("args") or {}
        new_calls = [
            {**call, "args": edited_args.get(call["id"], call["args"])}
            if call["name"] in SENSITIVE_TOOLS else call
            for call in last.tool_calls
        ]
        kwargs = {k: v for k, v in last.additional_kwargs.items() if k != "tool_calls"}
        updated = last.model_copy(update={"tool_calls": new_calls, "additional_kwargs": kwargs})
        return Command(update={"messages": [updated]}, goto="tools")

    # Anything else (explicit reject, missing or malformed decision) denies the action.
    reason = (decision.get("reason") if isinstance(decision, dict) else None) or "No reason given."
    replies = [
        ToolMessage(
            content=(
                f"REJECTED by the human operator. Reason: {reason} The action was NOT executed."
                if call["name"] in SENSITIVE_TOOLS
                else "Not executed: the operator rejected another action in the same step. Call it again if still needed."
            ),
            name=call["name"],
            tool_call_id=call["id"],
        )
        for call in last.tool_calls
    ]
    return Command(update={"messages": replies}, goto="reasoner")


def build_graph(reasoning_node, tools, checkpointer):
    builder = StateGraph(AgentState)
    builder.add_node("reasoner", reasoning_node)
    builder.add_node("approval", approval_node)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "reasoner")
    builder.add_conditional_edges(
        "reasoner",
        route_after_reasoner,
        {"approval": "approval", "tools": "tools", END: END},
    )
    builder.add_edge("tools", "reasoner")
    return builder.compile(checkpointer=checkpointer)
