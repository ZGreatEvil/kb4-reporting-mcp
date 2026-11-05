from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config.settings import AppConfig, ConsoleConfig


class KnowBe4APIError(RuntimeError):
    def __init__(self, status_code: int, message: str, request_id: str | None = None):
        self.status_code = status_code
        self.request_id = request_id
        suffix = f"; request_id={request_id}" if request_id else ""
        super().__init__(f"KnowBe4 API error {status_code}: {message}{suffix}")


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
                    "User-Agent": "knowbe4-gemini-mcp/1.0",
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

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        reraise=True,
    )
    async def _request(self, console: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        client = self._client(console)
        limiter = self._limiters[console.lower().strip()]
        await limiter.wait()
        response = await client.get(path, params=params)
        request_id = response.headers.get("X-Request-Id")
        if response.status_code >= 400:
            safe_body = response.text[:1000]
            raise KnowBe4APIError(response.status_code, safe_body, request_id)
        return response.json()

    async def get(self, console: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        path = "/" + path.lstrip("/")
        if not path.startswith("/v1/"):
            raise ValueError("Only KnowBe4 Reporting API /v1/* paths are allowed")
        return await self._request(console, path, params)

    async def list_paginated(
        self,
        console: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_records: Optional[int] = None,
    ) -> list[Any]:
        """Retrieve a whole collection using the 2026 cursor pagination convention.

        KnowBe4 documents per_page (max 500) and cursor=0 as the starting point.
        A safety ceiling prevents accidentally loading an unbounded dataset into the LLM context.
        """
        base_params = dict(params or {})
        per_page = self.config.kb4_per_page
        ceiling = min(max_records or self.config.kb4_max_records, self.config.kb4_max_records)
        results: list[Any] = []
        cursor = 0

        while len(results) < ceiling:
            query = {**base_params, "per_page": per_page, "cursor": cursor}
            data = await self.get(console, path, query)
            if not isinstance(data, list):
                return [data]
            if not data:
                break
            remaining = ceiling - len(results)
            results.extend(data[:remaining])
            if len(data) < per_page:
                break
            cursor += per_page

        return results

    async def get_account(self, console: str) -> Any:
        return await self.get(console, "/v1/account")

    async def get_account_risk_history(self, console: str, full: bool = False) -> list[Any]:
        return await self.list_paginated(console, "/v1/account/risk_score_history", {"full": str(full).lower()}, 2000)

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
