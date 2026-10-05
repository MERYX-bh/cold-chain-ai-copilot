import os
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

RAW_TABLE = "dbo.TBL_SC_FLEET_HIST_RAW"

# (SQL file, object that exists once the file has been applied)
SETUP_STEPS = [
    ("setup_security_and_view.sql", "FDE_VIEWS.VW_ACTIVE_FLEET"),
    ("setup_audit_log.sql", "FDE_VIEWS.AgentAuditLog"),
    ("setup_incident_tickets.sql", "FDE_VIEWS.IncidentTickets"),
]

GO_LINE = re.compile(r"^[ \t]*GO\b[ \t]*(?:--.*)?\r?$", re.IGNORECASE | re.MULTILINE)
CREATE_LOGIN = re.compile(r"(CREATE LOGIN\s+\w+\s+WITH PASSWORD\s*=\s*)'[^']*'", re.IGNORECASE)


def split_batches(sql: str) -> list[str]:
    """Splits a script on its GO lines (a client-side keyword that SQL Server itself does not understand)."""
    batches = []
    for chunk in GO_LINE.split(sql):
        code_lines = [line for line in chunk.splitlines() if line.strip() and not line.strip().startswith("--")]
        if code_lines:
            batches.append(chunk.strip())
    return batches


def with_agent_password(sql: str, password: str) -> str:
    """Makes SQL_AGENT_PASSWORD the single source of truth for the agent login."""
    escaped = password.replace("'", "''")
    return CREATE_LOGIN.sub(lambda m: f"{m.group(1)}'{escaped}'", sql)


def admin_engine():
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('SQL_SERVER_HOST', 'localhost')},{os.getenv('SQL_SERVER_PORT', '1433')};"
        "DATABASE=master;"
        f"UID={os.getenv('SQL_ADMIN_USER', 'sa')};"
        f"PWD={os.environ['SQL_ADMIN_PASSWORD']};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(connection_string)}")


def wait_for_database(engine, timeout_seconds=120):
    deadline = time.time() + timeout_seconds
    while True:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as error:
            if time.time() > deadline:
                raise TimeoutError(f"SQL Server did not become ready in {timeout_seconds}s: {error}")
            print("Waiting for SQL Server...")
            time.sleep(3)


def object_exists(conn, name: str) -> bool:
    return conn.execute(text("SELECT OBJECT_ID(:name)"), {"name": name}).scalar() is not None


def main():
    missing = [var for var in ("SQL_ADMIN_PASSWORD", "SQL_AGENT_PASSWORD") if not os.getenv(var)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}")

    engine = admin_engine()
    wait_for_database(engine)

    with engine.connect() as conn:
        raw_table_exists = object_exists(conn, RAW_TABLE)

    if raw_table_exists:
        print(f"Skipped: {RAW_TABLE} already loaded")
    else:
        print(f"Loading the dataset into {RAW_TABLE}...")
        subprocess.run([sys.executable, str(SCRIPTS_DIR / "ingest_legacy_data.py")], check=True)

    for file_name, marker in SETUP_STEPS:
        # One transaction per script: a failure leaves nothing half-applied, so a retry starts clean.
        with engine.begin() as conn:
            if object_exists(conn, marker):
                print(f"Skipped: {file_name} (already applied)")
                continue
            sql = with_agent_password((SCRIPTS_DIR / file_name).read_text(encoding="utf-8"), os.environ["SQL_AGENT_PASSWORD"])
            for batch in split_batches(sql):
                conn.exec_driver_sql(batch)
            print(f"Applied: {file_name}")

    print("Database ready.")


if __name__ == "__main__":
    main()
