from langchain_core.messages import AIMessage, HumanMessage

from src.agent_graph import SENSITIVE_TOOLS

READ_TOOLS = {"query_telemetry_db", "fetch_corridor_conditions", "search_compliance_sop"}


class RecordingLLM:
    def __init__(self):
        self.received = None

    def invoke(self, messages):
        self.received = messages
        return AIMessage(content="ok")


def test_system_prompt_reaches_the_llm_first(app_modules, monkeypatch):
    orchestrator = app_modules.orchestrator
    llm = RecordingLLM()
    monkeypatch.setattr(orchestrator, "llm_with_tools", llm)

    state = {"messages": [HumanMessage(content="Any breach near Los Angeles?")]}
    update = orchestrator.reasoning_node(state)

    assert llm.received[0] is orchestrator.SYSTEM_PROMPT
    assert llm.received[1].content == "Any breach near Los Angeles?"
    assert len(state["messages"]) == 1
    assert update["messages"][0].content == "ok"


def test_system_prompt_explains_every_tool(app_modules):
    orchestrator = app_modules.orchestrator
    for tool in orchestrator.fde_tools:
        assert tool.name in orchestrator.SYSTEM_PROMPT.content


def test_tools_that_act_are_gated_and_reads_are_not(app_modules):
    names = {tool.name for tool in app_modules.orchestrator.fde_tools}
    assert "create_incident_ticket" in SENSITIVE_TOOLS
    assert SENSITIVE_TOOLS <= names
    assert names - SENSITIVE_TOOLS == READ_TOOLS, "a new tool must be classified: add it to SENSITIVE_TOOLS or to READ_TOOLS"


def test_compiled_agent_contains_the_approval_step(app_modules):
    nodes = app_modules.orchestrator.fde_agent.get_graph().nodes
    assert {"reasoner", "approval", "tools"} <= set(nodes)
