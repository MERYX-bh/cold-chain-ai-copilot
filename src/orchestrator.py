import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

# ==========================================
# 1. SETUP & PATH RESOLUTION
# ==========================================
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parents[0]

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.agent_tools import query_telemetry_db, fetch_corridor_conditions, search_compliance_sop
from src.action_tools import create_incident_ticket
from src.agent_graph import build_graph

load_dotenv(project_root / ".env")

# ==========================================
# 2. FACTORY INITIALIZATION: AGENT REASONER LLM
# ==========================================

AGENT_LLM_SETTING = os.getenv("Agent_llm", "OLLAMA").strip().upper()

if AGENT_LLM_SETTING == "OPENAI":
    print("🤖 Brain Mode: Utilizing Cloud OpenAI Reasoner (gpt-4o)...")
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

elif AGENT_LLM_SETTING == "DEEPSEEK":
    print("🐳 Brain Mode: Utilizing Flagship DeepSeek Cloud Reasoner (deepseek-v4-pro)...")
    from langchain_openai import ChatOpenAI

    # Fully updated to match 2026 DeepSeek API parameters and endpoint contracts
    llm = ChatOpenAI(
        model="deepseek-v4-flash",                           # deepseek-v4-flash, deepseek-v4-pro
        temperature=0,
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",     # Fixed connection string url endpoint
        max_tokens=2048,                                   # Gives the deep reasoner plenty of output runway
        # extra_body={
        #     "thinking": {"type": "enabled"},              # Activates DeepSeek Deep-Thinking mode
        #     "reasoning_effort": "high"                     # Drives maximal reasoning depth for logic maps
        # }
    )

else:  # FALLBACK / DEFAULT RUNNER MODE
    print("🤗 Brain Mode: Local Fallback Activated. Binding Local Ollama (qwen2.5:7b)...")
    from langchain_community.chat_models import ChatOllama
    llm = ChatOllama(model="qwen2.5:7b", temperature=0, num_predict=1024)

# Read tools run freely; create_incident_ticket is gated by the human approval node.
fde_tools = [query_telemetry_db, fetch_corridor_conditions, search_compliance_sop, create_incident_ticket]
llm_with_tools = llm.bind_tools(fde_tools)

# ==========================================
# 3. GRAPH ARCHITECTURE ASSEMBLY
# ==========================================
prompt_path = project_root / "src" / "prompts" / "system_prompt.txt"
try:
    SYSTEM_PROMPT = SystemMessage(content=prompt_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    print(f"Error: Could not find {prompt_path}")
    SYSTEM_PROMPT = SystemMessage(content="You are a helpful AI assistant.")

def reasoning_node(state):
    # The system prompt is prepended on every call, so it applies to the CLI and the UI alike.
    response = llm_with_tools.invoke([SYSTEM_PROMPT, *state["messages"]])
    return {"messages": [response]}

print("⚙️ Compiling LangGraph FDE Orchestrator...")
fde_agent = build_graph(reasoning_node, fde_tools, MemorySaver())

# ==========================================
# 4. CHAT LOOP TESTING PANEL
# ==========================================
def ask_operator(request: dict) -> dict:
    print("\n" + "!" * 55)
    print("✋ HUMAN APPROVAL REQUIRED - the agent wants to act:")
    for call in request["tool_calls"]:
        print(f"\n  Action: {call['name']}")
        print(json.dumps(call["args"], indent=2, ensure_ascii=False))
    print("!" * 55)

    while True:
        choice = input("[a]pprove / [e]dit / [r]eject > ").strip().lower()
        if choice in ("a", "approve"):
            return {"action": "approve"}
        if choice in ("e", "edit"):
            new_args = {}
            try:
                for call in request["tool_calls"]:
                    raw = input(f"Full corrected JSON args for {call['name']} (empty = keep): ").strip()
                    if raw:
                        new_args[call["id"]] = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON ({e}). Try again.")
                continue
            return {"action": "edit", "args": new_args}
        if choice in ("r", "reject"):
            return {"action": "reject", "reason": input("Reason (optional): ").strip() or "No reason given."}


def run_turn(payload, config):
    while True:
        approval_request = None
        for event in fde_agent.stream(payload, config=config, stream_mode="updates"):
            if "__interrupt__" in event:
                approval_request = event["__interrupt__"][0].value
                continue
            for node_name, node_state in event.items():
                if not node_state:
                    continue
                if node_name == "tools":
                    print("   [System] 🔄 Retrieving external data elements via ToolNode...")
                elif node_name == "reasoner":
                    latest_msg = node_state["messages"][-1]
                    if latest_msg.content:
                        print(f"\n🤖 FDE Agent:\n{latest_msg.content}")

        if approval_request is None:
            return
        payload = Command(resume=ask_operator(approval_request))


if __name__ == "__main__":
    print("\n" + "="*55)
    print("🚀 FDE Supply Chain Orchestrator State Machine Online")
    print(f"   Configured Execution: [LLM: {AGENT_LLM_SETTING}] -> [Embeddings: {os.getenv('Embeddings_model', 'LOCAL')}]")
    print("="*55 + "\n")

    thread_config = {"configurable": {"thread_id": "production_test_1"}}

    while True:
        user_input = input("\nDispatcher > ")
        if user_input.lower() in ['exit', 'quit']:
            break

        run_turn({"messages": [("user", user_input)]}, thread_config)
