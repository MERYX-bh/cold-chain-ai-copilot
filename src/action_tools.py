import os
import uuid
import urllib.parse
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

project_root = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=project_root / ".env")


@lru_cache(maxsize=1)
def _agent_engine():
    connection_string = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('SQL_SERVER_HOST', 'localhost')},{os.getenv('SQL_SERVER_PORT', '1433')};"
        f"DATABASE=master;"
        f"UID={os.getenv('SQL_AGENT_USER', 'USR_FDE_RO')};"
        f"PWD={os.getenv('SQL_AGENT_PASSWORD')};"
        f"Encrypt=no;"
        f"TrustServerCertificate=yes;"
    )
    params = urllib.parse.quote_plus(connection_string)
    return create_engine(f"mssql+pyodbc:///?odbc_connect={params}")


@tool
def create_incident_ticket(
    title: str,
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    description: str,
    recommended_action: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    config: RunnableConfig = None,
) -> str:
    """
    Creates an incident ticket for a confirmed cold-chain breach (temperature violation, reefer failure, severe corridor disruption).
    This action is irreversible and ALWAYS needs human approval, so only call it once the telemetry and the SOP both support it.
    Write the description from verified data only (temperatures, coordinates, SOP clause), never from assumptions.
    """
    ticket_ref = f"INC-{uuid.uuid4().hex[:8].upper()}"
    session_id = ((config or {}).get("configurable") or {}).get("thread_id")

    try:
        with _agent_engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO FDE_VIEWS.IncidentTickets
                    (TicketRef, SessionID, Title, Severity, Description, RecommendedAction, Latitude, Longitude)
                VALUES
                    (:ref, :session_id, :title, :severity, :description, :action, :lat, :lon)
            """), {
                "ref": ticket_ref,
                "session_id": session_id,
                "title": title,
                "severity": severity,
                "description": description,
                "action": recommended_action,
                "lat": latitude,
                "lon": longitude,
            })
        return f"Ticket {ticket_ref} created successfully (severity: {severity}, status: OPEN)."
    except Exception as e:
        return f"Ticket creation failed, nothing was saved: {e}"
