import { parseSse } from "../lib/sse";
import type { AuditRow, ChatBody, Health, StreamEvent } from "../types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((item: { msg: string }) => item.msg).join("; ");
  } catch {
    // fall through to the status text
  }
  return `${response.status} ${response.statusText}`.trim();
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "Cannot reach the server. Is the API running on port 8000?";
  return error instanceof Error ? error.message : "Something went wrong.";
}

export async function streamChat(body: ChatBody, onEvent: (event: StreamEvent) => void, signal: AbortSignal): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  if (!response.body) throw new Error("The server sent no stream.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSse(buffer);
    buffer = parsed.rest;
    for (const { event, data } of parsed.events) {
      onEvent({ type: event, data } as StreamEvent);
    }
  }
}

export async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return response.json();
}

export async function login(username: string, password: string): Promise<string> {
  const response = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return (await response.json()).token;
}

export async function fetchAudit(token: string, limit = 200): Promise<AuditRow[]> {
  const response = await fetch(`/api/audit?limit=${limit}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return (await response.json()).rows;
}
