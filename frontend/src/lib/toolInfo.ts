export type ToolInfo = { label: string; working: string; chip: string };

const TOOLS: Record<string, ToolInfo> = {
  query_telemetry_db: { label: "Fleet telemetry", working: "Reading the fleet sensors", chip: "Reading the sensor" },
  fetch_corridor_conditions: { label: "Corridor weather", working: "Checking the corridor weather", chip: "Checking the weather" },
  search_compliance_sop: { label: "Compliance SOP", working: "Searching the procedures", chip: "Searching the SOP" },
  create_incident_ticket: { label: "Incident ticket", working: "Preparing an incident ticket", chip: "Ticket needs approval" },
};

export function toolInfo(name: string): ToolInfo {
  return TOOLS[name] ?? { label: name, working: `Running ${name}`, chip: name };
}

export const SUGGESTIONS = [
  "Is any shipment near Los Angeles above the temperature limit? Open an incident if so.",
  "Port congestion looks high: what does the SOP say we should do?",
  "Explain the difference between a Tier 1 and a Tier 2 escalation.",
];
