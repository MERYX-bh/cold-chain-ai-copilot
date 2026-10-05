import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from streamlit.testing.v1 import AppTest

from src.agent_graph import build_graph

UI_FILE = str(Path(__file__).resolve().parents[1] / "src" / "ui.py")
TICKET_ARGS = {"title": "Reefer breach LA", "severity": "HIGH"}


class FakeAuditConnection:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self._rows.append(params)

    def commit(self):
        pass


class FakeAuditEngine:
    def __init__(self, rows):
        self._rows = rows

    def connect(self):
        return FakeAuditConnection(self._rows)


@pytest.fixture
def ui(monkeypatch):
    executed, audit = [], []

    @tool
    def create_incident_ticket(title: str, severity: str) -> str:
        """Fake ticket tool."""
        executed.append({"title": title, "severity": severity})
        return "Ticket INC-FAKE created successfully."

    def fake_reasoner(state):
        if isinstance(state["messages"][-1], HumanMessage):
            call = {"id": "call_1", "name": "create_incident_ticket", "args": dict(TICKET_ARGS)}
            return {"messages": [AIMessage(content="", tool_calls=[call])]}
        return {"messages": [AIMessage(content="FINAL ANSWER: " + state["messages"][-1].content)]}

    fake_orchestrator = types.ModuleType("src.orchestrator")
    fake_orchestrator.fde_agent = build_graph(fake_reasoner, [create_incident_ticket], MemorySaver())
    monkeypatch.setitem(sys.modules, "src.orchestrator", fake_orchestrator)
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *args, **kwargs: FakeAuditEngine(audit))

    app = AppTest.from_file(UI_FILE, default_timeout=60).run()
    assert not app.exception
    return SimpleNamespace(app=app, executed=executed, audit=audit)


def ask(ui, question="Check the LA reefer"):
    ui.app.chat_input[0].set_value(question).run()
    assert not ui.app.exception


def click(ui, label_fragment):
    button = next(b for b in ui.app.button if label_fragment in b.label)
    button.click().run()
    assert not ui.app.exception


def shown(ui):
    app = ui.app
    return [m.value for m in app.markdown] + [w.value for w in app.warning] + [e.value for e in app.error]


def test_a_sensitive_action_pauses_and_locks_the_chat(ui):
    ask(ui)
    assert any("Human approval required" in text for text in shown(ui))
    assert ui.executed == []
    assert ui.app.chat_input[0].disabled
    labels = [b.label for b in ui.app.button]
    assert any("Approve" in label for label in labels) and any("Reject" in label for label in labels)


def test_approve_runs_the_ticket_and_unlocks_the_chat(ui):
    ask(ui)
    click(ui, "Approve")
    assert ui.executed == [TICKET_ARGS]
    assert any("FINAL ANSWER" in text for text in shown(ui))
    assert not any("Human approval required" in text for text in shown(ui))
    assert not ui.app.chat_input[0].disabled


def test_edited_arguments_are_what_runs(ui):
    ask(ui)
    ui.app.text_area[0].set_value(json.dumps({**TICKET_ARGS, "severity": "CRITICAL"}))
    click(ui, "Approve")
    assert ui.executed == [{**TICKET_ARGS, "severity": "CRITICAL"}]


def test_reject_runs_nothing_and_the_agent_sees_the_reason(ui):
    ask(ui)
    ui.app.text_input[0].set_value("False alarm, sensor glitch")
    click(ui, "Reject")
    assert ui.executed == []
    assert any("FINAL ANSWER" in text and "REJECTED" in text and "sensor glitch" in text for text in shown(ui))
    assert not ui.app.chat_input[0].disabled


def test_invalid_json_is_refused_and_nothing_runs(ui):
    ask(ui)
    ui.app.text_area[0].set_value("{not json")
    click(ui, "Approve")
    assert any("Invalid JSON" in text for text in shown(ui))
    assert ui.executed == []


def test_purge_cancels_a_pending_approval(ui):
    ask(ui)
    assert ui.app.chat_input[0].disabled
    ui.app.sidebar.button[0].click().run()
    assert not ui.app.exception
    assert not ui.app.chat_input[0].disabled
    assert not any("Human approval required" in text for text in shown(ui))
    assert ui.executed == []


def test_audit_trail_records_proposal_decision_and_outcome(ui):
    ask(ui)
    click(ui, "Approve")
    by_node = {row["node_name"]: row for row in ui.audit}
    assert json.loads(by_node["reasoner"]["content"]) == TICKET_ARGS
    assert by_node["reasoner"]["tool_name"] == "create_incident_ticket"
    assert json.loads(by_node["approval"]["content"]) == {"action": "approve"}
    assert "INC-FAKE" in by_node["tools"]["content"]
    assert by_node["reasoner_final"]["content"].startswith("FINAL ANSWER")
    assert len({row["session_id"] for row in ui.audit}) == 1


def test_audit_trail_records_a_rejection_with_its_reason(ui):
    ask(ui)
    ui.app.text_input[0].set_value("Not a real breach")
    click(ui, "Reject")
    decision = json.loads(next(row for row in ui.audit if row["node_name"] == "approval")["content"])
    assert decision == {"action": "reject", "reason": "Not a real breach"}
