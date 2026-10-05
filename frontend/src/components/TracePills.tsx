import { toolInfo } from "../lib/toolInfo";
import type { Trace } from "../types";

export function TracePills({ traces }: { traces: Trace[] }) {
  if (traces.length === 0) return null;
  return (
    <div className="traces">
      {traces.map((trace, index) => (
        <details key={index} className={`trace trace--${trace.type}`}>
          <summary>
            <span className="trace-dot" aria-hidden="true" />
            <span className="trace-name">{toolInfo(trace.name).label}</span>
            <span className="trace-kind">{trace.type === "tool_call" ? "input" : "result"}</span>
          </summary>
          <pre>{trace.type === "tool_call" ? JSON.stringify(trace.args, null, 2) : trace.content}</pre>
        </details>
      ))}
    </div>
  );
}
