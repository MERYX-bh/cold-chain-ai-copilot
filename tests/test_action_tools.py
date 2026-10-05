import re

import pytest
from pydantic import ValidationError

from src import action_tools


class FakeConnection:
    def __init__(self, store, error=None):
        self._store = store
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        if self._error:
            raise self._error
        self._store.append((str(statement), params))


class FakeEngine:
    def __init__(self, error=None):
        self.inserts = []
        self._error = error

    def begin(self):
        return FakeConnection(self.inserts, self._error)


@pytest.fixture
def engine(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(action_tools, "_agent_engine", lambda: fake)
    return fake


TICKET = {
    "title": "Reefer temperature breach near Los Angeles",
    "severity": "HIGH",
    "description": "Cargo at 11.4C for 3 readings, above the 8C limit.",
    "recommended_action": "Reroute to the nearest cold storage and notify quality.",
    "latitude": 33.77,
    "longitude": -118.19,
}


def test_ticket_is_inserted_with_every_field(engine):
    action_tools.create_incident_ticket.invoke(TICKET)
    statement, params = engine.inserts[0]
    assert "INSERT INTO FDE_VIEWS.IncidentTickets" in statement
    assert params["title"] == TICKET["title"]
    assert params["severity"] == "HIGH"
    assert params["description"] == TICKET["description"]
    assert params["action"] == TICKET["recommended_action"]
    assert (params["lat"], params["lon"]) == (33.77, -118.19)


def test_ticket_reference_is_returned_and_stored(engine):
    result = action_tools.create_incident_ticket.invoke(TICKET)
    reference = engine.inserts[0][1]["ref"]
    assert re.fullmatch(r"INC-[0-9A-F]{8}", reference)
    assert reference in result and "created successfully" in result


def test_each_ticket_gets_a_unique_reference(engine):
    action_tools.create_incident_ticket.invoke(TICKET)
    action_tools.create_incident_ticket.invoke(TICKET)
    assert engine.inserts[0][1]["ref"] != engine.inserts[1][1]["ref"]


def test_ticket_is_linked_to_the_conversation_thread(engine):
    config = {"configurable": {"thread_id": "thread-42"}}
    action_tools.create_incident_ticket.invoke(TICKET, config=config)
    assert engine.inserts[0][1]["session_id"] == "thread-42"


def test_coordinates_are_optional(engine):
    minimal = {k: v for k, v in TICKET.items() if k not in ("latitude", "longitude")}
    action_tools.create_incident_ticket.invoke(minimal)
    params = engine.inserts[0][1]
    assert params["lat"] is None and params["lon"] is None


def test_database_failure_is_reported_as_nothing_saved(monkeypatch):
    broken = FakeEngine(error=RuntimeError("permission denied"))
    monkeypatch.setattr(action_tools, "_agent_engine", lambda: broken)
    result = action_tools.create_incident_ticket.invoke(TICKET)
    assert "failed" in result and "nothing was saved" in result and "permission denied" in result
    assert "created successfully" not in result


def test_unknown_severity_is_rejected_before_touching_the_database(engine):
    with pytest.raises(ValidationError):
        action_tools.create_incident_ticket.invoke({**TICKET, "severity": "URGENT"})
    assert engine.inserts == []


def test_llm_sees_the_severity_choices_but_not_the_internal_config():
    schema = action_tools.create_incident_ticket.args_schema.model_json_schema()
    assert schema["properties"]["severity"]["enum"] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert "config" not in schema["properties"]
    assert set(schema["required"]) == {"title", "severity", "description", "recommended_action"}
