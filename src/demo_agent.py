import uuid
from typing import Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.agent_graph import build_graph

# A scripted agent with canned data: the whole app can be explored with no API key and no database.


@tool
def query_telemetry_db(sql_query: str) -> str:
    """Demo stand-in for the SQL telemetry tool."""
    return (
        "COLUMNS: Timestamp, Latitude, Longitude, Current_Temperature_C, Risk_Classification, Port_Congestion_Level\n"
        "('2021-03-14 09:00:00', 33.7701, -118.1937, 6.8, 'High Risk', 8.2)\n"
        "('2021-03-14 08:00:00', 33.7712, -118.1990, 5.9, 'High Risk', 7.9)\n"
        "('2021-03-14 07:00:00', 33.8021, -118.2410, 3.4, 'Moderate Risk', 6.1)\n"
    )


@tool
def fetch_corridor_conditions(latitude: float, longitude: float) -> str:
    """Demo stand-in for the live weather tool."""
    return (
        "--- LIVE CORRIDOR TELEMETRY ---\n"
        f"Target GPS: {latitude}, {longitude}\n"
        "External Temp: 31.4C | Wind Speed: 14.2 km/h\n"
        "Corridor Risk: High Transit Disruption (Congestion Index: 8.5/10)\n"
        "-------------------------------"
    )


@tool
def search_compliance_sop(query: str) -> str:
    """Demo stand-in for the SOP vector search."""
    return (
        "--- COMPLIANCE SOP CONTEXT ---\n"
        "[Source: Cold_Chain_Incident_SOP_v2.md | Format: MD]\n"
        "Fresh Perishables: IoT temperature must remain between 0.0C and 4.0C. If it exceeds 4.0C, an immediate "
        "cold-chain breach is declared. The dispatcher must contact the driver to restart the auxiliary cooling unit. "
        "If the ETA delay is greater than 1 hour, divert the vehicle to the nearest emergency cold-storage facility.\n\n"
        "[Source: Cold_Chain_Incident_SOP_v2.md | Format: MD]\n"
        "Port of Long Beach / LA: if the congestion level exceeds 7.0, standard routing is suspended. Divert shipments "
        "to the Inland Empire Overflow Depot (San Bernardino) for cross-docking.\n"
        "------------------------------"
    )


@tool
def create_incident_ticket(
    title: str,
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    description: str,
    recommended_action: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> str:
    """Demo stand-in for the ticket tool: nothing is saved."""
    return f"Ticket INC-DEMO{uuid.uuid4().hex[:4].upper()} created successfully (demo mode: nothing was saved)."


DEMO_TOOLS = [query_telemetry_db, fetch_corridor_conditions, search_compliance_sop, create_incident_ticket]

ANSWER = """### 1. Executive Summary
* A refrigerated truck near the Port of Long Beach is at **6.8 C**, above the 4.0 C limit: a cold-chain breach is declared.
* The cargo is at risk of spoilage while port congestion (8.2) and wind keep the corridor disrupted.

### 2. Telemetry & Environment Analysis
| Location (Lat/Lon) | Current Temp | Cargo Risk | Weather / Congestion |
| :--- | :--- | :--- | :--- |
| 33.77 / -118.19 | 6.8 C | High Risk | Wind 14.2 km/h, congestion 8.2 |

*Analysis:* The temperature has climbed for three hours while the truck waits in a congested corridor, which points to the cooling unit rather than the weather.

### 3. Required Action Plan
1. **Restart the cooling unit**: contact the driver now.
2. **Divert if the delay exceeds 1 hour**: go to the nearest emergency cold-storage facility, or the Inland Empire Overflow Depot because port congestion is above 7.0.
{ticket_line}

*SOP Compliance Citation:* Cold_Chain_Incident_SOP_v2.md, sections 1 and 2.
"""

EXPLANATION = (
    "A **Tier 1** escalation is handled by the dispatcher on duty (restart the cooling unit, contact the driver). "
    "A **Tier 2** escalation goes to the Logistics Manager when a shipment is *High Risk* and its delay probability "
    "is above 0.65. I answered from general knowledge, so no tool was needed."
)


def _turn_tool_messages(messages):
    """Tool results produced since the last user message."""
    found = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, ToolMessage):
            found.append(message)
    return list(reversed(found))


def _call(name, args):
    return {"id": f"call_{uuid.uuid4().hex[:10]}", "name": name, "args": args}


def scripted_reasoner(state):
    messages = state["messages"]
    question = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    results = _turn_tool_messages(messages)

    if not results and any(word in str(question).lower() for word in ("explain", "difference", "what is", "tier")):
        return {"messages": [AIMessage(content=EXPLANATION)]}

    steps = [
        lambda: _call("query_telemetry_db", {"sql_query": "SELECT TOP 3 * FROM FDE_VIEWS.VW_ACTIVE_FLEET WHERE Latitude BETWEEN 33.5 AND 34.0 ORDER BY Timestamp DESC"}),
        lambda: _call("fetch_corridor_conditions", {"latitude": 33.77, "longitude": -118.19}),
        lambda: _call("search_compliance_sop", {"query": "temperature rules for fresh perishables and breach mitigation"}),
        lambda: _call("create_incident_ticket", {
            "title": "Reefer temperature breach near Port of Long Beach",
            "severity": "HIGH",
            "description": "Cargo temperature 6.8 C (limit 4.0 C), rising for 3 hours. Port congestion 8.2, wind 14.2 km/h.",
            "recommended_action": "Restart the cooling unit; divert to the nearest cold storage if the delay exceeds 1 hour.",
            "latitude": 33.77,
            "longitude": -118.19,
        }),
    ]

    if len(results) < len(steps):
        return {"messages": [AIMessage(content="", tool_calls=[steps[len(results)]()])]}

    rejected = "REJECTED" in str(results[-1].content)
    ticket_line = (
        "3. **No ticket opened**: the operator declined it, so follow the steps above manually."
        if rejected
        else f"3. **Incident ticket**: {results[-1].content}"
    )
    return {"messages": [AIMessage(content=ANSWER.format(ticket_line=ticket_line))]}


def build_demo_agent():
    return build_graph(scripted_reasoner, DEMO_TOOLS, MemorySaver())
