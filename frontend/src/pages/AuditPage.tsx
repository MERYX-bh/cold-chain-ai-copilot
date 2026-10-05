import { useCallback, useState, type FormEvent } from "react";
import { ApiError, describeError, fetchAudit, login } from "../api/client";
import type { AuditRow, Health } from "../types";

export function AuditPage({ health }: { health: Health | null }) {
  const [token, setToken] = useState<string | null>(null);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);

  const load = useCallback(async (activeToken: string) => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchAudit(activeToken));
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        setToken(null);
        setError("Your admin session expired. Sign in again.");
      } else {
        setError(describeError(failure));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const signIn = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const newToken = await login(username, password);
      setToken(newToken);
      setPassword("");
      await load(newToken);
    } catch (failure) {
      setError(describeError(failure));
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="audit">
        <header className="page-head">
          <h1>Audit trail</h1>
          <p className="muted">Every proposal, decision and tool result of the agent. Reading it needs the administrator account.</p>
        </header>
        <form className="card login" onSubmit={signIn}>
          <h2>Administrator sign-in</h2>
          {health?.mode === "demo" && <p className="banner">Demo mode: sign in with <code>demo</code> / <code>demo</code>.</p>}
          <label htmlFor="admin-user">Username</label>
          <input id="admin-user" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          <label htmlFor="admin-pass">Password</label>
          <input id="admin-pass" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="button button--primary" disabled={loading}>
            {loading ? "Signing in" : "Sign in"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="audit">
      <header className="page-head page-head--row">
        <div>
          <h1>Audit trail</h1>
          <p className="muted">{rows.length} most recent entries, newest first.</p>
        </div>
        <div className="actions">
          <button type="button" className="button" onClick={() => void load(token)} disabled={loading}>
            {loading ? "Refreshing" : "Refresh"}
          </button>
          <button type="button" className="button" onClick={() => setToken(null)}>
            Sign out
          </button>
        </div>
      </header>

      {error && (
        <p className="banner banner--error" role="alert">
          {error}
        </p>
      )}

      {rows.length === 0 && !loading ? (
        <p className="card muted">No entries yet. Ask the agent something in the console first.</p>
      ) : (
        <div className="table-wrap card">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Time</th>
                <th>Session</th>
                <th>Step</th>
                <th>Tool</th>
                <th>Payload</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.LogID}>
                  <td>{row.LogID}</td>
                  <td className="nowrap">{new Date(row.Timestamp).toLocaleString()}</td>
                  <td className="mono">{row.SessionID?.slice(0, 8)}</td>
                  <td>{row.NodeExecuted}</td>
                  <td>{row.ToolName}</td>
                  <td>
                    <button type="button" className="link" onClick={() => setOpen(open === row.LogID ? null : row.LogID)} aria-expanded={open === row.LogID}>
                      {open === row.LogID ? "Hide" : "Show"}
                    </button>
                    {open === row.LogID && <pre>{row.Content}</pre>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
