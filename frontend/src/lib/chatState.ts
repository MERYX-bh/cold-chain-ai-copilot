import type { ApprovalRequest, ChatMessage, StreamEvent } from "../types";

export type ChatState = {
  messages: ChatMessage[];
  pending: ApprovalRequest | null;
  busy: boolean;
  activeTool: string | null;
  error: string | null;
};

export const initialChatState: ChatState = {
  messages: [],
  pending: null,
  busy: false,
  activeTool: null,
  error: null,
};

export type ChatAction =
  | { type: "user_sent"; text: string; userId: string; assistantId: string }
  | { type: "decision_sent" }
  | { type: "event"; event: StreamEvent }
  | { type: "failed"; message: string }
  | { type: "reset" };

function lastAssistantIndex(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return i;
  }
  return -1;
}

function withLastAssistant(messages: ChatMessage[], change: (message: ChatMessage) => ChatMessage): ChatMessage[] {
  const index = lastAssistantIndex(messages);
  if (index === -1) return messages;
  return messages.map((message, i) => (i === index ? change(message) : message));
}

function dropEmptyDraft(messages: ChatMessage[]): ChatMessage[] {
  const index = lastAssistantIndex(messages);
  const draft = messages[index];
  if (index === -1 || draft.content !== "" || draft.traces.length > 0) return messages;
  return messages.filter((_, i) => i !== index);
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "user_sent":
      return {
        messages: [
          ...state.messages,
          { id: action.userId, role: "user", content: action.text, traces: [] },
          { id: action.assistantId, role: "assistant", content: "", traces: [] },
        ],
        pending: null,
        busy: true,
        activeTool: null,
        error: null,
      };

    case "decision_sent":
      return { ...state, pending: null, busy: true, error: null };

    case "failed":
      return {
        ...state,
        messages: dropEmptyDraft(state.messages),
        busy: false,
        activeTool: null,
        error: action.message,
      };

    case "reset":
      return initialChatState;

    case "event": {
      const { event } = action;
      switch (event.type) {
        case "tool_call":
          return {
            ...state,
            activeTool: event.data.name,
            messages: withLastAssistant(state.messages, (m) => ({
              ...m,
              traces: [...m.traces, { type: "tool_call", name: event.data.name, args: event.data.args }],
            })),
          };
        case "tool_result":
          return {
            ...state,
            activeTool: null,
            messages: withLastAssistant(state.messages, (m) => ({
              ...m,
              traces: [...m.traces, { type: "tool_result", name: event.data.name, content: event.data.content }],
            })),
          };
        case "approval_request":
          return { ...state, pending: event.data, activeTool: event.data.tool_calls[0]?.name ?? null };
        case "final":
          return {
            ...state,
            activeTool: null,
            messages: withLastAssistant(state.messages, (m) => ({ ...m, content: event.data.content })),
          };
        case "error":
          return {
            ...state,
            messages: dropEmptyDraft(state.messages),
            busy: false,
            activeTool: null,
            error: event.data.message,
          };
        case "done":
          return { ...state, busy: false, activeTool: state.pending ? state.activeTool : null };
      }
    }
  }
}
