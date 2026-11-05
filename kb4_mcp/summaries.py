"""Small, pre-computed answers for the chat model.

Each function pulls the full collection through KnowBe4Client, does the sorting and
arithmetic in Python and returns a compact result, so a local model with a small
context never has to read thousands of raw records.
"""
from __future__ import annotations

from typing import Any

from config.settings import AppConfig

MAX_LIMIT = 50


def _limit(value: int | None, default: int = 10) -> int:
    return max(1, min(int(default if value is None else value), MAX_LIMIT))


def _date(value: Any) -> str:
    # api timestamps are iso 8601 utc; the date part is enough for filtering and display
    return str(value)[:10] if value else ""


def _name(user: dict[str, Any]) -> str:
    return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p) or user.get("email", "")


def _user_row(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user.get("id"),
        "name": _name(user),
        "email": user.get("email"),
        "department": user.get("department"),
        "job_title": user.get("job_title"),
        "status": user.get("status"),
        "current_risk_score": user.get("current_risk_score"),
        "phish_prone_percentage": user.get("phish_prone_percentage"),
    }


async def top_users_by_risk(kb: Any, console: str, limit: int = 10, status: str = "active") -> dict[str, Any]:
    users = await kb.list_users(console, status or None)
    scored = [u for u in users if isinstance(u.get("current_risk_score"), (int, float))]
    scored.sort(key=lambda u: u["current_risk_score"], reverse=True)
    top = scored[: _limit(limit)]
    return {
        "console": console,
        "status_filter": status or "all",
        "users_considered": len(users),
        "users_without_score": len(users) - len(scored),
        "metric": "current_risk_score (higher = riskier)",
        "users": [{"rank": i + 1, **_user_row(u)} for i, u in enumerate(top)],
    }


async def find_user(kb: Any, console: str, query: str, limit: int = 10) -> dict[str, Any]:
    needle = (query or "").strip().lower()
    if not needle:
        return {"console": console, "query": query, "matches": [], "note": "Empty query."}
    users = await kb.list_users(console, None)
    fields = ("first_name", "last_name", "email", "job_title", "department")

    def matches(u: dict[str, Any]) -> bool:
        haystack = " ".join(str(u.get(f) or "") for f in fields).lower() + " " + _name(u).lower()
        return all(word in haystack for word in needle.split())

    found = [u for u in users if matches(u)]
    return {
        "console": console,
        "query": query,
        "searched": len(users),
        "match_count": len(found),
        "matches": [_user_row(u) for u in found[: _limit(limit)]],
        "next_step": "Use get_user or get_user_risk_score_history with the id.",
    }


def _test_percent(value: Any) -> float | None:
    # on security tests the api returns failure events / delivered as a fraction
    # (matched 67 of 67 live tests, Nov 2026); users already use 0-100
    return round(value * 100, 2) if isinstance(value, (int, float)) else None


async def phishing_campaign_summary(kb: Any, console: str, limit: int = 10, sort: str = "latest") -> dict[str, Any]:
    tests = await kb.list_phishing_security_tests(console)
    if sort == "highest_ppp":
        ranked = sorted(
            (t for t in tests if isinstance(t.get("phish_prone_percentage"), (int, float))),
            key=lambda t: t["phish_prone_percentage"],
            reverse=True,
        )
    else:
        sort = "latest"
        ranked = sorted(tests, key=lambda t: str(t.get("started_at") or ""), reverse=True)

    rows = [
        {
            "pst_id": t.get("pst_id"),
            "campaign_id": t.get("campaign_id"),
            "name": t.get("name"),
            "started_at": _date(t.get("started_at")),
            "status": t.get("status"),
            "delivered": t.get("delivered_count"),
            "clicked": t.get("clicked_count"),
            "data_entered": t.get("data_entered_count"),
            "reported": t.get("reported_count"),
            "phish_prone_percent": _test_percent(t.get("phish_prone_percentage")),
        }
        for t in ranked[: _limit(limit)]
    ]
    return {
        "console": console,
        "sort": sort,
        "total_security_tests": len(tests),
        "metric": (
            "phish_prone_percent is already a percentage: failure events per delivered email x 100. "
            "It can exceed 100 when people fail in more than one way. It is not the risk score. "
            "Report it as given, e.g. 25.0 means 25.0%."
        ),
        "tests": rows,
    }


async def training_completion_summary(
    kb: Any,
    console: str,
    campaign_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    campaigns = await kb.list_training_campaigns(console)
    if campaign_id is not None:
        campaigns = [c for c in campaigns if c.get("campaign_id") == campaign_id]
    if start_date:
        campaigns = [c for c in campaigns if _date(c.get("start_date")) >= start_date[:10]]
    if end_date:
        campaigns = [c for c in campaigns if _date(c.get("start_date")) and _date(c.get("start_date")) <= end_date[:10]]

    campaigns.sort(key=lambda c: str(c.get("start_date") or ""), reverse=True)
    shown = campaigns[: _limit(limit)]
    rates = [c["completion_percentage"] for c in campaigns if isinstance(c.get("completion_percentage"), (int, float))]
    return {
        "console": console,
        "filters": {"campaign_id": campaign_id, "start_date": start_date, "end_date": end_date},
        "matching_campaigns": len(campaigns),
        "average_completion_percentage": round(sum(rates) / len(rates), 2) if rates else None,
        "campaigns": [
            {
                "campaign_id": c.get("campaign_id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "start_date": _date(c.get("start_date")),
                "end_date": _date(c.get("end_date")),
                "completion_percentage": c.get("completion_percentage"),
            }
            for c in shown
        ],
        "order": "newest start_date first",
    }


async def compare_consoles_risk(kb: Any, config: AppConfig) -> dict[str, Any]:
    available, unavailable = [], []
    for key, console in config.consoles.items():
        if not console.has_api_key:
            unavailable.append({"console": key, "display_name": console.display_name, "reason": "no API key configured"})
            continue
        try:
            account = await kb.get_account(key)
        except Exception as exc:
            unavailable.append({"console": key, "display_name": console.display_name, "reason": f"request failed ({type(exc).__name__})"})
            continue
        available.append({
            "console": key,
            "display_name": console.display_name,
            "current_risk_score": account.get("current_risk_score") if isinstance(account, dict) else None,
        })

    available.sort(key=lambda r: r["current_risk_score"] if isinstance(r["current_risk_score"], (int, float)) else -1, reverse=True)
    return {
        "metric": "current_risk_score (higher = riskier)",
        "consoles": available,
        "unavailable": unavailable,
    }
