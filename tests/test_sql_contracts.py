import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def insert_columns(source, table):
    match = re.search(rf"INSERT INTO {re.escape(table)}\s*\(([^)]*)\)", source)
    assert match, f"no INSERT INTO {table} found"
    return [column.strip() for column in match.group(1).split(",")]


def created_columns(sql, table):
    match = re.search(rf"CREATE TABLE {re.escape(table)}\s*\((.*?)\n\s*\);", sql, re.S)
    assert match, f"no CREATE TABLE {table} found"
    return {line.split()[0] for line in match.group(1).splitlines() if line.strip()}


def test_ticket_insert_only_uses_columns_the_table_has():
    columns = insert_columns(read("src/action_tools.py"), "FDE_VIEWS.IncidentTickets")
    table = created_columns(read("scripts/setup_incident_tickets.sql"), "FDE_VIEWS.IncidentTickets")
    assert set(columns) <= table


def test_ticket_columns_without_a_default_are_all_filled_by_the_code():
    sql = read("scripts/setup_incident_tickets.sql")
    filled = set(insert_columns(read("src/action_tools.py"), "FDE_VIEWS.IncidentTickets"))
    body = re.search(r"CREATE TABLE FDE_VIEWS\.IncidentTickets\s*\((.*?)\n\s*\);", sql, re.S).group(1)
    required = {
        line.split()[0]
        for line in body.splitlines()
        if "NOT NULL" in line and "DEFAULT" not in line and "IDENTITY" not in line
    }
    assert required <= filled


def test_audit_insert_only_uses_columns_the_table_has():
    columns = insert_columns(read("src/ui.py"), "FDE_VIEWS.AgentAuditLog")
    table = created_columns(read("scripts/setup_audit_log.sql"), "FDE_VIEWS.AgentAuditLog")
    assert set(columns) <= table


def test_audit_viewer_only_selects_columns_the_table_has():
    ui = read("src/ui.py")
    selected = re.search(r"SELECT\s+(.*?)\s+FROM FDE_VIEWS\.AgentAuditLog", ui, re.S).group(1)
    columns = {column.strip() for column in selected.split(",")}
    assert columns <= created_columns(read("scripts/setup_audit_log.sql"), "FDE_VIEWS.AgentAuditLog")


def test_agent_user_may_only_insert_into_the_write_tables():
    for script in ("scripts/setup_incident_tickets.sql", "scripts/setup_audit_log.sql"):
        grants = re.findall(r"GRANT\s+(.+?)\s+ON\s+\S+\s+TO\s+(\S+?);", read(script))
        assert grants, f"no GRANT in {script}"
        for privilege, user in grants:
            assert privilege.strip().upper() == "INSERT"
            assert user == "USR_FDE_RO"


def test_code_defaults_to_the_same_agent_user_the_sql_creates():
    login = re.search(r"CREATE LOGIN (\w+)", read("scripts/setup_security_and_view.sql")).group(1)
    for source in ("src/agent_tools.py", "src/action_tools.py", "src/ui.py"):
        assert f'"SQL_AGENT_USER", "{login}"' in read(source) or f"'SQL_AGENT_USER', '{login}'" in read(source)


def test_agent_view_exposes_every_column_the_sql_tool_documents():
    view = read("scripts/setup_security_and_view.sql")
    documented = re.search(r"Columns available:\s*(.*?)\s*Always write", read("src/agent_tools.py"), re.S).group(1)
    for column in [c.strip() for c in documented.replace("\n", " ").split(",") if c.strip()]:
        assert f"[{column.rstrip('.')}]" in view, f"{column} is documented to the LLM but missing from the view"
