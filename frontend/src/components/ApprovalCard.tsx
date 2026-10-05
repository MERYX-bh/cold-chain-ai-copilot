import { useState } from "react";
import { parseArgs, sameJson } from "../lib/json";
import { toolInfo } from "../lib/toolInfo";
import type { ApprovalRequest, Decision } from "../types";

type Props = { request: ApprovalRequest; onDecide: (decision: Decision) => void };

export function ApprovalCard({ request, onDecide }: Props) {
  const calls = request.tool_calls;
  const single = calls.length === 1;
  const original = Object.fromEntries(calls.map((call) => [call.id, call.args]));
  const [text, setText] = useState(() => JSON.stringify(single ? calls[0].args : original, null, 2));
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const approve = () => {
    const parsed = parseArgs(text);
    if (!parsed.ok) return setError(parsed.error);
    const edited = single ? { [calls[0].id]: parsed.value } : (parsed.value as Record<string, Record<string, unknown>>);
    setError(null);
    onDecide(sameJson(edited, original) ? { action: "approve" } : { action: "edit", args: edited });
  };

  const reject = () => onDecide({ action: "reject", reason: reason.trim() || "No reason given." });

  return (
    <section className="approval" aria-labelledby="approval-title">
      <h3 id="approval-title">Human approval required</h3>
      <p>
        The agent wants to run <strong>{calls.map((call) => toolInfo(call.name).label).join(", ")}</strong>. It cannot act until you decide. You can correct the
        arguments before approving.
      </p>
      <label htmlFor="approval-args">Arguments (editable JSON)</label>
      <textarea id="approval-args" value={text} onChange={(event) => setText(event.target.value)} rows={Math.min(14, text.split("\n").length + 1)} spellCheck={false} />
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      <label htmlFor="approval-reason">Reason if you reject (optional)</label>
      <input id="approval-reason" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
      <div className="approval-actions">
        <button type="button" className="button button--primary" onClick={approve}>
          Approve and run
        </button>
        <button type="button" className="button button--danger" onClick={reject}>
          Reject
        </button>
      </div>
    </section>
  );
}
