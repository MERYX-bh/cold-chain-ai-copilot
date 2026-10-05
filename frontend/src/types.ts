export type ToolCall = { id: string; name: string; args: Record<string, unknown> };

export type Trace =
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; content: string };

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  traces: Trace[];
};

export type ApprovalRequest = { tool_calls: ToolCall[] };

export type Decision = {
  action: "approve" | "edit" | "reject";
  args?: Record<string, Record<string, unknown>>;
  reason?: string;
};

export type StreamEvent =
  | { type: "tool_call"; data: ToolCall }
  | { type: "tool_result"; data: { name: string; content: string } }
  | { type: "approval_request"; data: ApprovalRequest }
  | { type: "final"; data: { content: string } }
  | { type: "error"; data: { message: string } }
  | { type: "done"; data: Record<string, never> };

export type ChatBody =
  | { thread_id: string; message: string }
  | { thread_id: string; decision: Decision };

export type AuditRow = {
  LogID: number;
  Timestamp: string;
  SessionID: string | null;
  NodeExecuted: string | null;
  ToolName: string | null;
  Content: string | null;
};

export type Health = { status: string; mode: "demo" | "live" };
