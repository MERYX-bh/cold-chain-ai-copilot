import importlib
import sys
import types
from types import SimpleNamespace

import pytest


class _FakeRetriever:
    def invoke(self, query):
        return []


class _FakePineconeVectorStore:
    """Stands in for the real store, which would call Pinecone as soon as it is created."""

    def __init__(self, **kwargs):
        pass

    def as_retriever(self, **kwargs):
        return _FakeRetriever()


@pytest.fixture(scope="session")
def app_modules():
    """Imports src.agent_tools and src.orchestrator with no Pinecone, no real API key and no model download."""
    mp = pytest.MonkeyPatch()
    mp.setenv("PINECONE_API_KEY", "test-key")
    mp.setenv("OPENAI_API_KEY", "test-key")
    mp.setenv("Embeddings_model", "OPENAI")
    mp.setenv("Agent_llm", "OPENAI")

    fake_pinecone = types.ModuleType("langchain_pinecone")
    fake_pinecone.PineconeVectorStore = _FakePineconeVectorStore
    mp.setitem(sys.modules, "langchain_pinecone", fake_pinecone)

    for name in ("src.agent_tools", "src.orchestrator"):
        sys.modules.pop(name, None)

    agent_tools = importlib.import_module("src.agent_tools")
    orchestrator = importlib.import_module("src.orchestrator")

    yield SimpleNamespace(agent_tools=agent_tools, orchestrator=orchestrator)

    for name in ("src.agent_tools", "src.orchestrator"):
        sys.modules.pop(name, None)
    mp.undo()
