import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("init_database", ROOT / "scripts" / "init_database.py")
init_database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(init_database)


def test_script_is_split_on_go_lines():
    sql = "CREATE SCHEMA A;\nGO\nCREATE VIEW B AS SELECT 1;\nGO\n"
    assert init_database.split_batches(sql) == ["CREATE SCHEMA A;", "CREATE VIEW B AS SELECT 1;"]


@pytest.mark.parametrize("go_line", ["GO", "go", "  GO  ", "GO -- end of batch"])
def test_go_is_recognised_whatever_its_form(go_line):
    sql = f"SELECT 1;\n{go_line}\nSELECT 2;"
    assert init_database.split_batches(sql) == ["SELECT 1;", "SELECT 2;"]


def test_windows_line_endings_are_handled():
    sql = "SELECT 1;\r\nGO\r\nSELECT 2;\r\n"
    assert [b.replace("\r", "") for b in init_database.split_batches(sql)] == ["SELECT 1;", "SELECT 2;"]


def test_go_inside_a_word_or_a_comment_is_not_a_separator():
    sql = "-- GO only works in client tools\nSELECT 'GOOD' AS GOAL;\nGO\n"
    assert init_database.split_batches(sql) == [sql.split("\nGO")[0]]


def test_comment_only_batches_are_dropped():
    sql = "SELECT 1;\nGO\n-- Check later:\n-- SELECT * FROM t;\n"
    assert init_database.split_batches(sql) == ["SELECT 1;"]


def test_real_security_script_is_split_into_runnable_batches():
    sql = (ROOT / "scripts" / "setup_security_and_view.sql").read_text(encoding="utf-8")
    batches = init_database.split_batches(sql)

    def first_statement(batch):
        code = [line for line in batch.splitlines() if line.strip() and not line.strip().startswith("--")]
        return code[0].split()[:2]

    assert first_statement(batches[0]) == ["CREATE", "SCHEMA"], "CREATE SCHEMA must be alone in its batch"
    assert first_statement(batches[1]) == ["CREATE", "VIEW"], "CREATE VIEW must be alone in its batch"
    assert any("CREATE LOGIN" in batch for batch in batches)
    assert not any(line.strip().upper().startswith("GO") for batch in batches for line in batch.splitlines())


def test_agent_password_comes_from_the_environment():
    sql = "CREATE LOGIN USR_FDE_RO WITH PASSWORD = 'AgentPassword2026!';\nCREATE USER USR_FDE_RO FOR LOGIN USR_FDE_RO;"
    result = init_database.with_agent_password(sql, "Another#Pass1")
    assert "WITH PASSWORD = 'Another#Pass1';" in result
    assert "AgentPassword2026!" not in result
    assert result.endswith("CREATE USER USR_FDE_RO FOR LOGIN USR_FDE_RO;")


def test_a_quote_in_the_password_cannot_break_the_statement():
    sql = "CREATE LOGIN USR_FDE_RO WITH PASSWORD = 'x';"
    assert init_database.with_agent_password(sql, "it's") == "CREATE LOGIN USR_FDE_RO WITH PASSWORD = 'it''s';"


def test_real_security_script_contains_the_login_that_gets_the_password():
    sql = (ROOT / "scripts" / "setup_security_and_view.sql").read_text(encoding="utf-8")
    assert init_database.with_agent_password(sql, "Replaced#1") != sql


@pytest.mark.parametrize("file_name, marker", init_database.SETUP_STEPS)
def test_each_setup_step_really_creates_its_marker_object(file_name, marker):
    sql = (ROOT / "scripts" / file_name).read_text(encoding="utf-8")
    assert f"CREATE TABLE {marker}" in sql or f"CREATE VIEW {marker}" in sql
