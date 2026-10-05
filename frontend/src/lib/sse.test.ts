import { describe, expect, it } from "vitest";
import { parseSse } from "./sse";

describe("parseSse", () => {
  it("reads complete events and parses their JSON", () => {
    const { events, rest } = parseSse('event: tool_call\ndata: {"name":"query_telemetry_db"}\n\nevent: done\ndata: {}\n\n');
    expect(events).toEqual([
      { event: "tool_call", data: { name: "query_telemetry_db" } },
      { event: "done", data: {} },
    ]);
    expect(rest).toBe("");
  });

  it("keeps a partial event until the next chunk completes it", () => {
    const first = parseSse('event: final\ndata: {"content":"He');
    expect(first.events).toEqual([]);

    const second = parseSse(first.rest + 'llo"}\n\n');
    expect(second.events).toEqual([{ event: "final", data: { content: "Hello" } }]);
  });

  it("handles Windows line endings, even when split between chunks", () => {
    const first = parseSse("event: done\r\ndata: {}\r");
    expect(first.events).toEqual([]);
    const second = parseSse(first.rest + "\n\r\n");
    expect(second.events).toEqual([{ event: "done", data: {} }]);
  });

  it("keeps non-ASCII text intact", () => {
    const { events } = parseSse('event: final\ndata: {"content":"6,8 °C, très élevé"}\n\n');
    expect(events[0].data).toEqual({ content: "6,8 °C, très élevé" });
  });

  it("skips malformed blocks without losing the good ones", () => {
    const { events } = parseSse("event: x\ndata: {not json}\n\nevent: done\ndata: {}\n\n: comment only\n\n");
    expect(events).toEqual([{ event: "done", data: {} }]);
  });

  it("uses 'message' when an event has no name", () => {
    expect(parseSse('data: {"a":1}\n\n').events).toEqual([{ event: "message", data: { a: 1 } }]);
  });
});
