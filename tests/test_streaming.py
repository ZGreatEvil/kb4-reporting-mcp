import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import openai
import pytest

from agent.agent import Agent
from agent.llm import LLMClient, LLMError
from agent.messages import msg
from config.settings import AppConfig, ConsoleConfig


def make_config(monkeypatch, **overrides):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    return AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")}, **overrides)


def call(call_id, name="get_account", arguments='{"console": "main"}'):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def end(content="", calls=None, finish="stop"):
    return SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls), finish_reason=finish)


class FakeStreamLLM:
    """each round is a list of ("content", text) / ("end", choice) items"""

    def __init__(self, rounds):
        self.rounds = list(rounds)

    async def chat_stream(self, messages, tools):
        for item in self.rounds.pop(0):
            if isinstance(item, Exception):
                raise item
            yield item

    async def chat(self, messages, tools):
        raise AssertionError("streaming path must not call chat()")


class Session:
    def __init__(self):
        self.calls = []

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name="get_account", description="d", input_schema={"type": "object"})])

    async def call_tool(self, name, arguments):
        self.calls.append(name)
        return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(text='{"current_risk_score": 39.4}')])


def make_agent(cfg, llm, session=None):
    session = session or Session()

    @asynccontextmanager
    async def factory():
        yield session

    return Agent(cfg, llm=llm, session_factory=factory), session


async def collect(agent, prompt="q", language="id"):
    return [e async for e in agent.ask_stream(prompt, language)]


async def test_text_streams_then_done(monkeypatch):
    llm = FakeStreamLLM([[("content", "Halo, "), ("content", "apa kabar"), ("end", end("Halo, apa kabar"))]])
    agent, _ = make_agent(make_config(monkeypatch), llm)
    events = await collect(agent)
    assert events == [
        {"type": "thinking"},
        {"type": "delta", "text": "Halo, "},
        {"type": "delta", "text": "apa kabar"},
        {"type": "done", "answer": "Halo, apa kabar", "note": ""},
    ]


async def test_tool_round_then_answer(monkeypatch):
    llm = FakeStreamLLM([
        [("end", end(calls=[call("c1")], finish="tool_calls"))],
        [("content", "Ok"), ("end", end("Ok"))],
    ])
    agent, session = make_agent(make_config(monkeypatch), llm)
    events = await collect(agent)
    assert [e["type"] for e in events] == ["thinking", "tool", "thinking", "delta", "done"]
    assert events[1] == {"type": "tool", "name": "get_account"}
    assert session.calls == ["get_account"]


async def test_text_in_tool_round_is_reset(monkeypatch):
    llm = FakeStreamLLM([
        [("content", "let me check"), ("end", end("let me check", calls=[call("c1")], finish="tool_calls"))],
        [("content", "Answer"), ("end", end("Answer"))],
    ])
    agent, _ = make_agent(make_config(monkeypatch), llm)
    types = [e["type"] for e in await collect(agent)]
    assert types == ["thinking", "delta", "reset", "tool", "thinking", "delta", "done"]


async def test_empty_answer_nudged_in_stream(monkeypatch):
    llm = FakeStreamLLM([[("end", end(""))], [("content", "Now"), ("end", end("Now"))]])
    agent, _ = make_agent(make_config(monkeypatch), llm)
    events = await collect(agent)
    assert events[-1]["type"] == "done" and events[-1]["answer"] == "Now"


async def test_loop_limit_in_stream(monkeypatch):
    llm = FakeStreamLLM([[("end", end(calls=[call("c1")], finish="tool_calls"))]])
    agent, _ = make_agent(make_config(monkeypatch, llm_max_tool_loops=1), llm)
    events = await collect(agent, language="en")
    assert events[-1] == {"type": "done", "answer": "Reached the limit of 1 tool-call rounds without a final answer. Try a narrower question."}


async def test_empty_question_in_stream(monkeypatch):
    agent, _ = make_agent(make_config(monkeypatch), FakeStreamLLM([]))
    assert await collect(agent, "  ", "en") == [{"type": "done", "answer": "Please enter a question first."}]


async def test_llm_error_propagates_from_stream(monkeypatch):
    llm = FakeStreamLLM([[LLMError("llm_unreachable", url="http://x")]])
    agent, _ = make_agent(make_config(monkeypatch), llm)
    with pytest.raises(LLMError):
        await collect(agent)


# the real chat_stream against a fake openai stream


class FakeChunks:
    def __init__(self, chunks, fail_after=None):
        self.chunks, self.fail_after = chunks, fail_after

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for i, c in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise openai.APIConnectionError(request=None)
            yield c


def chunk(content=None, tool_calls=None, finish=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


def tc(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


async def run_stream(monkeypatch, chunks, fail_after=None):
    client = LLMClient(make_config(monkeypatch))

    async def create(**kwargs):
        assert kwargs["stream"] is True
        return FakeChunks(chunks, fail_after)

    monkeypatch.setattr(client.client.chat.completions, "create", create)
    return [item async for item in client.chat_stream([], [])]


async def test_chat_stream_reassembles_split_tool_calls(monkeypatch):
    items = await run_stream(monkeypatch, [
        chunk(tool_calls=[tc(0, id="a", name="get_", arguments='{"con')]),
        chunk(tool_calls=[tc(0, name="account", arguments='sole": "main"}'), tc(1, id="b", name="list_users", arguments="{}")]),
        chunk(finish="tool_calls"),
    ])
    kind, choice = items[-1]
    assert kind == "end" and choice.finish_reason == "tool_calls"
    calls = choice.message.tool_calls
    assert [(c.id, c.function.name, c.function.arguments) for c in calls] == [
        ("a", "get_account", '{"console": "main"}'),
        ("b", "list_users", "{}"),
    ]


async def test_chat_stream_passes_text_through(monkeypatch):
    items = await run_stream(monkeypatch, [chunk("Hel"), chunk("lo"), chunk(finish="stop")])
    assert items[:2] == [("content", "Hel"), ("content", "lo")]
    assert items[-1][1].message.content == "Hello" and items[-1][1].message.tool_calls is None


async def test_chat_stream_failure_mid_stream_becomes_llm_error(monkeypatch):
    with pytest.raises(LLMError) as exc:
        await run_stream(monkeypatch, [chunk("partial"), chunk("more")], fail_after=1)
    assert exc.value.key == "llm_unreachable"


# the http endpoint


@pytest.fixture
def stream_client(monkeypatch):
    from fastapi.testclient import TestClient

    import web.main as web_main

    async def fake_stream(message, language="id", history=None):
        if message == "boom":
            raise LLMError("llm_model_missing", model="m")
            yield  # pragma: no cover
        yield {"type": "thinking"}
        yield {"type": "delta", "text": f"hi-{language}"}
        yield {"type": "done", "answer": f"hi-{language}"}

    monkeypatch.setattr(web_main.AGENT, "ask_stream", fake_stream)
    return TestClient(web_main.app)


def lines(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_stream_endpoint_sends_ndjson(stream_client):
    r = stream_client.post("/api/chat/stream", json={"message": "q", "language": "en"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert lines(r) == [{"type": "thinking"}, {"type": "delta", "text": "hi-en"}, {"type": "done", "answer": "hi-en"}]


def test_stream_endpoint_translates_errors(stream_client):
    r = stream_client.post("/api/chat/stream", json={"message": "boom", "language": "en"})
    assert lines(r) == [{"type": "error", "message": msg("llm_model_missing", "en", model="m")}]


def test_stream_endpoint_rejects_bad_language(stream_client):
    assert stream_client.post("/api/chat/stream", json={"message": "q", "language": "de"}).status_code == 422


async def test_chinese_slip_in_stream_is_reset_and_rewritten(monkeypatch):
    llm = FakeStreamLLM([
        [("content", "x 中文"), ("end", end("x 中文"))],
        [("content", "clean"), ("end", end("clean"))],
    ])
    agent, _ = make_agent(make_config(monkeypatch), llm)
    types = [e["type"] for e in await collect(agent)]
    assert types == ["thinking", "delta", "reset", "thinking", "delta", "done"]


async def test_presence_penalty_is_sent(monkeypatch):
    client = LLMClient(make_config(monkeypatch, llm_presence_penalty=0.0, llm_temperature=0.6))
    kwargs = client._kwargs([], [])
    assert kwargs["presence_penalty"] == 0.0 and kwargs["temperature"] == 0.6



async def test_numbers_without_tool_are_reset_in_stream(monkeypatch):
    llm = FakeStreamLLM([
        [("content", "User 1-20 semua 75.1"), ("end", end("User 1-20 semua 75.1"))],
        [("end", end(calls=[call("c1")], finish="tool_calls"))],
        [("content", "Skor 39.4"), ("end", end("Skor 39.4"))],
    ])
    agent, session = make_agent(make_config(monkeypatch), llm)
    events = await collect(agent, "siapa user paling berisiko?")
    types = [e["type"] for e in events]
    assert types[:3] == ["thinking", "delta", "reset"]
    assert session.calls == ["get_account"]
    assert events[-1]["answer"] == "Skor 39,4"
    assert "get_account" in events[-1]["note"]
