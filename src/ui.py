import os
import sys
import uuid
import json
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

# ==========================================
# 1. IMMEDIATE PATH & ENVIRONMENT RESOLUTION
# ==========================================
script_dir = Path(__file__).resolve().parent  # points to src/
project_root = script_dir.parent              # climbs to project root

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

# Import the compiled graph and tools list dynamically
from src.orchestrator import fde_agent

# ==========================================
# 2. SQL CREDENTIALS MAPPING FROM .ENV
# ==========================================
db_host = os.getenv("SQL_SERVER_HOST", "localhost")
db_port = os.getenv("SQL_SERVER_PORT", "1433")
db_user = os.getenv("SQL_AGENT_USER", "USR_FDE_RO")
db_password = os.getenv("SQL_AGENT_PASSWORD")

# Engine for the Agent to write logs using its standard credentials
connection_string = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={db_host},{db_port};"
    f"DATABASE=master;"
    f"UID={db_user};"
    f"PWD={db_password};"
    f"Encrypt=no;"
    f"TrustServerCertificate=yes;"
)

log_params = urllib.parse.quote_plus(connection_string)

log_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={log_params}")

def write_audit_log(session_id, node_name, tool_name, content):
    """Silently writes agent execution traces to the SQL audit table using agent permissions."""
    try:
        with log_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO FDE_VIEWS.AgentAuditLog (SessionID, NodeExecuted, ToolName, Content)
                VALUES (:session_id, :node_name, :tool_name, :content)
            """), {
                "session_id": session_id,
                "node_name": node_name,
                "tool_name": tool_name,
                "content": content
            })
            conn.commit()
    except Exception as e:
        print(f"Audit Log Failed (Silent): {e}")

# ==========================================
# 3. PAGE CONFIGURATION & ENTERPRISE THEME
# ==========================================
st.set_page_config(
    page_title="FDE Supply Chain Dispatch Console",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #0B0E14; color: #E2E8F0; }
    div[data-testid="stSidebar"] { background-color: #111622; border-right: 1px solid #1E293B; }
    .stMarkdown code { background-color: #1E293B !important; color: #38BDF8 !important; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 4. MULTI-USER STATE & THREAD MANAGEMENT
# ==========================================
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = []

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

thread_config = {"configurable": {"thread_id": st.session_state.thread_id}}

# ==========================================
# 5. AGENT RUN HELPERS (STREAMING + HUMAN APPROVAL)
# ==========================================
def render_trace(trace):
    if trace["type"] == "tool_input":
        st.markdown(f"**⚡ Intent Recognized:** `{trace['name']}`")
        with st.expander(f"📥 View Generated Input ({trace['name']})", expanded=False):
            st.json(trace["args"])
    elif trace["type"] == "tool_output":
        with st.expander(f"📤 View Raw Output ({trace['name']})", expanded=False):
            st.code(trace["content"], language="text")


def stream_agent(stream_input, traces):
    """Runs the agent until it answers or pauses for approval. Returns (final_response, traces, approval_request)."""
    final_response = ""
    approval_request = None

    with st.status("🧠 Initializing Core Reasoner Node...", expanded=True) as status:
        events = fde_agent.stream(stream_input, config=thread_config, stream_mode="updates")

        for event in events:
            if "__interrupt__" in event:
                approval_request = event["__interrupt__"][0].value
                continue

            for node_name, node_state in event.items():
                if not node_state:
                    continue

                if node_name == "reasoner":
                    latest_msg = node_state["messages"][-1]

                    # A. Intercept Tool Call Requests (Inputs)
                    if hasattr(latest_msg, "tool_calls") and latest_msg.tool_calls:
                        status.update(label="🧠 Agent generated tool parameters...")
                        for tool_call in latest_msg.tool_calls:
                            trace = {"type": "tool_input", "name": tool_call["name"], "args": tool_call["args"]}
                            traces.append(trace)
                            render_trace(trace)

                            write_audit_log(
                                session_id=st.session_state.thread_id,
                                node_name="reasoner",
                                tool_name=tool_call["name"],
                                content=json.dumps(tool_call["args"])
                            )

                    # B. Intercept Final Generation
                    if latest_msg.content:
                        final_response = latest_msg.content
                        status.update(label="📝 Generating Operational Resolution Report...")

                        write_audit_log(
                            session_id=st.session_state.thread_id,
                            node_name="reasoner_final",
                            tool_name="LLM Text Synthesis",
                            content=final_response
                        )

                elif node_name in ("tools", "approval"):
                    if node_name == "tools":
                        status.update(label="🔧 Executing Enterprise Subsystem Tools...")
                    # "approval" only emits ToolMessages when the operator rejected the action
                    for msg in node_state.get("messages", []):
                        if isinstance(msg, ToolMessage):
                            trace = {"type": "tool_output", "name": msg.name, "content": msg.content}
                            traces.append(trace)
                            render_trace(trace)

                            write_audit_log(
                                session_id=st.session_state.thread_id,
                                node_name=node_name,
                                tool_name=msg.name,
                                content=msg.content
                            )

        if approval_request:
            status.update(label="✋ Paused: waiting for operator approval", state="complete", expanded=True)
        else:
            status.update(label="Incident Matrix Evaluation Complete", state="complete", expanded=False)

    return final_response, traces, approval_request


def conclude_turn(final_response, traces, approval_request):
    if approval_request:
        st.session_state.pending_approval = {"request": approval_request, "traces": traces}
        st.rerun()

    if final_response:
        st.markdown(final_response)
        st.session_state.ui_messages.append({
            "role": "assistant",
            "content": final_response,
            "traces": traces
        })
    else:
        error_fallback = "⚠️ Execution Timeout: System engine encountered an unresolved processing edge case."
        st.error(error_fallback)

# ==========================================
# 6. SIDEBAR NAVIGATION & METADATA
# ==========================================
with st.sidebar:
    st.image(str(script_dir / "image_L25X5q.png") if (script_dir / "image_L25X5q.png").exists() else "https://cdn-icons-png.flaticon.com/512/2830/2830305.png", width=65)
    st.title("FDE Command Center")

    app_mode = st.radio("System Mode", ["🧊 Dispatch Console", "🛡️ Security & Audit Logs"])

    st.markdown("---")
    st.caption(f"Session Token: `{st.session_state.thread_id[:8]}...`")
    st.markdown(f"**Reasoning Architecture:** `{os.getenv('Agent_llm', 'DEEPSEEK')}`")

    st.markdown("---")
    if st.button("🗑️ Purge Dispatch Workspace Session", use_container_width=True):
        st.session_state.ui_messages = []
        st.session_state.pending_approval = None
        st.session_state.thread_id = str(uuid.uuid4())
        st.rerun()

# ==========================================
# 7. VIEW ROUTING (DISPATCH VS AUDIT)
# ==========================================

if app_mode == "🧊 Dispatch Console":
    # ------------------------------------------
    # TAB 1: CHAT UI & AGENT EXECUTION
    # ------------------------------------------
    st.title("Cold-Chain Incident Control Dashboard")
    st.caption("Production Data Engineering Pipeline • Real-Time Decision Optimization Platform")

    for entry in st.session_state.ui_messages:
        with st.chat_message(entry["role"], avatar="👤" if entry["role"] == "user" else "🤖"):
            for trace in entry.get("traces", []):
                render_trace(trace)
            st.markdown(entry["content"])

    # ------------------------------------------
    # HUMAN-IN-THE-LOOP: APPROVAL CARD
    # ------------------------------------------
    pending = st.session_state.pending_approval
    approve = reject = False
    approval_slot = st.empty()

    if pending:
        request_calls = pending["request"]["tool_calls"]
        single_call = len(request_calls) == 1
        args_by_id = {call["id"]: call["args"] for call in request_calls}
        editable_args = request_calls[0]["args"] if single_call else args_by_id

        with approval_slot.container():
            with st.chat_message("assistant", avatar="🛡️"):
                for trace in pending["traces"]:
                    render_trace(trace)
                st.warning("✋ Human approval required: the agent wants to perform an action.")
                for call in request_calls:
                    st.markdown(f"**Proposed action:** `{call['name']}`")

                with st.form("approval_form"):
                    edited_text = st.text_area(
                        "Arguments (editable JSON)",
                        value=json.dumps(editable_args, indent=2, ensure_ascii=False),
                        height=280
                    )
                    reject_reason = st.text_input("Rejection reason (optional)")
                    col_approve, col_reject = st.columns(2)
                    approve = col_approve.form_submit_button("✅ Approve & execute", use_container_width=True)
                    reject = col_reject.form_submit_button("⛔ Reject", use_container_width=True)

    if pending and (approve or reject):
        if approve:
            try:
                parsed = json.loads(edited_text)
                if not isinstance(parsed, dict):
                    raise ValueError("arguments must be a JSON object")
            except ValueError as e:
                st.error(f"Invalid JSON arguments: {e}")
                st.stop()

            edited_by_id = {request_calls[0]["id"]: parsed} if single_call else parsed
            if edited_by_id != args_by_id:
                decision = {"action": "edit", "args": edited_by_id}
            else:
                decision = {"action": "approve"}
        else:
            decision = {"action": "reject", "reason": reject_reason.strip() or "No reason given."}

        write_audit_log(
            session_id=st.session_state.thread_id,
            node_name="approval",
            tool_name=", ".join(call["name"] for call in request_calls),
            content=json.dumps(decision, ensure_ascii=False)
        )

        approval_slot.empty()
        st.session_state.pending_approval = None

        with st.chat_message("assistant", avatar="🤖"):
            for trace in pending["traces"]:
                render_trace(trace)
            conclude_turn(*stream_agent(Command(resume=decision), pending["traces"]))

    # ------------------------------------------
    # NEW USER QUESTION
    # ------------------------------------------
    if user_input := st.chat_input(
        "Query fleet telemetry, corridor updates, or compliance thresholds...",
        disabled=st.session_state.pending_approval is not None
    ):
        st.session_state.ui_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🤖"):
            conclude_turn(*stream_agent({"messages": [HumanMessage(content=user_input)]}, []))


elif app_mode == "🛡️ Security & Audit Logs":
    # ------------------------------------------
    # TAB 2: AUDIT LOG VIEWER (REQUIRES ADMIN CREDENTIALS FROM .ENV OR INPUT)
    # ------------------------------------------
    st.title("🛡️ Enterprise Agent Audit Trail")
    st.caption("Secure database inspection of FDE_VIEWS.AgentAuditLog")

    st.markdown("### Database Authorization Gate")
    st.markdown("Enter high-privilege administrative credentials (defined in `.env` as `SQL_ADMIN_USER`) to query audit logs.")

    with st.form("admin_auth_form"):
        col1, col2 = st.columns(2)
        with col1:
            input_user = st.text_input("Admin Username", value=os.getenv("SQL_ADMIN_USER", ""))
        with col2:
            input_pass = st.text_input("Admin Password", type="password", value="")

        submit_admin = st.form_submit_button("Authenticate & Load Logs", use_container_width=True)

    if submit_admin:
        expected_admin_user = os.getenv("SQL_ADMIN_USER")
        expected_admin_pass = os.getenv("SQL_ADMIN_PASSWORD")

        if input_user == expected_admin_user and input_pass == expected_admin_pass:
            try:
                # Build an isolated admin connection string for viewing data
                admin_params = urllib.parse.quote_plus(
                    "DRIVER={ODBC Driver 18 for SQL Server};"
                    f"SERVER={db_host},{db_port};"
                    "DATABASE=master;"
                    f"UID={input_user};"
                    f"PWD={input_pass};"
                    "Encrypt=no;"
                    "TrustServerCertificate=yes;"
                )
                admin_engine = create_engine(f"mssql+pyodbc:///?odbc_connect={admin_params}")

                with admin_engine.connect() as conn:
                    query = """
                        SELECT LogID, Timestamp, SessionID, NodeExecuted, ToolName, Content
                        FROM FDE_VIEWS.AgentAuditLog
                        ORDER BY Timestamp DESC
                    """
                    df = pd.read_sql(query, conn)

                st.success("✅ Authenticated successfully as Admin.")

                if not df.empty:
                    st.dataframe(
                        df,
                        column_config={
                            "LogID": st.column_config.NumberColumn("ID", format="%d"),
                            "Timestamp": st.column_config.DatetimeColumn("Execution Time", format="DD/MM/YYYY-h:mm a"),
                            "SessionID": "Session Token",
                            "NodeExecuted": "Graph Node",
                            "ToolName": "Tool Triggered",
                            "Content": "Raw Payload Data"
                        },
                        hide_index=True,
                        use_container_width=True,
                        height=600
                    )
                else:
                    st.info("No audit logs found in the database. Run a query in the Dispatch Console first.")

            except Exception as e:
                st.error(f"Database Query Failed: {e}")
        else:
            st.error("❌ Invalid Administrator Credentials.")
