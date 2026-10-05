import { describe, expect, it } from "vitest";
import { chatReducer, initialChatState, type ChatAction, type ChatState } from "./chatState";

const run = (actions: ChatAction[], from: ChatState = initialChatState) => actions.reduce(chatReducer, from);

const sent: ChatAction = { type: "user_sent", text: "Any breach?", userId: "u1", assistantId: "a1" };
const toolCall: ChatAction = { type: "event", event: { type: "tool_call", data: { id: "c1", name: "query_telemetry_db", args: { sql_query: "SELECT 1" } } } };
const toolResult: ChatAction = { type: "event", event: { type: "tool_result", data: { name: "query_telemetry_db", content: "rows" } } };
const approval: ChatAction = {
  type: "event",
  event: { type: "approval_request", data: { tool_calls: [{ id: "c2", name: "create_incident_ticket", args: { severity: "HIGH" } }] } },
};
const done: ChatAction = { type: "event", event: { type: "done", data: {} } };
const final: ChatAction = { type: "event", event: { type: "final", data: { content: "All good." } } };

describe("chatReducer", () => {
  it("adds the question and an empty answer, and marks the chat busy", () => {
    const state = run([sent]);
    expect(state.messages.map((m) => m.role)).toEqual(["user", "assistant"]);
    expect(state.messages[0].content).toBe("Any breach?");
    expect(state.busy).toBe(true);
  });

  it("records each tool call and its result on the answer being built", () => {
    const state = run([sent, toolCall]);
    expect(state.activeTool).toBe("query_telemetry_db");
    expect(state.messages[1].traces).toHaveLength(1);

    const after = chatReducer(state, toolResult);
    expect(after.activeTool).toBeNull();
    expect(after.messages[1].traces.map((t) => t.type)).toEqual(["tool_call", "tool_result"]);
  });

  it("pauses on an approval request and keeps the tool active while waiting", () => {
    const state = run([sent, toolCall, toolResult, approval, done]);
    expect(state.pending?.tool_calls[0].name).toBe("create_incident_ticket");
    expect(state.busy).toBe(false);
    expect(state.activeTool).toBe("create_incident_ticket");
  });

  it("resumes after a decision and finishes with the final answer", () => {
    const state = run([sent, approval, done, { type: "decision_sent" }]);
    expect(state.pending).toBeNull();
    expect(state.busy).toBe(true);

    const finished = run([final, done], state);
    expect(finished.messages[1].content).toBe("All good.");
    expect(finished.busy).toBe(false);
    expect(finished.activeTool).toBeNull();
  });

  it("a second question starts a fresh answer and clears the previous error", () => {
    const state = run([sent, final, done, { type: "failed", message: "boom" }, { ...sent, userId: "u2", assistantId: "a2" }]);
    expect(state.messages).toHaveLength(4);
    expect(state.error).toBeNull();
    expect(state.messages[3].id).toBe("a2");
  });

  it("an error removes an answer that has nothing in it", () => {
    const state = run([sent, { type: "failed", message: "Cannot reach the server." }]);
    expect(state.messages.map((m) => m.role)).toEqual(["user"]);
    expect(state.error).toBe("Cannot reach the server.");
    expect(state.busy).toBe(false);
  });

  it("an error keeps what the agent already did", () => {
    const state = run([sent, toolCall, toolResult, { type: "event", event: { type: "error", data: { message: "The agent failed." } } }]);
    expect(state.messages[1].traces).toHaveLength(2);
    expect(state.error).toBe("The agent failed.");
  });

  it("ignores stream events when there is no answer to update", () => {
    expect(() => run([toolCall, final, done])).not.toThrow();
  });

  it("reset returns to the empty state", () => {
    expect(run([sent, toolCall, { type: "reset" }])).toEqual(initialChatState);
  });
});
