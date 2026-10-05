import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.agent_graph import build_graph
from src.api import create_app
from src.audit import MemoryAuditLog
from src.demo_agent import build_demo_agent

THREAD = "thread-abcdef12"


def events(response):
    parsed = []
    for block in response.text.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        parsed.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return parsed


def names(response):
    return [name for name, _ in events(response)]


def payload(response, event_name):
    return next(data for name, data in events(response) if name == event_name)


@pytest.fixture
def demo():
    audit = MemoryAuditLog()
    client = TestClient(create_app(agent=build_demo_agent(), audit=audit, demo=True))
    return SimpleNamespace(client=client, audit=audit)


def ask(client, message="Is there a temperature breach near Long Beach?", thread=THREAD):
    return client.post("/api/chat", json={"thread_id": thread, "message": message})


def decide(client, decision, thread=THREAD):
    return client.post("/api/chat", json={"thread_id": thread, "decision": decision})


# ---------- conversation flow ----------

def test_health_reports_the_mode(demo):
    assert demo.client.get("/api/health").json() == {"status": "ok", "mode": "demo"}


def test_the_agent_investigates_then_pauses_before_acting(demo):
    response = ask(demo.client)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert names(response) == [
        "tool_call", "tool_result",
        "tool_call", "tool_result",
        "tool_call", "tool_result",
        "tool_call", "approval_request", "done",
    ]
    assert [d["name"] for n, d in events(response) if n == "tool_call"] == [
        "query_telemetry_db", "fetch_corridor_conditions", "search_compliance_sop", "create_incident_ticket",
    ]
    request = payload(response, "approval_request")
    assert request["tool_calls"][0]["name"] == "create_incident_ticket"
    assert request["tool_calls"][0]["args"]["severity"] == "HIGH"


def test_approving_creates_the_ticket_and_the_agent_answers(demo):
    ask(demo.client)
    response = decide(demo.client, {"action": "approve"})
    assert names(response) == ["tool_result", "final", "done"]
    assert "INC-DEMO" in payload(response, "tool_result")["content"]
    assert "Incident ticket" in payload(response, "final")["content"]


def test_rejecting_opens_no_ticket(demo):
    ask(demo.client)
    response = decide(demo.client, {"action": "reject", "reason": "False alarm"})
    assert "False alarm" in payload(response, "tool_result")["content"]
    assert "No ticket opened" in payload(response, "final")["content"]


def test_a_question_that_needs_no_tool_gets_a_direct_answer(demo):
    response = ask(demo.client, "Explain the difference between Tier 1 and Tier 2")
    assert names(response) == ["final", "done"]


def test_edited_arguments_are_what_the_tool_receives():
    executed = []

    @tool
    def create_incident_ticket(title: str, severity: str) -> str:
        """Fake ticket tool."""
        executed.append({"title": title, "severity": severity})
        return "Ticket INC-X created"

    def reasoner(state):
        if isinstance(state["messages"][-1], HumanMessage):
            call = {"id": "c1", "name": "create_incident_ticket", "args": {"title": "T", "severity": "HIGH"}}
            return {"messages": [AIMessage(content="", tool_calls=[call])]}
        return {"messages": [AIMessage(content="done")]}

    client = TestClient(create_app(agent=build_graph(reasoner, [create_incident_ticket], MemorySaver()), audit=MemoryAuditLog(), demo=False))
    ask(client)
    decide(client, {"action": "edit", "args": {"c1": {"title": "T", "severity": "CRITICAL"}}})
    assert executed == [{"title": "T", "severity": "CRITICAL"}]


# ---------- request rules ----------

def test_a_decision_with_nothing_pending_is_refused(demo):
    response = decide(demo.client, {"action": "approve"})
    assert response.status_code == 409


def test_a_new_question_is_refused_while_an_action_is_pending(demo):
    ask(demo.client)
    assert ask(demo.client, "Another question").status_code == 409


def test_conversations_do_not_share_their_pending_actions(demo):
    ask(demo.client, thread="thread-aaaaaaaa")
    assert decide(demo.client, {"action": "approve"}, thread="thread-bbbbbbbb").status_code == 409


@pytest.mark.parametrize("body", [
    {"thread_id": "short", "message": "hi"},
    {"thread_id": "has spaces in it", "message": "hi"},
    {"thread_id": THREAD},
    {"thread_id": THREAD, "message": "hi", "decision": {"action": "approve"}},
    {"thread_id": THREAD, "message": "   "},
    {"thread_id": THREAD, "message": "x" * 4001},
    {"thread_id": THREAD, "decision": {"action": "delete-everything"}},
])
def test_malformed_requests_are_rejected(demo, body):
    assert demo.client.post("/api/chat", json=body).status_code == 422


def test_an_agent_crash_is_reported_without_leaking_details():
    class CrashingAgent:
        def get_state(self, config):
            return SimpleNamespace(tasks=[])

        def stream(self, *args, **kwargs):
            raise RuntimeError("secret internal detail")
            yield

    client = TestClient(create_app(agent=CrashingAgent(), audit=MemoryAuditLog(), demo=False))
    response = ask(client)
    assert names(response) == ["error", "done"]
    assert "secret internal detail" not in response.text


# ---------- audit trail and admin ----------

def login(client, username="demo", password="demo"):
    return client.post("/api/admin/login", json={"username": username, "password": password})


def test_the_audit_trail_requires_an_admin_login(demo):
    assert demo.client.get("/api/audit").status_code == 401
    assert demo.client.get("/api/audit", headers={"Authorization": "Bearer made-up"}).status_code == 401


def test_wrong_credentials_are_refused(demo):
    assert login(demo.client, password="wrong").status_code == 401
    assert login(demo.client, username="intruder").status_code == 401


def test_login_is_disabled_when_credentials_are_not_configured():
    client = TestClient(create_app(agent=build_demo_agent(), audit=MemoryAuditLog(), demo=False, admin_credentials=(None, None)))
    assert login(client).status_code == 503


def test_audit_trail_records_proposal_decision_and_outcome(demo):
    ask(demo.client)
    decide(demo.client, {"action": "approve"})
    token = login(demo.client).json()["token"]

    rows = demo.client.get("/api/audit", headers={"Authorization": f"Bearer {token}"}).json()["rows"]
    by_node = {row["NodeExecuted"]: row for row in rows}
    assert by_node["reasoner"]["ToolName"] in {"query_telemetry_db", "fetch_corridor_conditions", "search_compliance_sop", "create_incident_ticket"}
    assert json.loads(by_node["approval"]["Content"]) == {"action": "approve"}
    assert by_node["approval"]["ToolName"] == "create_incident_ticket"
    assert "INC-DEMO" in next(r for r in rows if r["NodeExecuted"] == "tools" and r["ToolName"] == "create_incident_ticket")["Content"]
    assert {row["SessionID"] for row in rows} == {THREAD}
    assert rows[0]["LogID"] > rows[-1]["LogID"], "newest first"


def test_audit_limit_is_validated(demo):
    token = login(demo.client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert demo.client.get("/api/audit?limit=0", headers=headers).status_code == 422
    assert demo.client.get("/api/audit?limit=5000", headers=headers).status_code == 422


# ---------- serving the built frontend ----------

def test_the_built_frontend_is_served_next_to_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<html><body>cold chain app</body></html>", encoding="utf-8")
    client = TestClient(create_app(agent=build_demo_agent(), audit=MemoryAuditLog(), demo=True, static_dir=tmp_path))
    assert "cold chain app" in client.get("/").text
    assert client.get("/api/health").status_code == 200
