import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ChatState } from "../lib/chatState";
import { SUGGESTIONS, toolInfo } from "../lib/toolInfo";
import type { Decision } from "../types";
import { ApprovalCard } from "./ApprovalCard";
import { Markdown } from "./Markdown";
import { TracePills } from "./TracePills";

type Props = { state: ChatState; onSend: (text: string) => void; onDecide: (decision: Decision) => void };

export function ChatPanel({ state, onSend, onDecide }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const locked = state.busy || state.pending !== null;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.messages, state.pending, state.busy]);

  const submit = (text: string) => {
    const clean = text.trim();
    if (!clean || locked) return;
    setDraft("");
    onSend(clean);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(draft);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(draft);
    }
  };

  return (
    <section className="chat" aria-label="Conversation with the agent">
      <div className="chat-scroll">
        {state.messages.length === 0 && (
          <div className="empty">
            <h2>Ask the dispatch agent</h2>
            <p>It reads fleet telemetry, checks the corridor weather and looks up your SOPs. Try one of these:</p>
            <div className="suggestions">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" className="suggestion" onClick={() => submit(suggestion)} disabled={locked}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {state.messages.map((message) => (
          <article key={message.id} className={`message message--${message.role}`}>
            <div className="message-role">{message.role === "user" ? "You" : "Agent"}</div>
            {message.role === "user" ? <p>{message.content}</p> : <TracePills traces={message.traces} />}
            {message.role === "assistant" && message.content && <Markdown>{message.content}</Markdown>}
          </article>
        ))}

        {state.pending && <ApprovalCard key={state.pending.tool_calls.map((call) => call.id).join("|")} request={state.pending} onDecide={onDecide} />}

        {state.busy && (
          <div className="working" role="status">
            <span className="dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            {state.activeTool ? toolInfo(state.activeTool).working : "Thinking"}
          </div>
        )}

        {state.error && (
          <p className="banner banner--error" role="alert">
            {state.error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={state.pending ? "Approve or reject the action above to continue" : "Ask about telemetry, corridor conditions or compliance"}
          rows={2}
          maxLength={4000}
          disabled={locked}
        />
        <button type="submit" className="button button--primary" disabled={locked || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  );
}
