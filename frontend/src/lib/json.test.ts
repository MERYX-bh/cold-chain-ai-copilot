import { describe, expect, it } from "vitest";
import { parseArgs, sameJson } from "./json";

describe("sameJson", () => {
  it("ignores key order", () => {
    expect(sameJson({ a: 1, b: { c: [1, 2] } }, { b: { c: [1, 2] }, a: 1 })).toBe(true);
  });

  it("sees a changed value, a missing key and an extra key", () => {
    expect(sameJson({ severity: "HIGH" }, { severity: "CRITICAL" })).toBe(false);
    expect(sameJson({ a: 1, b: 2 }, { a: 1 })).toBe(false);
    expect(sameJson({ a: 1 }, { a: 1, b: 2 })).toBe(false);
  });

  it("tells arrays from objects and null from objects", () => {
    expect(sameJson([1], { 0: 1 })).toBe(false);
    expect(sameJson(null, {})).toBe(false);
    expect(sameJson([1, 2], [1, 2])).toBe(true);
    expect(sameJson([1, 2], [2, 1])).toBe(false);
  });
});

describe("parseArgs", () => {
  it("accepts a JSON object", () => {
    expect(parseArgs('{"title":"x","latitude":33.7}')).toEqual({ ok: true, value: { title: "x", latitude: 33.7 } });
  });

  it("rejects broken JSON with a readable message", () => {
    const result = parseArgs("{not json");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error).toMatch(/^Invalid JSON/);
  });

  it.each(["[1,2]", '"text"', "42", "null"])("rejects %s because arguments must be an object", (text) => {
    expect(parseArgs(text)).toEqual({ ok: false, error: "Arguments must be a JSON object." });
  });
});
