import { ChatPanel } from "../components/ChatPanel";
import { RouteMap } from "../components/RouteMap";
import { prefersReducedMotion, useAnimatedProgress } from "../hooks/useAnimatedProgress";
import type { useAgentChat } from "../hooks/useAgentChat";
import { toolInfo } from "../lib/toolInfo";

const TOOLS = [
  ["query_telemetry_db", "Reads fleet sensors in SQL Server"],
  ["fetch_corridor_conditions", "Live weather along the road"],
  ["search_compliance_sop", "Searches your procedures"],
  ["create_incident_ticket", "Opens a ticket, needs approval"],
] as const;

export function ConsolePage({ chat }: { chat: ReturnType<typeof useAgentChat> }) {
  const [progress] = useAnimatedProgress({ playing: !prefersReducedMotion(), speed: 1, durationSeconds: 50, loop: true });
  const { state } = chat;

  return (
    <div className="console">
      <ChatPanel state={state} onSend={chat.send} onDecide={chat.decide} />

      <aside className="side" aria-label="Agent activity">
        <div className="card">
          <h2>Live route</h2>
          <p className="muted">Illustrative shipment. The agent&apos;s tool calls light up on it as they run.</p>
          <RouteMap scenario="normal" progress={progress} activeTool={state.activeTool} compact />
        </div>

        <div className="card">
          <h2>Agent tools</h2>
          <ul className="tool-list">
            {TOOLS.map(([name, description]) => (
              <li key={name} className={state.activeTool === name ? "tool tool--active" : "tool"}>
                <span className="tool-dot" aria-hidden="true" />
                <div>
                  <strong>{toolInfo(name).label}</strong>
                  <span>{description}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
