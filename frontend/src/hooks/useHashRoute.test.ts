import { describe, expect, it } from "vitest";
import { DEFAULT_ROUTE, parseRoute } from "./useHashRoute";

describe("parseRoute", () => {
  it("opens on the supply chain journey by default", () => {
    expect(DEFAULT_ROUTE).toBe("journey");
    expect(parseRoute("")).toBe("journey");
    expect(parseRoute("#")).toBe("journey");
    expect(parseRoute("#/")).toBe("journey");
  });

  it("recognises every page, with or without the slash", () => {
    expect(parseRoute("#/journey")).toBe("journey");
    expect(parseRoute("#/console")).toBe("console");
    expect(parseRoute("#audit")).toBe("audit");
  });

  it("falls back to the journey for an unknown page", () => {
    expect(parseRoute("#/does-not-exist")).toBe("journey");
    expect(parseRoute("#/console/extra")).toBe("journey");
  });
});
