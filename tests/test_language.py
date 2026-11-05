import string
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.agent import Agent, build_system_prompt
from agent.llm import LLMError
from agent.messages import LANGUAGE_NAMES, MESSAGES, msg
from config.settings import AppConfig, ConsoleConfig


def test_every_message_has_both_languages_with_same_placeholders():
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
    for key, texts in MESSAGES.items():
        assert set(texts) == set(LANGUAGE_NAMES), key
        assert fields(texts["id"]) == fields(texts["en"]), key


def test_unknown_language_falls_back_to_indonesian():
    assert msg("no_answer", "fr") == MESSAGES["no_answer"]["id"]


@pytest.mark.parametrize("language,name", [("id", "Indonesian"), ("en", "English")])
def test_prompt_follows_language(monkeypatch, language, name):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")})
    prompt = build_system_prompt(cfg, language)
    assert f"Answer in {name} unless" in prompt
    assert "Do not add scales, benchmarks, ratings or interpretations" in prompt


def test_llm_error_translates():
    err = LLMError("llm_model_missing", model="m:1b")
    assert "belum tersedia" in str(err)
    assert err.text("en") == "Model 'm:1b' is not available on the LLM server. Run: ollama pull m:1b"


async def test_agent_messages_follow_language(monkeypatch):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")}, llm_max_tool_loops=1)

    class LoopingLLM:
        def __init__(self):
            self.system = None

        async def chat(self, messages, tools):
            self.system = messages[0]["content"]
            call = SimpleNamespace(id="c1", function=SimpleNamespace(name="get_account", arguments='{"console": "main"}'))
            return SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[call]), finish_reason="tool_calls")

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="get_account", description="d", input_schema={"type": "object"})])

        async def call_tool(self, name, arguments):
            return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(text="{}")])

    @asynccontextmanager
    async def factory():
        yield Session()

    llm = LoopingLLM()
    agent = Agent(cfg, llm=llm, session_factory=factory)
    assert await agent.ask("x", "en") == "Reached the limit of 1 tool-call rounds without a final answer. Try a narrower question."
    assert "Answer in English" in llm.system
    assert await agent.ask("   ", "en") == "Please enter a question first."
    assert await agent.ask("   ") == "Masukkan pertanyaan terlebih dahulu."


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import web.main as web_main

    seen = {}

    async def fake_ask(message, language="id"):
        seen["language"] = language
        if message == "boom":
            raise LLMError("llm_unreachable", url="http://x")
        return f"ok:{language}"

    monkeypatch.setattr(web_main.AGENT, "ask", fake_ask)
    return TestClient(web_main.app), seen


def test_api_defaults_to_indonesian(client):
    c, seen = client
    assert c.post("/api/chat", json={"message": "hi"}).json()["answer"] == "ok:id"
    assert seen["language"] == "id"


def test_api_passes_english(client):
    c, seen = client
    assert c.post("/api/chat", json={"message": "hi", "language": "en"}).json()["answer"] == "ok:en"


def test_api_rejects_other_languages(client):
    c, _ = client
    assert c.post("/api/chat", json={"message": "hi", "language": "fr"}).status_code == 422


@pytest.mark.parametrize("language,expected", [("id", "Masukkan pertanyaan terlebih dahulu."), ("en", "Please enter a question first.")])
def test_api_empty_message_translated(client, language, expected):
    c, _ = client
    assert c.post("/api/chat", json={"message": "  ", "language": language}).json()["answer"] == expected


def test_api_llm_error_translated(client):
    c, _ = client
    body = c.post("/api/chat", json={"message": "boom", "language": "en"}).json()
    assert body == {"answer": "Cannot reach the LLM server at http://x. Make sure Ollama is running.", "error_type": "LLMError"}
