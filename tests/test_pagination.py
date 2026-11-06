import httpx
import pytest

from config.settings import AppConfig, ConsoleConfig
from knowbe4.client import AsyncRateLimiter, KnowBe4APIError, KnowBe4Client


def make_client(monkeypatch, handler, **overrides):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(
        consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")},
        kb4_rate_limit_rps=1000,
        **overrides,
    )
    kb = KnowBe4Client(cfg)
    # inject a fake transport instead of the real https client
    kb._clients["main"] = httpx.AsyncClient(base_url="https://kb4.test", transport=httpx.MockTransport(handler))
    kb._limiters["main"] = AsyncRateLimiter(1000)
    return kb


def pages(rows_per_page):
    """handler serving envelope pages; cursor values are opaque strings like the real api"""
    seen = []

    def handler(request):
        cursor = request.url.params.get("cursor")
        seen.append(cursor)
        index = 0 if cursor == "0" else int(cursor.removeprefix("tok"))
        rows = [{"id": f"{index}-{i}"} for i in range(rows_per_page[index])]
        nxt = f"tok{index + 1}" if index + 1 < len(rows_per_page) else None
        return httpx.Response(200, json={"data": rows, "pagination": {"perPage": 500, "nextCursor": nxt}})

    return handler, seen


async def test_follows_next_cursor_until_null(monkeypatch):
    handler, seen = pages([3, 3, 2])
    kb = make_client(monkeypatch, handler)
    rows = await kb.list_paginated("main", "/v1/users")
    assert len(rows) == 8
    assert seen == ["0", "tok1", "tok2"]


async def test_short_pages_do_not_stop_early(monkeypatch):
    # training campaigns come back 10 per page even with per_page=500
    handler, _ = pages([10, 10, 10, 4])
    kb = make_client(monkeypatch, handler)
    assert len(await kb.list_paginated("main", "/v1/training/campaigns")) == 34


async def test_ceiling_stops_paging(monkeypatch):
    handler, seen = pages([5, 5, 5, 5])
    kb = make_client(monkeypatch, handler)
    rows = await kb.list_paginated("main", "/v1/users", max_records=7)
    assert len(rows) == 7
    assert seen == ["0", "tok1"]


async def test_plain_list_response_is_accepted(monkeypatch):
    kb = make_client(monkeypatch, lambda request: httpx.Response(200, json=[{"id": 1}, {"id": 2}]))
    assert await kb.list_paginated("main", "/v1/users") == [{"id": 1}, {"id": 2}]


async def test_repeated_cursor_does_not_loop(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"data": [{"id": len(calls)}], "pagination": {"nextCursor": "same"}})

    kb = make_client(monkeypatch, handler)
    await kb.list_paginated("main", "/v1/users")
    assert len(calls) == 2


async def test_account_risk_history_sends_no_paging_params(monkeypatch):
    params = []

    def handler(request):
        params.append(dict(request.url.params))
        return httpx.Response(200, json=[{"date": "2026-11-01", "risk_score": 39.4}])

    kb = make_client(monkeypatch, handler)
    assert await kb.get_account_risk_history("main", True) == [{"date": "2026-11-01", "risk_score": 39.4}]
    assert params == [{"full": "true"}]


async def test_429_is_retried(monkeypatch):
    responses = iter([httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200, json={"name": "x"})])
    kb = make_client(monkeypatch, lambda request: next(responses))
    assert await kb.get("main", "/v1/account") == {"name": "x"}


@pytest.mark.parametrize("retries,expected_calls", [(0, 1), (2, 3)])
async def test_max_retries_setting_is_used(monkeypatch, retries, expected_calls):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, headers={"Retry-After": "0"})

    kb = make_client(monkeypatch, handler, kb4_max_retries=retries)
    # skip tenacity's backoff sleeps so the test stays fast
    monkeypatch.setattr("knowbe4.client.wait_exponential", lambda **kw: (lambda state: 0))
    with pytest.raises(KnowBe4APIError):
        await kb.get("main", "/v1/account")
    assert len(calls) == expected_calls


async def test_500_is_not_retried(monkeypatch):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"error": "Internal Server Error"})

    kb = make_client(monkeypatch, handler)
    with pytest.raises(KnowBe4APIError) as exc:
        await kb.get("main", "/v1/account")
    assert exc.value.status_code == 500
    assert len(calls) == 1
