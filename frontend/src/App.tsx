import { useEffect, useState } from "react";
import { fetchHealth } from "./api/client";
import { useAgentChat } from "./hooks/useAgentChat";
import { useHashRoute, type Route } from "./hooks/useHashRoute";
import { AuditPage } from "./pages/AuditPage";
import { ConsolePage } from "./pages/ConsolePage";
import { JourneyPage } from "./pages/JourneyPage";
import type { Health } from "./types";

const NAV: { route: Route; label: string }[] = [
  { route: "journey", label: "Supply chain journey" },
  { route: "console", label: "Dispatch console" },
  { route: "audit", label: "Audit trail" },
];

export default function App() {
  const route = useHashRoute();
  const chat = useAgentChat();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
            <rect width="32" height="32" rx="7" fill="#111827" />
            <path d="M16 5v22M7 10.5l18 11M25 10.5l-18 11" stroke="#38BDF8" strokeWidth="2.4" strokeLinecap="round" />
          </svg>
          <span>Cold-Chain Copilot</span>
        </div>

        <nav aria-label="Main">
          {NAV.map((item) => (
            <a key={item.route} href={`#/${item.route}`} className={route === item.route ? "nav nav--on" : "nav"} aria-current={route === item.route ? "page" : undefined}>
              {item.label}
            </a>
          ))}
        </nav>

        <div className="sidebar-foot">
          <span className={`mode mode--${health?.mode ?? "offline"}`}>{health ? (health.mode === "demo" ? "Demo mode: scripted agent" : "Live agent") : "API offline"}</span>
          <span className="muted small">Session {chat.threadId.slice(0, 8)}</span>
          <button type="button" className="button" onClick={chat.reset}>
            New session
          </button>
        </div>
      </aside>

      <main className="main">
        {route === "console" && <ConsolePage chat={chat} />}
        {route === "journey" && <JourneyPage />}
        {route === "audit" && <AuditPage health={health} />}
      </main>
    </div>
  );
}
