import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { describeError, streamChat } from "../api/client";
import { chatReducer, initialChatState } from "../lib/chatState";
import type { ChatBody, Decision } from "../types";

export function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useAgentChat() {
  const [threadId, setThreadId] = useState(newId);
  const [state, dispatch] = useReducer(chatReducer, initialChatState);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async (body: ChatBody) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(body, (event) => dispatch({ type: "event", event }), controller.signal);
      dispatch({ type: "event", event: { type: "done", data: {} } });
    } catch (error) {
      if (!controller.signal.aborted) dispatch({ type: "failed", message: describeError(error) });
    }
  }, []);

  const send = useCallback(
    (text: string) => {
      dispatch({ type: "user_sent", text, userId: newId(), assistantId: newId() });
      void run({ thread_id: threadId, message: text });
    },
    [run, threadId],
  );

  const decide = useCallback(
    (decision: Decision) => {
      dispatch({ type: "decision_sent" });
      void run({ thread_id: threadId, decision });
    },
    [run, threadId],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    dispatch({ type: "reset" });
    setThreadId(newId());
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  return { threadId, state, send, decide, reset };
}
