import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from agent.agent import Agent
from agent.llm import LLMClient, LLMError
from config.settings import AppConfig, ConsoleConfig


def make_config(monkeypatch, **overrides):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    monkeypatch.delenv("KB4_T_OFF", raising=False)
    consoles = {
        "main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN"),
        "off": ConsoleConfig(display_name="Off", api_key_env="KB4_T_OFF"),
    }
    return AppConfig(consoles=consoles, **overrides)


def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


def reply(content=None, calls=None, finish="stop", reasoning=None):
    message = SimpleNamespace(content=content, tool_calls=calls, reasoning=reasoning)
    return SimpleNamespace(message=message, finish_reason=finish)


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    async def chat(self, messages, tools):
        # copy, since the agent keeps appending to the same list
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        return self.replies.pop(0)


class FakeSession:
    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []
        names = ["get_account", "list_users", "knowbe4_raw_get"]
        self.tools = [
            SimpleNamespace(
                name=n,
                description=f"{n} tool",
                input_schema={"type": "object", "properties": {"console": {"type": "string"}}},
            )
            for n in names
        ]

    async def list_tools(self):
        return SimpleNamespace(tools=self.tools)

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        payload = self.results.get(name, {"ok": True})
        return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(text=json.dumps(payload))])


def make_agent(config, llm, session):
    @asynccontextmanager
    async def factory():
        yield session

    return Agent(config, llm=llm, session_factory=factory)


def tool_messages(request):
    return [m for m in request["messages"] if m["role"] == "tool"]


async def test_plain_answer_without_tools(monkeypatch):
    llm = FakeLLM([reply("Halo")])
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch), llm, session)
    assert await agent.ask("hai") == "Halo"
    assert session.calls == []


async def test_single_tool_call_then_answer(monkeypatch):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "get_account", '{"console": "MAIN"}')], finish="tool_calls"),
        reply("Risk score 12.3"),
    ])
    session = FakeSession({"get_account": {"current_risk_score": 12.3}})
    agent = make_agent(make_config(monkeypatch), llm, session)

    assert await agent.ask("risk score?") == "Risk score 12.3"
    # console is normalised before the mcp call
    assert session.calls == [("get_account", {"console": "main"})]
    [msg] = tool_messages(llm.requests[1])
    assert msg["tool_call_id"] == "c1"
    assert json.loads(msg["content"]) == {"current_risk_score": 12.3}


async def test_two_tool_calls_in_one_reply(monkeypatch):
    llm = FakeLLM([
        reply(calls=[
            tool_call("a", "get_account", '{"console": "main"}'),
            tool_call("b", "list_users", '{"console": "main"}'),
        ], finish="tool_calls"),
        reply("done"),
    ])
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch), llm, session)

    assert await agent.ask("both") == "done"
    assert [c[0] for c in session.calls] == ["get_account", "list_users"]
    assert [m["tool_call_id"] for m in tool_messages(llm.requests[1])] == ["a", "b"]


async def test_bad_json_arguments_are_fed_back(monkeypatch):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "get_account", '{"console": ')], finish="tool_calls"),
        reply("retried"),
    ])
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch), llm, session)

    assert await agent.ask("x") == "retried"
    assert session.calls == []
    [msg] = tool_messages(llm.requests[1])
    body = json.loads(msg["content"])
    assert body["error"] is True and "valid JSON" in body["message"]


@pytest.mark.parametrize("console,expected", [("nope", "Unknown console"), ("off", "not configured")])
async def test_bad_console_is_rejected_before_mcp(monkeypatch, console, expected):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "get_account", json.dumps({"console": console}))], finish="tool_calls"),
        reply("ok"),
    ])
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch), llm, session)

    await agent.ask("x")
    assert session.calls == []
    body = json.loads(tool_messages(llm.requests[1])[0]["content"])
    assert expected in body["message"]
    assert "Valid consoles: main." in body["message"]


async def test_unknown_tool_is_rejected(monkeypatch):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "delete_user", '{"console": "main"}')], finish="tool_calls"),
        reply("ok"),
    ])
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch), llm, session)

    await agent.ask("x")
    assert session.calls == []
    assert "Unknown tool" in tool_messages(llm.requests[1])[0]["content"]


async def test_large_result_is_truncated(monkeypatch):
    rows = [{"id": i, "email": f"user{i}@example.com", "current_risk_score": i / 10} for i in range(2000)]
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "list_users", '{"console": "main"}')], finish="tool_calls"),
        reply("ok"),
    ])
    session = FakeSession({"list_users": rows})
    agent = make_agent(make_config(monkeypatch, llm_max_tool_chars=5000), llm, session)

    await agent.ask("x")
    content = tool_messages(llm.requests[1])[0]["content"]
    assert len(content) <= 5000
    body = json.loads(content)
    assert body["truncated"] is True
    assert body["total_records"] == 2000
    assert 0 < body["rows_shown"] == len(body["rows"]) < 2000
    assert body["rows"][0] == rows[0]


async def test_loop_stops_at_max(monkeypatch):
    looping = [reply(calls=[tool_call(f"c{i}", "get_account", '{"console": "main"}')], finish="tool_calls") for i in range(3)]
    llm = FakeLLM(looping)
    session = FakeSession()
    agent = make_agent(make_config(monkeypatch, llm_max_tool_loops=3), llm, session)

    answer = await agent.ask("x")
    assert "Batas maksimum 3" in answer
    assert len(llm.requests) == 3
    assert len(session.calls) == 3


async def test_raw_get_hidden_by_default(monkeypatch):
    llm = FakeLLM([reply("ok")])
    agent = make_agent(make_config(monkeypatch), llm, FakeSession())
    await agent.ask("x")
    names = [t["function"]["name"] for t in llm.requests[0]["tools"]]
    assert "knowbe4_raw_get" not in names and "get_account" in names


async def test_raw_get_can_be_exposed(monkeypatch):
    llm = FakeLLM([reply("ok")])
    agent = make_agent(make_config(monkeypatch, llm_expose_raw_get=True), llm, FakeSession())
    await agent.ask("x")
    assert "knowbe4_raw_get" in [t["function"]["name"] for t in llm.requests[0]["tools"]]


async def test_thinking_is_not_kept_in_history(monkeypatch):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "get_account", '{"console": "main"}')], finish="tool_calls", reasoning="secret thoughts"),
        reply("ok"),
    ])
    agent = make_agent(make_config(monkeypatch), llm, FakeSession())
    await agent.ask("x")
    assistant = [m for m in llm.requests[1]["messages"] if m["role"] == "assistant"][0]
    assert "reasoning" not in assistant
    assert "secret thoughts" not in json.dumps(llm.requests[1]["messages"])


async def test_empty_answer_gets_one_nudge(monkeypatch):
    llm = FakeLLM([
        reply(calls=[tool_call("c1", "get_account", '{"console": "main"}')], finish="tool_calls"),
        reply("", reasoning="I will now answer"),
        reply("Risk score 39.4"),
    ])
    agent = make_agent(make_config(monkeypatch), llm, FakeSession())
    assert await agent.ask("x") == "Risk score 39.4"
    assert llm.requests[2]["messages"][-1]["role"] == "user"


async def test_empty_answer_twice_gives_fallback(monkeypatch):
    llm = FakeLLM([reply(""), reply("")])
    agent = make_agent(make_config(monkeypatch), llm, FakeSession())
    assert await agent.ask("x") == "Model tidak memberikan jawaban."
    assert len(llm.requests) == 2


async def test_length_cut_is_flagged(monkeypatch):
    llm = FakeLLM([reply("partial", finish="length")])
    agent = make_agent(make_config(monkeypatch), llm, FakeSession())
    assert "terpotong" in await agent.ask("x")


async def test_llm_server_down_gives_clear_error(monkeypatch):
    # nothing listens on this port, so the real openai client fails fast
    cfg = make_config(monkeypatch, llm_base_url="http://127.0.0.1:9/v1", llm_timeout_seconds=5)
    with pytest.raises(LLMError, match="Pastikan Ollama sedang berjalan"):
        await LLMClient(cfg).chat([{"role": "user", "content": "hi"}], [])
