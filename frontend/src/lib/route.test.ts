import { describe, expect, it } from "vitest";
import {
  CONGESTION_LIMIT,
  TEMP_FLOOR_C,
  TEMP_LIMIT_C,
  agentPlan,
  approximateFractions,
  portCongestion,
  revealedSteps,
  routeFor,
  segmentAt,
  segmentInfo,
  smoothPath,
  stationFractions,
  temperatureAt,
  temperatureStatus,
  triggerProgress,
  type Scenario,
} from "./route";

const fractionsFor = (scenario: Scenario) => approximateFractions(routeFor(scenario));
const sweep = (step = 0.001) => Array.from({ length: Math.round(1 / step) + 1 }, (_, i) => i * step);

describe("routes", () => {
  it("goes through the port normally and through the depot when the port is congested", () => {
    expect(routeFor("normal").map((p) => p.id)).toEqual(["producer", "cold", "port", "dc", "store"]);
    expect(routeFor("breach").map((p) => p.id)).toEqual(["producer", "cold", "port", "dc", "store"]);
    expect(routeFor("congestion").map((p) => p.id)).toEqual(["producer", "cold", "junction", "depot", "dc", "store"]);
  });

  it("draws one curve segment per leg", () => {
    const path = smoothPath(routeFor("normal"));
    expect(path.startsWith("M 90 310")).toBe(true);
    expect(path.match(/C /g)).toHaveLength(4);
    expect(smoothPath([{ x: 1, y: 1 }])).toBe("");
  });

  it("places stations in order from 0 to 1", () => {
    for (const scenario of ["normal", "congestion"] as const) {
      const fractions = fractionsFor(scenario);
      expect(fractions[0]).toBe(0);
      expect(fractions[fractions.length - 1]).toBe(1);
      expect(fractions.every((f, i) => i === 0 || f > fractions[i - 1])).toBe(true);
    }
  });

  it("measures station positions on a sampled curve", () => {
    const points = [{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 100, y: 0 }];
    const fractions = stationFractions(points, (distance) => ({ x: distance, y: 0 }), 100);
    expect(fractions).toEqual([0, 0.5, 1]);
  });

  it("finds which leg a progress value belongs to", () => {
    const fractions = [0, 0.25, 0.5, 0.75, 1];
    expect(segmentAt(0, fractions)).toBe(0);
    expect(segmentAt(0.3, fractions)).toBe(1);
    expect(segmentAt(0.5, fractions)).toBe(2);
    expect(segmentAt(1, fractions)).toBe(3);
  });
});

describe("temperature", () => {
  it("stays inside the 0 to 4 C limits for the whole normal journey", () => {
    for (const scenario of ["normal", "congestion"] as const) {
      const fractions = fractionsFor(scenario);
      for (const p of sweep()) {
        const t = temperatureAt(p, scenario, fractions);
        expect(t).toBeLessThanOrEqual(TEMP_LIMIT_C);
        expect(t).toBeGreaterThanOrEqual(TEMP_FLOOR_C);
      }
    }
  });

  it("breaks the limit only on the road between cold storage and the port", () => {
    const fractions = fractionsFor("breach");
    const above = sweep().filter((p) => temperatureAt(p, "breach", fractions) > TEMP_LIMIT_C);
    expect(above.length).toBeGreaterThan(0);
    expect(Math.min(...above)).toBeGreaterThanOrEqual(fractions[1]);
    expect(Math.max(...above)).toBeLessThanOrEqual(fractions[2]);
    expect(Math.max(...sweep().map((p) => temperatureAt(p, "breach", fractions)))).toBeGreaterThan(6);
  });

  it("classifies a reading against the SOP limits", () => {
    expect(temperatureStatus(2)).toBe("ok");
    expect(temperatureStatus(0)).toBe("ok");
    expect(temperatureStatus(3.5)).toBe("ok");
    expect(temperatureStatus(3.6)).toBe("warning");
    expect(temperatureStatus(4.0)).toBe("warning");
    expect(temperatureStatus(4.01)).toBe("breach");
    expect(temperatureStatus(-0.1)).toBe("breach");
  });

  it("reports port congestion above the SOP limit only in the congestion scenario", () => {
    expect(portCongestion("congestion")).toBeGreaterThan(CONGESTION_LIMIT);
    expect(portCongestion("normal")).toBeLessThan(CONGESTION_LIMIT);
    expect(portCongestion("breach")).toBeLessThan(CONGESTION_LIMIT);
  });
});

describe("the agent's reaction", () => {
  it("has nothing to do when everything is normal", () => {
    const fractions = fractionsFor("normal");
    expect(agentPlan("normal")).toEqual([]);
    expect(triggerProgress("normal", fractions)).toBeNull();
    expect(sweep(0.01).every((p) => revealedSteps(p, "normal", fractions) === 0)).toBe(true);
  });

  it("ends every plan with a human approval, after proposing the ticket", () => {
    for (const scenario of ["breach", "congestion"] as const) {
      const plan = agentPlan(scenario);
      expect(plan[plan.length - 1].tool).toBeNull();
      expect(plan[plan.length - 2].tool).toBe("create_incident_ticket");
    }
  });

  it("notices the breach as the temperature crosses the limit", () => {
    const fractions = fractionsFor("breach");
    const trigger = triggerProgress("breach", fractions) as number;
    expect(temperatureAt(trigger, "breach", fractions)).toBeGreaterThan(TEMP_LIMIT_C);
    expect(temperatureAt(trigger - 0.01, "breach", fractions)).toBeLessThanOrEqual(TEMP_LIMIT_C);
    expect(trigger).toBeGreaterThan(fractions[1]);
    expect(trigger).toBeLessThan(fractions[2]);
  });

  it("notices the congestion before the truck reaches the diversion point", () => {
    const fractions = fractionsFor("congestion");
    expect(triggerProgress("congestion", fractions)).toBeLessThan(fractions[2]);
  });

  it("reveals the steps one after the other, never too many and never backwards", () => {
    for (const scenario of ["breach", "congestion"] as const) {
      const fractions = fractionsFor(scenario);
      const trigger = triggerProgress(scenario, fractions) as number;
      const counts = sweep(0.005).map((p) => revealedSteps(p, scenario, fractions));

      expect(revealedSteps(trigger - 0.01, scenario, fractions)).toBe(0);
      expect(revealedSteps(trigger, scenario, fractions)).toBe(1);
      expect(Math.max(...counts)).toBe(agentPlan(scenario).length);
      expect(counts.every((c, i) => i === 0 || c >= counts[i - 1])).toBe(true);
    }
  });

  it("only uses tools that exist", () => {
    const known = ["query_telemetry_db", "fetch_corridor_conditions", "search_compliance_sop", "create_incident_ticket"];
    for (const scenario of ["breach", "congestion"] as const) {
      for (const step of agentPlan(scenario)) {
        if (step.tool) expect(known).toContain(step.tool);
      }
    }
  });
});

describe("leg descriptions", () => {
  it("describes every leg of every route", () => {
    for (const scenario of ["normal", "congestion"] as const) {
      const points = routeFor(scenario);
      for (let i = 0; i < points.length - 1; i++) {
        expect(segmentInfo(points[i].id, points[i + 1].id).title).not.toBe("In transit");
      }
    }
  });

  it("falls back to a generic description for an unknown leg", () => {
    expect(segmentInfo("store", "producer").title).toBe("In transit");
  });
});
