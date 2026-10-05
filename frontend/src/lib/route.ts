export type Scenario = "normal" | "breach" | "congestion";
export type StationId = "producer" | "cold" | "port" | "junction" | "depot" | "dc" | "store";
export type RoutePoint = { id: StationId; x: number; y: number };
export type Status = "ok" | "warning" | "breach";

// Thresholds from the SOP (Cold_Chain_Incident_SOP_v2.md)
export const TEMP_LIMIT_C = 4.0;
export const TEMP_FLOOR_C = 0.0;
export const TEMP_WARNING_C = 3.5;
export const CONGESTION_LIMIT = 7.0;

export type Station = {
  label: string;
  short: string;
  place: string;
  x: number;
  y: number;
  labelAbove: boolean;
};

export const STATIONS: Record<Exclude<StationId, "junction">, Station> = {
  producer: { label: "Packing house", short: "Farm", place: "Oxnard, CA", x: 90, y: 310, labelAbove: false },
  cold: { label: "Cold storage", short: "Cold store", place: "Vernon, Los Angeles", x: 260, y: 190, labelAbove: true },
  port: { label: "Port of LA / Long Beach", short: "Port", place: "Container terminal", x: 450, y: 310, labelAbove: false },
  depot: { label: "Inland Empire Depot", short: "Depot", place: "San Bernardino", x: 590, y: 110, labelAbove: true },
  dc: { label: "Distribution center", short: "DC", place: "Ontario, CA", x: 730, y: 270, labelAbove: false },
  store: { label: "Retail store", short: "Store", place: "Customer", x: 840, y: 130, labelAbove: true },
};

const JUNCTION = { x: 350, y: 245 };

export function routeFor(scenario: Scenario): RoutePoint[] {
  const at = (id: Exclude<StationId, "junction">): RoutePoint => ({ id, x: STATIONS[id].x, y: STATIONS[id].y });
  if (scenario === "congestion") {
    return [at("producer"), at("cold"), { id: "junction", ...JUNCTION }, at("depot"), at("dc"), at("store")];
  }
  return [at("producer"), at("cold"), at("port"), at("dc"), at("store")];
}

const round = (value: number) => Math.round(value * 10) / 10;

/** Smooth curve through the points (Catmull-Rom converted to cubic Beziers). */
export function smoothPath(points: { x: number; y: number }[]): string {
  if (points.length < 2) return "";
  const parts = [`M ${points[0].x} ${points[0].y}`];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    parts.push(`C ${round(c1.x)} ${round(c1.y)}, ${round(c2.x)} ${round(c2.y)}, ${p2.x} ${p2.y}`);
  }
  return parts.join(" ");
}

/** Where each station sits along the route (0 to 1), estimated from straight-line distances. */
export function approximateFractions(points: { x: number; y: number }[]): number[] {
  const distances = [0];
  for (let i = 1; i < points.length; i++) {
    distances.push(distances[i - 1] + Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y));
  }
  const total = distances[distances.length - 1] || 1;
  return distances.map((d) => d / total);
}

/** Where each station sits along the drawn curve, measured by sampling it. */
export function stationFractions(
  points: { x: number; y: number }[],
  pointAt: (distance: number) => { x: number; y: number },
  totalLength: number,
  samples = 800,
): number[] {
  const sampled = Array.from({ length: samples + 1 }, (_, i) => pointAt((i / samples) * totalLength));
  const fractions: number[] = [];
  let from = 0;

  points.forEach((point, index) => {
    if (index === 0) return fractions.push(0);
    if (index === points.length - 1) return fractions.push(1);
    let best = from;
    let bestDistance = Infinity;
    for (let i = from; i <= samples; i++) {
      const distance = Math.hypot(sampled[i].x - point.x, sampled[i].y - point.y);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = i;
      }
    }
    from = best;
    fractions.push(best / samples);
  });
  return fractions;
}

export function segmentAt(progress: number, fractions: number[]): number {
  for (let i = fractions.length - 2; i >= 0; i--) {
    if (progress >= fractions[i]) return i;
  }
  return 0;
}

const bump = (x: number, center: number, width: number) => Math.exp(-(((x - center) / width) ** 2));

export function breachCenter(fractions: number[]): number {
  return (fractions[1] + fractions[2]) / 2;
}

/** Cargo temperature along the journey. The breach scenario adds a cooling-unit failure on the road to the port. */
export function temperatureAt(progress: number, scenario: Scenario, fractions: number[]): number {
  let temperature = 2.2 + 0.4 * Math.sin(progress * Math.PI * 6);
  for (let i = 1; i < fractions.length - 1; i++) {
    temperature += 0.6 * bump(progress, fractions[i], 0.012);
  }
  if (scenario === "breach" && fractions.length >= 3) {
    temperature += 5.4 * bump(progress, breachCenter(fractions), 0.07);
  }
  return temperature;
}

export function temperatureStatus(temperature: number): Status {
  if (temperature > TEMP_LIMIT_C || temperature < TEMP_FLOOR_C) return "breach";
  if (temperature > TEMP_WARNING_C) return "warning";
  return "ok";
}

export function portCongestion(scenario: Scenario): number {
  return scenario === "congestion" ? 8.2 : 3.1;
}

export type SegmentInfo = { title: string; text: string; tools: string[] };

const SEGMENTS: Record<string, SegmentInfo> = {
  "producer>cold": {
    title: "First mile: packing house to cold storage",
    text: "Fresh produce is packed and pre-cooled. Open doors during loading are the first small temperature bump.",
    tools: ["query_telemetry_db"],
  },
  "cold>port": {
    title: "Reefer truck to the port",
    text: "The longest road leg. Heat, traffic or a cooling-unit failure can push the cargo above 4.0 °C.",
    tools: ["query_telemetry_db", "fetch_corridor_conditions"],
  },
  "port>dc": {
    title: "Port handling and delivery to the distribution center",
    text: "Containers wait at the terminal, then travel inland. Port congestion above 7.0 suspends standard routing.",
    tools: ["query_telemetry_db", "search_compliance_sop"],
  },
  "cold>junction": {
    title: "Approaching the port: the decision point",
    text: "Before entering the terminal the corridor is checked. Congestion decides whether the truck keeps going.",
    tools: ["fetch_corridor_conditions", "query_telemetry_db"],
  },
  "junction>depot": {
    title: "Diversion to the Inland Empire Overflow Depot",
    text: "Per the SOP, freight is never held at a congested port: it is diverted to San Bernardino for cross-docking.",
    tools: ["search_compliance_sop"],
  },
  "depot>dc": {
    title: "Cross-docked at the depot, on to the distribution center",
    text: "The shipment is re-sorted at the depot and continues inland to its distribution center.",
    tools: ["query_telemetry_db"],
  },
  "dc>store": {
    title: "Last mile: distribution center to the store",
    text: "The final leg. Delivery delays here still count against the cold-chain limit.",
    tools: ["query_telemetry_db"],
  },
};

export function segmentInfo(from: StationId, to: StationId): SegmentInfo {
  return (
    SEGMENTS[`${from}>${to}`] ?? {
      title: "In transit",
      text: "The shipment is moving between two stations.",
      tools: ["query_telemetry_db"],
    }
  );
}

export type AgentStep = { tool: string | null; title: string; detail: string };

export function agentPlan(scenario: Scenario): AgentStep[] {
  if (scenario === "breach") {
    return [
      { tool: "query_telemetry_db", title: "Reads the sensor", detail: "The cargo is above 4.0 °C and still rising." },
      { tool: "fetch_corridor_conditions", title: "Checks the corridor", detail: "Heat and wind rule out a weather cause: the cooling unit is failing." },
      { tool: "search_compliance_sop", title: "Looks up the rule", detail: "Breach above 4.0 °C: restart the cooling unit, divert if the delay exceeds 1 hour." },
      { tool: "create_incident_ticket", title: "Proposes a ticket", detail: "The agent cannot act alone: it waits for a human to approve." },
      { tool: null, title: "A human approves", detail: "The ticket is opened and the dispatcher calls the driver." },
    ];
  }
  if (scenario === "congestion") {
    return [
      { tool: "query_telemetry_db", title: "Reads the port index", detail: "Congestion is at 8.2, above the limit of 7.0." },
      { tool: "search_compliance_sop", title: "Looks up the rule", detail: "Above 7.0 standard routing is suspended: divert to the San Bernardino depot." },
      { tool: "create_incident_ticket", title: "Proposes the diversion", detail: "A ticket describes the new route and waits for human approval." },
      { tool: null, title: "A human approves", detail: "The shipment leaves the port road and heads to the depot." },
    ];
  }
  return [];
}

export const STEP_SPACING = 0.04;

/** Progress at which the agent notices the problem, or null when there is nothing to notice. */
export function triggerProgress(scenario: Scenario, fractions: number[]): number | null {
  if (scenario === "congestion") return Math.max(0, fractions[2] - STEP_SPACING);
  if (scenario === "breach") {
    for (let p = 0; p <= 1; p += 0.002) {
      if (temperatureAt(p, scenario, fractions) > TEMP_LIMIT_C) return p;
    }
  }
  return null;
}

/** How many of the agent's steps have happened by this point of the journey. */
export function revealedSteps(progress: number, scenario: Scenario, fractions: number[]): number {
  const trigger = triggerProgress(scenario, fractions);
  if (trigger === null || progress < trigger) return 0;
  return Math.min(agentPlan(scenario).length, Math.floor((progress - trigger) / STEP_SPACING) + 1);
}
