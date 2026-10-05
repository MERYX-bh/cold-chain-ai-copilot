import pytest
from langchain_core.documents import Document


class FakeCursor:
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = rows

    def keys(self):
        return self._columns

    def fetchmany(self, size):
        return self._rows[:size]


class FakeConnection:
    def __init__(self, cursor=None, error=None):
        self._cursor = cursor
        self._error = error
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement):
        self.queries.append(str(statement))
        if self._error:
            raise self._error
        return self._cursor


class FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


class ForbiddenEngine:
    def connect(self):
        raise AssertionError("the database must not be reached for a blocked query")


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def tools(app_modules):
    return app_modules.agent_tools


# ---------- query_telemetry_db ----------

@pytest.mark.parametrize("sql", [
    "DROP TABLE dbo.TBL_SC_FLEET_HIST_RAW",
    "UPDATE FDE_VIEWS.VW_ACTIVE_FLEET SET Latitude = 0",
    "DELETE FROM FDE_VIEWS.VW_ACTIVE_FLEET",
    "EXEC xp_cmdshell 'dir'",
])
def test_sql_tool_blocks_anything_that_is_not_a_select(tools, monkeypatch, sql):
    monkeypatch.setattr(tools, "create_engine", lambda url: ForbiddenEngine())
    result = tools.query_telemetry_db.invoke({"sql_query": sql})
    assert result.startswith("SECURITY BLOCK")


def test_sql_tool_accepts_lowercase_select_with_leading_spaces(tools, monkeypatch):
    connection = FakeConnection(FakeCursor(["Latitude"], [(33.7,)]))
    monkeypatch.setattr(tools, "create_engine", lambda url: FakeEngine(connection))
    result = tools.query_telemetry_db.invoke({"sql_query": "   select Latitude from FDE_VIEWS.VW_ACTIVE_FLEET"})
    assert result == "COLUMNS: Latitude\n(33.7,)\n"


def test_sql_tool_returns_at_most_ten_rows(tools, monkeypatch):
    rows = [(i, 20.0 + i) for i in range(25)]
    connection = FakeConnection(FakeCursor(["Id", "Temp"], rows))
    monkeypatch.setattr(tools, "create_engine", lambda url: FakeEngine(connection))
    result = tools.query_telemetry_db.invoke({"sql_query": "SELECT Id, Temp FROM FDE_VIEWS.VW_ACTIVE_FLEET"})
    assert result.splitlines()[0] == "COLUMNS: Id, Temp"
    assert len(result.splitlines()) == 1 + 10


def test_sql_tool_reports_empty_results(tools, monkeypatch):
    connection = FakeConnection(FakeCursor(["Id"], []))
    monkeypatch.setattr(tools, "create_engine", lambda url: FakeEngine(connection))
    result = tools.query_telemetry_db.invoke({"sql_query": "SELECT Id FROM FDE_VIEWS.VW_ACTIVE_FLEET"})
    assert result == "No records matched the query criteria."


def test_sql_tool_turns_database_failures_into_a_message(tools, monkeypatch):
    connection = FakeConnection(error=RuntimeError("login failed"))
    monkeypatch.setattr(tools, "create_engine", lambda url: FakeEngine(connection))
    result = tools.query_telemetry_db.invoke({"sql_query": "SELECT 1"})
    assert result.startswith("Database Error:") and "login failed" in result


# ---------- fetch_corridor_conditions ----------

def _weather(monkeypatch, tools, payload, calls=None):
    def fake_get(url, timeout):
        if calls is not None:
            calls.append(url)
        return FakeResponse(payload)

    monkeypatch.setattr(tools.requests, "get", fake_get)


def test_strong_wind_means_high_disruption(tools, monkeypatch):
    _weather(monkeypatch, tools, {"current_weather": {"temperature": 18.5, "windspeed": 22.0}})
    result = tools.fetch_corridor_conditions.invoke({"latitude": 33.77, "longitude": -118.19})
    assert "High Transit Disruption" in result and "8.5/10" in result
    assert "18.5" in result and "22.0" in result


def test_calm_wind_means_normal_corridor(tools, monkeypatch):
    _weather(monkeypatch, tools, {"current_weather": {"temperature": 12.0, "windspeed": 4.0}})
    result = tools.fetch_corridor_conditions.invoke({"latitude": 33.77, "longitude": -118.19})
    assert "Corridor Normal" in result and "2.5/10" in result


def test_weather_request_uses_the_given_coordinates(tools, monkeypatch):
    calls = []
    _weather(monkeypatch, tools, {"current_weather": {}}, calls)
    tools.fetch_corridor_conditions.invoke({"latitude": 33.77, "longitude": -118.19})
    assert "latitude=33.77" in calls[0] and "longitude=-118.19" in calls[0]


def test_weather_api_failure_is_reported_not_raised(tools, monkeypatch):
    def failing_get(url, timeout):
        raise ConnectionError("no network")

    monkeypatch.setattr(tools.requests, "get", failing_get)
    result = tools.fetch_corridor_conditions.invoke({"latitude": 0.0, "longitude": 0.0})
    assert result.startswith("Corridor API Communication Failure")


# ---------- search_compliance_sop ----------

class FakeRetriever:
    def __init__(self, docs=None, error=None):
        self._docs = docs or []
        self._error = error
        self.queries = []

    def invoke(self, query):
        self.queries.append(query)
        if self._error:
            raise self._error
        return self._docs


def test_sop_search_cites_source_and_format(tools, monkeypatch):
    doc = Document(
        page_content="Fresh perishables must stay between 2C and 8C.",
        metadata={"source_file": "Cold_Chain_Incident_SOP_v2.md", "file_format": "MD"},
    )
    retriever = FakeRetriever([doc])
    monkeypatch.setattr(tools, "retriever", retriever)
    result = tools.search_compliance_sop.invoke({"query": "temperature rules"})
    assert retriever.queries == ["temperature rules"]
    assert "[Source: Cold_Chain_Incident_SOP_v2.md | Format: MD]" in result
    assert "between 2C and 8C" in result


def test_sop_search_reports_when_nothing_matches(tools, monkeypatch):
    monkeypatch.setattr(tools, "retriever", FakeRetriever([]))
    result = tools.search_compliance_sop.invoke({"query": "anything"})
    assert result == "No matching compliance clauses found."


def test_sop_search_failure_is_reported_not_raised(tools, monkeypatch):
    monkeypatch.setattr(tools, "retriever", FakeRetriever(error=RuntimeError("index unavailable")))
    result = tools.search_compliance_sop.invoke({"query": "anything"})
    assert result.startswith("Vector Store Retrieval Error") and "index unavailable" in result
