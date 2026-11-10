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
        kb4_rate_limit_rps=4,
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
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")}, kb4_rate_limit_rps=4)
    kb = ToolClient(cfg)
    kb._clients["main"] = httpx.AsyncClient(base_url="https://kb4.test", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    kb._limiters["main"] = AsyncRateLimiter(1000)
    with pytest.raises(ToolError, match="API key was rejected"):
        await kb.get("main", "/v1/account")
    # product checks too: an unknown console or a missing key reads as a sentence, not the sdk's masked error
    with pytest.raises(ToolError, match="Unknown console"):
        kb.has_product("nope", "ksat")
    with pytest.raises(ToolError, match="not configured"):
        await kb.graph("main", "ksat", "query { account { id } }")
    with pytest.raises(ToolError, match="read-only"):
        await kb.graph("main", "ksat", "mutation { x }")


def test_agent_passes_tool_error_text_to_model():
    from agent.agent import Agent

    result = SimpleNamespace(is_error=True, structured_content=None, content=[SimpleNamespace(text="KnowBe4 daily API limit reached")])
    assert json.loads(Agent._mcp_result_text(result)) == {"error": True, "message": "KnowBe4 daily API limit reached"}


@pytest.mark.parametrize("path", [
    "/v1/../v2/secret",
    "/v1/%2e%2e/admin",
    "/v1/users/../../v2",
    "/v1//evil.example/x",
    "/v1/users/..",
    r"/v1\..\v2",
    "/v2/users",
    "https://evil.example/v1/users",
])
async def test_paths_outside_v1_are_refused(path):
    kb = KnowBe4Client(AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")}))
    with pytest.raises(ValueError, match="/v1/"):
        await kb.get("main", path)


@pytest.mark.parametrize("path", ["/v1/users", "v1/users", "/v1/users/12/risk_score_history", "/v1/users/"])
async def test_normal_v1_paths_still_reach_knowbe4(monkeypatch, path):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler)
    await kb.get("main", path)
    assert calls and calls[0][0].startswith("/v1/users")
    await kb.aclose()


def test_two_processes_counting_at_once_lose_nothing(tmp_path):
    path = tmp_path / "usage.json"
    a, b = UsageTracker(path), UsageTracker(path)
    a.record("main", now=1000.0)
    b.record("main", now=1001.0)
    a.record("main", now=1002.0)
    assert UsageTracker(path).used("main", now=1003.0) == 3
    assert not (tmp_path / "usage.tmp").exists()


def test_corrupt_counter_file_starts_fresh_and_is_repaired(tmp_path):
    path = tmp_path / "usage.json"
    path.write_text("{broken", encoding="utf-8")
    tracker = UsageTracker(path)
    assert tracker.used("main", now=1000.0) == 0
    tracker.record("main", now=1000.0)
    assert json.loads(path.read_text(encoding="utf-8")) == {"main": [1000.0]}



async def test_refresh_drops_the_cached_copy_once_a_minute(monkeypatch):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler, kb4_cache_seconds=600)
    clock = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])
    await kb.get("main", "/v1/account")
    assert kb.clear_cache("main") == {"console": "main", "refreshed": True, "cached_answers_dropped": 1}
    await kb.get("main", "/v1/account")
    assert len(calls) == 2
    # a second "refresh" within the minute keeps the copy that is seconds old
    clock[0] += 20
    assert kb.clear_cache("MAIN") == {"console": "main", "refreshed": False, "data_age_at_most_seconds": 20}
    await kb.get("main", "/v1/account")
    assert len(calls) == 2
    clock[0] += 41
    assert kb.clear_cache("main")["refreshed"] is True
    await kb.get("main", "/v1/account")
    assert len(calls) == 3


async def test_refresh_leaves_other_consoles_cached(monkeypatch):
    handler, calls = counting()
    kb = make_client(monkeypatch, handler)
    kb._cache[("other", "/v1/account", ())] = (time.monotonic() + 600, {"name": "other"})
    await kb.get("main", "/v1/account")
    kb.clear_cache("main")
    assert ("other", "/v1/account", ()) in kb._cache



def test_raw_account_and_user_carry_the_knowbe4_level():
    # the model called 38.01 "Medium" from a bare score
    from kb4_mcp.server_impl import _with_level

    assert _with_level({"name": "a", "current_risk_score": 38.01})["current_risk_level"] == "Low"
    assert _with_level({"current_risk_score": 54.2})["current_risk_level"] == "Critical"
    assert _with_level({"name": "no score"}) == {"name": "no score"}
