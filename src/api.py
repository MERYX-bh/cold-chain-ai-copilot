import asyncio
import hmac
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator, model_validator

from src.audit import MemoryAuditLog, SqlAuditLog

logger = logging.getLogger("coldchain.api")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADMIN_TOKEN_TTL_SECONDS = 3600


class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    args: Optional[dict[str, dict]] = None
    reason: Optional[str] = Field(default=None, max_length=500)


class ChatRequest(BaseModel):
    thread_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    message: Optional[str] = Field(default=None, max_length=4000)
    decision: Optional[Decision] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("message must not be blank")
        return value

    @model_validator(mode="after")
    def exactly_one_input(self):
        if (self.message is None) == (self.decision is None):
            raise ValueError("send either 'message' or 'decision'")
        return self


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=200)


class AdminSessions:
    def __init__(self):
        self._tokens = {}
        self._lock = threading.Lock()

    def issue(self):
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token] = time.time() + ADMIN_TOKEN_TTL_SECONDS
        return token

    def is_valid(self, token):
        with self._lock:
            expires = self._tokens.get(token)
            if expires is None:
                return False
            if expires < time.time():
                del self._tokens[token]
                return False
            return True


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def as_text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)


def pending_interrupts(agent, config):
    return [item for task in agent.get_state(config).tasks for item in task.interrupts]


def load_agent(demo: bool):
    if demo:
        from src.demo_agent import build_demo_agent
        return build_demo_agent()
    from src.orchestrator import fde_agent
    return fde_agent


def run_agent(agent, audit, thread_id, payload):
    """Runs the agent and yields server-sent events until it answers or pauses for approval."""
    config = {"configurable": {"thread_id": thread_id}}
    answered = paused = False

    try:
        for event in agent.stream(payload, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                paused = True
                yield sse("approval_request", event["__interrupt__"][0].value)
                continue

            for node_name, node_state in event.items():
                if not node_state:
                    continue

                if node_name == "reasoner":
                    message = node_state["messages"][-1]
                    if getattr(message, "tool_calls", None):
                        for call in message.tool_calls:
                            audit.write(thread_id, "reasoner", call["name"], json.dumps(call["args"]))
                            yield sse("tool_call", {"id": call["id"], "name": call["name"], "args": call["args"]})
                    elif message.content:
                        answered = True
                        content = as_text(message.content)
                        audit.write(thread_id, "reasoner_final", "LLM Text Synthesis", content)
                        yield sse("final", {"content": content})

                elif node_name in ("tools", "approval"):
                    for message in node_state.get("messages", []):
                        if isinstance(message, ToolMessage):
                            audit.write(thread_id, node_name, message.name, as_text(message.content))
                            yield sse("tool_result", {"name": message.name, "content": as_text(message.content)})

        if not answered and not paused:
            yield sse("error", {"message": "The agent finished without an answer."})
    except Exception:
        logger.exception("Agent run failed")
        yield sse("error", {"message": "The agent failed. Check the server logs for details."})
    yield sse("done", {})


def create_app(agent=None, audit=None, demo=None, admin_credentials=None, static_dir=None) -> FastAPI:
    demo = os.getenv("COLDCHAIN_DEMO") == "1" if demo is None else demo
    agent = agent if agent is not None else load_agent(demo)
    audit = audit if audit is not None else (MemoryAuditLog() if demo else SqlAuditLog())
    if admin_credentials is None:
        admin_credentials = ("demo", "demo") if demo else (os.getenv("SQL_ADMIN_USER"), os.getenv("SQL_ADMIN_PASSWORD"))
    sessions = AdminSessions()

    app = FastAPI(title="Cold-chain AI copilot", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def require_admin(authorization: Optional[str] = Header(default=None)):
        token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
        if not sessions.is_valid(token):
            raise HTTPException(status_code=401, detail="Admin login required.")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "demo" if demo else "live"}

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        config = {"configurable": {"thread_id": request.thread_id}}
        waiting = pending_interrupts(agent, config)

        if request.decision is not None:
            if not waiting:
                raise HTTPException(status_code=409, detail="No action is waiting for approval in this conversation.")
            decision = request.decision.model_dump(exclude_none=True)
            names = ", ".join(call["name"] for call in waiting[0].value.get("tool_calls", [])) or "approval"
            audit.write(request.thread_id, "approval", names, json.dumps(decision, ensure_ascii=False))
            payload = Command(resume=decision)
        else:
            if waiting:
                raise HTTPException(status_code=409, detail="Approve or reject the pending action first.")
            payload = {"messages": [HumanMessage(content=request.message)]}

        return StreamingResponse(
            run_agent(agent, audit, request.thread_id, payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/admin/login")
    async def admin_login(request: LoginRequest):
        user, password = admin_credentials
        if not user or not password:
            raise HTTPException(status_code=503, detail="Admin credentials are not configured on the server.")
        valid = hmac.compare_digest(request.username.encode(), user.encode()) & hmac.compare_digest(request.password.encode(), password.encode())
        if not valid:
            await asyncio.sleep(0.6)
            raise HTTPException(status_code=401, detail="Invalid administrator credentials.")
        return {"token": sessions.issue(), "expires_in": ADMIN_TOKEN_TTL_SECONDS}

    @app.get("/api/audit", dependencies=[Depends(require_admin)])
    def audit_trail(limit: int = Query(default=200, ge=1, le=1000)):
        try:
            return {"rows": audit.read(limit)}
        except Exception:
            logger.exception("Audit read failed")
            raise HTTPException(status_code=502, detail="The audit table could not be read. Check the database connection.")

    static_path = Path(static_dir) if static_dir else PROJECT_ROOT / "frontend" / "dist"
    if static_path.is_dir():
        app.mount("/", StaticFiles(directory=static_path, html=True), name="web")

    return app
