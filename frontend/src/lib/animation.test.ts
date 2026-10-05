import { describe, expect, it } from "vitest";
import { advance } from "./animation";

describe("advance", () => {
  it("moves in proportion to time and speed", () => {
    expect(advance(0, 1, 1, 20, false).progress).toBeCloseTo(0.05);
    expect(advance(0, 1, 2, 20, false).progress).toBeCloseTo(0.1);
  });

  it("wraps around when looping", () => {
    const result = advance(0.98, 1, 1, 20, true);
    expect(result.progress).toBeCloseTo(0.03);
    expect(result.finished).toBe(false);
  });

  it("stops at the end when not looping", () => {
    expect(advance(0.98, 1, 1, 20, false)).toEqual({ progress: 1, finished: true });
  });

  it("never goes below zero", () => {
    expect(advance(0, 1, -5, 20, false).progress).toBe(0);
  });
});
