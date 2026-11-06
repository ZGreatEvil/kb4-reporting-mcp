import json
import time
from types import SimpleNamespace

import httpx
import pytest

from config.settings import AppConfig, ConsoleConfig
from knowbe4 import client as client_module
from knowbe4.client import (
    DAY_SECONDS,
    AsyncRateLimiter,
    KnowBe4APIError,
    KnowBe4Client,
    KnowBe4DailyLimitError,
    UsageTracker,
)


def make_client(monkeypatch, handler, **overrides):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(
        consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")},
        kb4_rate_limit_rps=1000,
        **overrides,
    )
    kb = KnowBe4Client(cfg)
    kb._clients["main"] = httpx.AsyncClient(base_url="https://kb4.test", transport=httpx.MockTransport(handler))
    kb._limiters["main"] = AsyncRateLimiter(1000)
    return kb


def counting(body=None, status=200):
    calls = []

    def handler(request):
        calls.append((request.url.path, dict(request.url.params)))
        return httpx.Response(status, json=body if body is not None else {"ok": len(calls)})

    return handler, calls


async def test_repeat_request_served_from_cache(monkeypatch):
    handler, calls = counting({"name": "acct"})
    kb = make_client(monkeypatch, handler)
    assert await kb.get("main", "/v1/account") == await kb.get("main", "/v1/account")
    assert len(calls) == 1
    assert kb.usage.used("main") == 1


async def test_param_order_does_not_matter(monkeypatch):
    handler, calls = counting([])
    kb = make_client(monkeypatch, handler)
    await kb.get("main", "/v1/users", {"status": "active", "per_page": 5})
    await kb.get("main", "/v1/users", {"per_page": 5, "status": "active"})
    assert len(calls) == 1


async def test_different_params_are_separate(monkeypatch):
    handler, calls = counting([])
    kb = make_client(monkeypatch, handler)
    await kb.get("main", "/v1/users", {"status": "active"})
    await kb.get("main", "/v1/users", {"status": "archived"})
    assert len(calls) == 2


async def test_cache_expires(monkeypatch):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler, kb4_cache_seconds=60)
    clock = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])
    await kb.get("main", "/v1/account")
    clock[0] += 59
    await kb.get("main", "/v1/account")
    assert len(calls) == 1
    clock[0] += 2
    await kb.get("main", "/v1/account")
    assert len(calls) == 2


async def test_cache_can_be_turned_off(monkeypatch):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler, kb4_cache_seconds=0)
    await kb.get("main", "/v1/account")
    await kb.get("main", "/v1/account")
    assert len(calls) == 2


async def test_errors_are_not_cached(monkeypatch):
    responses = iter([httpx.Response(404, json={"error": "nf"}), httpx.Response(200, json={"id": 1})])
    kb = make_client(monkeypatch, lambda request: next(responses))
    with pytest.raises(KnowBe4APIError):
        await kb.get("main", "/v1/users/1")
    assert await kb.get("main", "/v1/users/1") == {"id": 1}


async def test_callers_get_copies(monkeypatch):
    handler, _ = counting([{"id": 2}, {"id": 1}])
    kb = make_client(monkeypatch, handler)
    first = await kb.get("main", "/v1/users")
    first.sort(key=lambda u: u["id"])
    first[0]["id"] = 99
    assert await kb.get("main", "/v1/users") == [{"id": 2}, {"id": 1}]


async def test_paginated_list_reuses_cached_pages(monkeypatch):
    calls = []

    def handler(request):
        cursor = request.url.params.get("cursor")
        calls.append(cursor)
        nxt = "tok1" if cursor == "0" else None
        return httpx.Response(200, json={"data": [{"id": cursor}], "pagination": {"nextCursor": nxt}})

    kb = make_client(monkeypatch, handler)
    assert len(await kb.list_paginated("main", "/v1/training/campaigns")) == 2
    assert len(await kb.list_paginated("main", "/v1/training/campaigns")) == 2
    assert calls == ["0", "tok1"]


async def test_retries_count_against_daily_usage(monkeypatch):
    responses = iter([httpx.Response(503, headers={"Retry-After": "0"}), httpx.Response(200, json={"ok": 1})])
    kb = make_client(monkeypatch, lambda request: next(responses))
    monkeypatch.setattr(client_module, "wait_exponential", lambda **kw: (lambda state: 0))
    await kb.get("main", "/v1/account")
    assert kb.usage.used("main") == 2


async def test_daily_limit_blocks_before_calling(monkeypatch):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler, kb4_daily_limit=2)
    await kb.get("main", "/v1/a")
    await kb.get("main", "/v1/b")
    with pytest.raises(KnowBe4DailyLimitError) as exc:
        await kb.get("main", "/v1/c")
    assert (exc.value.used, exc.value.limit) == (2, 2)
    assert len(calls) == 2
    # cached answers still work at the limit
    assert await kb.get("main", "/v1/a") == {"ok": 1}


async def test_automatic_limit_is_2000_plus_seats(monkeypatch):
    monkeypatch.delenv("KB4_DAILY_LIMIT")
    handler, calls = counting({"name": "acct", "number_of_seats": 10})
    kb = make_client(monkeypatch, handler)
    assert await kb.daily_limit("main") == 2010
    # the seat lookup is cached and reused by later account requests
    await kb.get("main", "/v1/account")
    assert len(calls) == 1
    assert kb.usage_summary("main") == {"requests_last_24h": 1, "daily_limit": 2010}


async def test_automatic_limit_falls_back_to_2000(monkeypatch):
    monkeypatch.delenv("KB4_DAILY_LIMIT")
    kb = make_client(monkeypatch, lambda request: httpx.Response(500, json={}))
    assert await kb.daily_limit("main") == 2000


def test_usage_survives_restart_and_forgets_after_24h(tmp_path):
    path = tmp_path / "u.json"
    now = time.time()
    first = UsageTracker(path)
    first.record("main", now - DAY_SECONDS - 5)
    first.record("main", now - 10)
    first.record("other", now - 10)
    second = UsageTracker(path)
    assert second.used("main", now) == 1
    assert second.used("other", now) == 1


def test_broken_usage_file_starts_fresh(tmp_path):
    path = tmp_path / "u.json"
    path.write_text("not json", encoding="utf-8")
    assert UsageTracker(path).used("main") == 0


# server: KnowBe4 failures reach the model as readable ToolErrors


def test_tool_messages():
    from kb4_mcp.server_impl import tool_message

    assert "daily API limit reached" in tool_message(KnowBe4DailyLimitError(5, 5))
    assert "API key was rejected" in tool_message(KnowBe4APIError(401, "x"))
    assert "not found" in tool_message(KnowBe4APIError(404, "x"))
    assert "could not be reached" in tool_message(httpx.ConnectError("x"))
    # response bodies are never passed on
    assert "secret-body" not in tool_message(KnowBe4APIError(500, "secret-body"))


async def test_tool_client_raises_tool_error(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError
    from kb4_mcp.server_impl import ToolClient

    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")}, kb4_rate_limit_rps=1000)
    kb = ToolClient(cfg)
    kb._clients["main"] = httpx.AsyncClient(base_url="https://kb4.test", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    kb._limiters["main"] = AsyncRateLimiter(1000)
    with pytest.raises(ToolError, match="API key was rejected"):
        await kb.get("main", "/v1/account")


def test_agent_passes_tool_error_text_to_model():
    from agent.agent import Agent

    result = SimpleNamespace(is_error=True, structured_content=None, content=[SimpleNamespace(text="KnowBe4 daily API limit reached")])
    assert json.loads(Agent._mcp_result_text(result)) == {"error": True, "message": "KnowBe4 daily API limit reached"}
