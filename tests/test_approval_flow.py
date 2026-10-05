import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.agent_graph import build_graph

executed = []


@tool
def query_telemetry_db(sql_query: str) -> str:
    """Fake read tool."""
    executed.append(("query_telemetry_db", {"sql_query": sql_query}))
    return "rows"


@tool
def create_incident_ticket(title: str, severity: str) -> str:
    """Fake action tool."""
    executed.append(("create_incident_ticket", {"title": title, "severity": severity}))
    return "Ticket INC-TEST created"


TICKET_CALL = {"id": "call_ticket", "name": "create_incident_ticket", "args": {"title": "Reefer breach", "severity": "HIGH"}}
READ_CALL = {"id": "call_read", "name": "query_telemetry_db", "args": {"sql_query": "SELECT 1"}}


def make_graph(tool_calls):
    def fake_reasoner(state):
        if isinstance(state["messages"][-1], HumanMessage):
            return {"messages": [AIMessage(content="", tool_calls=tool_calls)]}
        return {"messages": [AIMessage(content="final answer")]}

    return build_graph(fake_reasoner, [query_telemetry_db, create_incident_ticket], MemorySaver())


def start(tool_calls):
    executed.clear()
    graph = make_graph(tool_calls)
    config = {"configurable": {"thread_id": "t1"}}
    result = graph.invoke({"messages": [HumanMessage(content="go")]}, config)
    return graph, config, result


def test_read_only_calls_never_pause():
    _, _, result = start([READ_CALL])
    assert "__interrupt__" not in result
    assert executed == [("query_telemetry_db", {"sql_query": "SELECT 1"})]
    assert result["messages"][-1].content == "final answer"


def test_sensitive_call_pauses_before_executing():
    _, _, result = start([TICKET_CALL])
    assert result["__interrupt__"][0].value["tool_calls"][0]["name"] == "create_incident_ticket"
    assert executed == []


def test_approve_runs_the_original_call():
    graph, config, _ = start([TICKET_CALL, READ_CALL])
    result = graph.invoke(Command(resume={"action": "approve"}), config)
    assert ("create_incident_ticket", {"title": "Reefer breach", "severity": "HIGH"}) in executed
    assert ("query_telemetry_db", {"sql_query": "SELECT 1"}) in executed
    assert result["messages"][-1].content == "final answer"


def test_edit_runs_the_corrected_args():
    graph, config, _ = start([TICKET_CALL])
    edited = {"call_ticket": {"title": "Reefer breach", "severity": "CRITICAL"}}
    graph.invoke(Command(resume={"action": "edit", "args": edited}), config)
    assert executed == [("create_incident_ticket", {"title": "Reefer breach", "severity": "CRITICAL"})]


def test_reject_executes_nothing_and_informs_the_agent():
    graph, config, _ = start([TICKET_CALL, READ_CALL])
    result = graph.invoke(Command(resume={"action": "reject", "reason": "Not a real breach."}), config)
    assert executed == []
    replies = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert {m.tool_call_id for m in replies} == {"call_ticket", "call_read"}
    assert any("REJECTED" in m.content and "Not a real breach." in m.content for m in replies)
    assert result["messages"][-1].content == "final answer"


def test_malformed_decision_is_treated_as_reject():
    graph, config, _ = start([TICKET_CALL])
    graph.invoke(Command(resume="yes please"), config)
    assert executed == []


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(tests)} tests passed")
