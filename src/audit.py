import os
import threading
import urllib.parse
from datetime import datetime
from functools import lru_cache

from sqlalchemy import create_engine, text


def _engine(user: str, password: str):
    connection_string = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={os.getenv('SQL_SERVER_HOST', 'localhost')},{os.getenv('SQL_SERVER_PORT', '1433')};"
        "DATABASE=master;"
        f"UID={user};"
        f"PWD={password};"
        "Encrypt=no;"
        "TrustServerCertificate=yes;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(connection_string)}")


@lru_cache(maxsize=1)
def _agent_engine():
    return _engine(os.getenv("SQL_AGENT_USER", "USR_FDE_RO"), os.getenv("SQL_AGENT_PASSWORD", ""))


@lru_cache(maxsize=1)
def _admin_engine():
    return _engine(os.getenv("SQL_ADMIN_USER", ""), os.getenv("SQL_ADMIN_PASSWORD", ""))


class SqlAuditLog:
    """The agent account may only insert; reading the trail needs the admin account."""

    def write(self, session_id, node_name, tool_name, content):
        try:
            with _agent_engine().connect() as conn:
                conn.execute(text("""
                    INSERT INTO FDE_VIEWS.AgentAuditLog (SessionID, NodeExecuted, ToolName, Content)
                    VALUES (:session_id, :node_name, :tool_name, :content)
                """), {"session_id": session_id, "node_name": node_name, "tool_name": tool_name, "content": content})
                conn.commit()
        except Exception as error:
            print(f"Audit Log Failed (Silent): {error}")

    def read(self, limit=200):
        with _admin_engine().connect() as conn:
            result = conn.execute(text("""
                SELECT TOP (:limit) LogID, Timestamp, SessionID, NodeExecuted, ToolName, Content
                FROM FDE_VIEWS.AgentAuditLog
                ORDER BY Timestamp DESC
            """), {"limit": limit})
            return [
                {**dict(row._mapping), "Timestamp": row._mapping["Timestamp"].isoformat()}
                for row in result
            ]


class MemoryAuditLog:
    """Keeps the trail in memory: used by the demo mode and by the tests."""

    def __init__(self):
        self._rows = []
        self._lock = threading.Lock()

    def write(self, session_id, node_name, tool_name, content):
        with self._lock:
            self._rows.append({
                "LogID": len(self._rows) + 1,
                "Timestamp": datetime.now().isoformat(timespec="seconds"),
                "SessionID": session_id,
                "NodeExecuted": node_name,
                "ToolName": tool_name,
                "Content": content,
            })

    def read(self, limit=200):
        with self._lock:
            return list(reversed(self._rows))[:limit]
