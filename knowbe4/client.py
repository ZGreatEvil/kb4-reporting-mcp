from __future__ import annotations

import asyncio
import copy
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.settings import AppConfig, ConsoleConfig


class KnowBe4APIError(RuntimeError):
    def __init__(self, status_code: int, message: str, request_id: str | None = None):
        self.status_code = status_code
        self.request_id = request_id
        suffix = f"; request_id={request_id}" if request_id else ""
        super().__init__(f"KnowBe4 API error {status_code}: {message}{suffix}")


class KnowBe4RetryableError(KnowBe4APIError):
    """429 or a transient 502/503/504; retried by _request"""


class KnowBe4DailyLimitError(KnowBe4APIError):
    """refused locally before calling KnowBe4, so the real daily limit is never hit"""

    def __init__(self, used: int, limit: int):
        self.used = used
        self.limit = limit
        super().__init__(429, f"daily request limit reached ({used} of {limit} in the last 24 hours)")


STATUS_HINTS = {
    401: "the API key was rejected (wrong, expired, or not a Reporting API key)",
    403: "the API key is not allowed to read this data",
    404: "not found; check the id",
    429: "KnowBe4 rate limit hit; try again in a few minutes",
}


def readable_error(exc: Exception) -> str:
    """one plain sentence for a failed request; never the response body, which can echo data"""
    if isinstance(exc, KnowBe4DailyLimitError):
        return (f"KnowBe4 daily API limit reached for this console ({exc.used} of {exc.limit} requests "
                "in the last 24 hours). Tell the user to try again later.")
    if isinstance(exc, KnowBe4APIError):
        return f"KnowBe4 API error {exc.status_code}: {STATUS_HINTS.get(exc.status_code, 'the request failed')}."
    if isinstance(exc, httpx.HTTPError):
        return "KnowBe4 could not be reached (network error or timeout). Try again later."
    return str(exc)


RETRYABLE_STATUS = {429, 502, 503, 504}
MAX_RETRY_AFTER_SECONDS = 60.0

# KnowBe4 docs: 2,000 requests per day plus the number of licensed users
BASE_DAILY_REQUESTS = 2000
DAY_SECONDS = 24 * 3600
WARN_AT = 0.8
MAX_CACHE_ENTRIES = 1000


class UsageTracker:
    """real requests per console over a rolling 24 h, saved to a small json file so restarts don't reset it"""

    def __init__(self, path: Path):
        self.path = path
        self._stamps: Dict[str, list[float]] = self._load()

    def _load(self) -> Dict[str, list[float]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: [float(t) for t in v] for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError, AttributeError, TypeError):
            return {}

    def _recent(self, console: str, now: float) -> list[float]:
        stamps = [t for t in self._stamps.get(console, []) if t > now - DAY_SECONDS]
        self._stamps[console] = stamps
        return stamps

    def used(self, console: str, now: float | None = None) -> int:
        return len(self._recent(console, time.time() if now is None else now))

    def record(self, console: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        self._recent(console, now).append(now)
        # another process (the mcp server and test_knowbe4.py, say) may have counted too: merge, don't overwrite
        for key, stamps in self._load().items():
            self._stamps[key] = sorted(set(self._stamps.get(key, [])) | {t for t in stamps if t > now - DAY_SECONDS})
        try:
            # a crash mid-write must not leave a broken file, which would reset the count
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._stamps), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            # counting still works in memory
            pass


class AsyncRateLimiter:
    def __init__(self, rps: float):
        self.interval = 1.0 / max(rps, 0.1)
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self.interval:
                await asyncio.sleep(self.interval - delta)
            self._last = time.monotonic()


class KnowBe4Client:
    def __init__(self, config: AppConfig):
        self.config = config
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._limiters: Dict[str, AsyncRateLimiter] = {}
        self._cache: Dict[tuple, tuple[float, Any]] = {}
        self.usage = UsageTracker(config.kb4_usage_file)
        self._daily_limits: Dict[str, int] = {}
        self._warned: set[str] = set()

    def _console(self, console: str) -> ConsoleConfig:
        key = console.lower().strip()
        if key not in self.config.consoles:
            raise ValueError(f"Unknown console '{console}'. Available: {', '.join(self.config.consoles)}")
        return self.config.consoles[key]

    def _client(self, console: str) -> httpx.AsyncClient:
        key = console.lower().strip()
        if key not in self._clients:
            cc = self._console(key)
            self._clients[key] = httpx.AsyncClient(
                base_url=cc.base_url,
                timeout=self.config.kb4_timeout_seconds,
                headers={
                    "Authorization": f"Bearer {cc.api_key}",
                    "Accept": "application/json",
                    "User-Agent": "knowbe4-reporting-mcp/1.1",
                },
                follow_redirects=True,
            )
            self._limiters[key] = AsyncRateLimiter(self.config.kb4_rate_limit_rps)
        return self._clients[key]

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
        self._limiters.clear()

    async def _request(self, console: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        # KB4_MAX_RETRIES counts retries after the first try
        retrying = AsyncRetrying(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, KnowBe4RetryableError)),
            stop=stop_after_attempt(max(0, self.config.kb4_max_retries) + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._request_once(console, path, params)

    async def _request_once(self, console: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        client = self._client(console)
        key = console.lower().strip()
        limiter = self._limiters[key]
        await limiter.wait()
        # every attempt counts against KnowBe4's daily limit, retries included
        self.usage.record(key)
        response = await client.get(path, params=params)
        request_id = response.headers.get("X-Request-Id")
        if response.status_code in RETRYABLE_STATUS:
            # honour Retry-After (seconds) before tenacity's own backoff
            try:
                delay = float(response.headers.get("Retry-After", "0"))
            except ValueError:
                delay = 0.0
            if delay > 0:
                await asyncio.sleep(min(delay, MAX_RETRY_AFTER_SECONDS))
            raise KnowBe4RetryableError(response.status_code, response.text[:1000], request_id)
        if response.status_code >= 400:
            safe_body = response.text[:1000]
            raise KnowBe4APIError(response.status_code, safe_body, request_id)
        return response.json()

    async def daily_limit(self, console: str) -> int:
        key = console.lower().strip()
        if self.config.kb4_daily_limit is not None:
            return self.config.kb4_daily_limit
        if key not in self._daily_limits:
            # provisional value while the account (and its seat count) is fetched through the normal path
            self._daily_limits[key] = BASE_DAILY_REQUESTS
            try:
                account = await self.get(key, "/v1/account")
                seats = account.get("number_of_seats") if isinstance(account, dict) else None
                if isinstance(seats, int) and seats > 0:
                    self._daily_limits[key] = BASE_DAILY_REQUESTS + seats
            except (KnowBe4APIError, httpx.HTTPError):
                pass
        return self._daily_limits[key]

    async def _check_daily_limit(self, console: str) -> None:
        key = console.lower().strip()
        limit = await self.daily_limit(key)
        used = self.usage.used(key)
        if used >= limit:
            raise KnowBe4DailyLimitError(used, limit)
        if used >= WARN_AT * limit and key not in self._warned:
            self._warned.add(key)
            print(f"[KB4 WARNING] console {key}: {used} of {limit} daily requests used", flush=True)

    def usage_summary(self, console: str) -> Dict[str, Any]:
        key = console.lower().strip()
        limit = self.config.kb4_daily_limit or self._daily_limits.get(key)
        return {"requests_last_24h": self.usage.used(key), "daily_limit": limit}

    def _cache_key(self, console: str, path: str, params: Optional[Dict[str, Any]]) -> tuple:
        items = tuple(sorted((str(k), str(v)) for k, v in (params or {}).items()))
        return (console.lower().strip(), path, items)

    async def get(self, console: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        path = "/" + path.lstrip("/")
        # "/v1/../v2" would pass a prefix check and be normalised to /v2 by httpx
        segments = unquote(path.split("?", 1)[0]).split("/")[1:]
        if not path.startswith("/v1/") or "\\" in unquote(path) or any(s in ("", ".", "..") for s in segments[:-1]) or segments[-1] in (".", ".."):
            raise ValueError("Only KnowBe4 Reporting API /v1/* paths are allowed")

        ttl = self.config.kb4_cache_seconds
        key = self._cache_key(console, path, params)
        now = time.monotonic()
        hit = self._cache.get(key)
        if ttl > 0 and hit and hit[0] > now:
            # copies, so a caller sorting or editing results can't change the cache
            return copy.deepcopy(hit[1])

        await self._check_daily_limit(console)
        data = await self._request(console, path, params)
        if ttl > 0:
            if len(self._cache) >= MAX_CACHE_ENTRIES:
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
                while len(self._cache) >= MAX_CACHE_ENTRIES:
                    self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (now + ttl, data)
        return copy.deepcopy(data)

    async def list_paginated(
        self,
        console: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_records: Optional[int] = None,
    ) -> list[Any]:
        """Retrieve a whole collection using the 2026 cursor pagination convention.

        cursor=0 starts it; responses are {"data": [...], "pagination": {"perPage", "nextCursor"}},
        and nextCursor (an opaque string, null on the last page) is sent back as cursor.
        Pages can be shorter than per_page before the end, so only nextCursor decides when to stop.
        A safety ceiling prevents accidentally loading an unbounded dataset into the LLM context.
        """
        base_params = dict(params or {})
        per_page = self.config.kb4_per_page
        ceiling = min(max_records or self.config.kb4_max_records, self.config.kb4_max_records)
        results: list[Any] = []
        cursor: str = "0"

        while len(results) < ceiling:
            query = {**base_params, "per_page": per_page, "cursor": cursor}
            data = await self.get(console, path, query)
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                rows = data["data"]
                next_cursor = (data.get("pagination") or {}).get("nextCursor")
            elif isinstance(data, list):
                # an endpoint that ignores cursor returns everything at once
                rows, next_cursor = data, None
            else:
                return [data]

            results.extend(rows[: ceiling - len(results)])
            if not rows or not next_cursor or str(next_cursor) == cursor:
                break
            cursor = str(next_cursor)

        return results

    async def get_account(self, console: str) -> Any:
        return await self.get(console, "/v1/account")

    async def get_account_risk_history(self, console: str, full: bool = False) -> list[Any]:
        # this endpoint returns a plain list and answers 500 to per_page/cursor
        return await self.get(console, "/v1/account/risk_score_history", {"full": str(full).lower()})

    async def list_users(self, console: str, status: str | None = None, group_id: int | None = None, max_records: int | None = None) -> list[Any]:
        params = {}
        if status:
            params["status"] = status
        if group_id is not None:
            params["group_id"] = group_id
        return await self.list_paginated(console, "/v1/users", params, max_records)

    async def get_user(self, console: str, user_id: int) -> Any:
        return await self.get(console, f"/v1/users/{user_id}")

    async def get_user_risk_history(self, console: str, user_id: int, full: bool = False) -> list[Any]:
        return await self.get(console, f"/v1/users/{user_id}/risk_score_history", {"full": str(full).lower()})

    async def list_groups(self, console: str, status: str | None = None, max_records: int | None = None) -> list[Any]:
        params = {"status": status} if status else {}
        return await self.list_paginated(console, "/v1/groups", params, max_records)

    async def get_group(self, console: str, group_id: int) -> Any:
        return await self.get(console, f"/v1/groups/{group_id}")

    async def list_group_members(self, console: str, group_id: int, max_records: int | None = None) -> list[Any]:
        return await self.list_paginated(console, f"/v1/groups/{group_id}/members", {}, max_records)

    async def list_phishing_campaigns(self, console: str, campaign_type: str | None = None, max_records: int | None = None) -> list[Any]:
        params = {"campaign_type": campaign_type} if campaign_type else {}
        return await self.list_paginated(console, "/v1/phishing/campaigns", params, max_records)

    async def get_phishing_campaign(self, console: str, campaign_id: int, campaign_type: str | None = None) -> Any:
        params = {"campaign_type": campaign_type} if campaign_type else None
        return await self.get(console, f"/v1/phishing/campaigns/{campaign_id}", params)

    async def list_phishing_security_tests(self, console: str, campaign_type: str | None = None, max_records: int | None = None) -> list[Any]:
        params = {"campaign_type": campaign_type} if campaign_type else {}
        return await self.list_paginated(console, "/v1/phishing/security_tests", params, max_records)

    async def get_phishing_security_test(self, console: str, pst_id: int, campaign_type: str | None = None) -> Any:
        params = {"campaign_type": campaign_type} if campaign_type else None
        return await self.get(console, f"/v1/phishing/security_tests/{pst_id}", params)

    async def list_pst_recipients(self, console: str, pst_id: int, campaign_type: str | None = None, max_records: int | None = None) -> list[Any]:
        params = {"campaign_type": campaign_type} if campaign_type else {}
        return await self.list_paginated(console, f"/v1/phishing/security_tests/{pst_id}/recipients", params, max_records)

    async def get_pst_recipient(self, console: str, pst_id: int, recipient_id: int, campaign_type: str | None = None) -> Any:
        params = {"campaign_type": campaign_type} if campaign_type else None
        return await self.get(console, f"/v1/phishing/security_tests/{pst_id}/recipients/{recipient_id}", params)

    async def list_training_campaigns(self, console: str, exclude_percentages: bool = False, max_records: int | None = None) -> list[Any]:
        params = {"exclude_percentages": str(exclude_percentages).lower()}
        return await self.list_paginated(console, "/v1/training/campaigns", params, max_records)

    async def get_training_campaign(self, console: str, campaign_id: int) -> Any:
        return await self.get(console, f"/v1/training/campaigns/{campaign_id}")

    async def list_training_enrollments(self, console: str, store_purchase_id: int | None = None, campaign_id: int | None = None, user_id: int | None = None, exclude_archived_users: bool = False, include_campaign_id: bool = False, include_store_purchase_id: bool = False, include_employee_number: bool = False, max_records: int | None = None) -> list[Any]:
        params: Dict[str, Any] = {
            "exclude_archived_users": str(exclude_archived_users).lower(),
            "include_campaign_id": str(include_campaign_id).lower(),
            "include_store_purchase_id": str(include_store_purchase_id).lower(),
            "include_employee_number": str(include_employee_number).lower(),
        }
        if store_purchase_id is not None:
            params["store_purchase_id"] = store_purchase_id
        if campaign_id is not None:
            params["campaign_id"] = campaign_id
        if user_id is not None:
            params["user_id"] = user_id
        return await self.list_paginated(console, "/v1/training/enrollments", params, max_records)

    async def get_training_enrollment(self, console: str, enrollment_id: int) -> Any:
        return await self.get(console, f"/v1/training/enrollments/{enrollment_id}")

    async def list_store_purchases(self, console: str, max_records: int | None = None) -> list[Any]:
        return await self.list_paginated(console, "/v1/training/store_purchases", {}, max_records)

    async def get_store_purchase(self, console: str, store_purchase_id: int) -> Any:
        return await self.get(console, f"/v1/training/store_purchases/{store_purchase_id}")

    async def list_policies(self, console: str, max_records: int | None = None) -> list[Any]:
        return await self.list_paginated(console, "/v1/training/policies", {}, max_records)

    async def get_policy(self, console: str, policy_id: int) -> Any:
        return await self.get(console, f"/v1/training/policies/{policy_id}")

    async def health_check(self, console: str) -> dict[str, Any]:
        account = await self.get_account(console)
        return {
            "console": console,
            "status": "ok",
            "account_name": account.get("name") if isinstance(account, dict) else None,
            "subscription_level": account.get("subscription_level") if isinstance(account, dict) else None,
            "current_risk_score": account.get("current_risk_score") if isinstance(account, dict) else None,
        }
