"""Small, pre-computed answers for the chat model.

Each function pulls the full collection through KnowBe4Client, does the sorting and
arithmetic in Python and returns a compact result, so a local model with a small
context never has to read thousands of raw records.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from config.settings import AppConfig

MAX_LIMIT = 50
PAGE_SIZE = 20

# KnowBe4 SmartRisk risk levels (score 0-100, shown 10-90, higher = riskier).
# from KnowBe4's "SmartRisk Engine and Risk Score Guide" as quoted in search results, Nov 2026;
# the page itself blocks automated reading, so confirm against it before relying on the cut-offs
RISK_LEVELS = [(40, "Low"), (47, "Medium"), (53, "High"), (100, "Critical")]
RISK_SCALE_NOTE = "KnowBe4 risk levels: Low 10-40, Medium 41-47, High 48-53, Critical 54-90 (higher = riskier)."

# KnowBe4 2026 Phishing by Industry Benchmarking Report (blog, 7 Jul 2026): global average phish-prone %
PPP_BENCHMARKS = [("before training", 33.2), ("after 90 days of training", 20.1), ("after 12 months of training", 4.2)]
# weekly snapshots: a point counts for "N days ago" only if it is at most this many days older than that date
SNAPSHOT_SLACK_DAYS = 21


def risk_level(score: Any) -> str | None:
    if not isinstance(score, (int, float)):
        return None
    # the published bands are whole numbers (40, then 41); 40.24 would otherwise land between them
    whole = math.floor(score + 0.5)
    for upper, name in RISK_LEVELS:
        if whole <= upper:
            return name
    return "Critical"


def _r(value: Any) -> Any:
    # long floats like 52.0618896484375 are unreadable; two decimals is plenty
    return round(value, 2) if isinstance(value, float) else value


def _limit(value: int | None, default: int = 10) -> int:
    return max(1, min(int(default if value is None else value), MAX_LIMIT))


def _date(value: Any) -> str:
    # api timestamps are iso 8601 utc; the date part is enough for filtering and display
    return str(value)[:10] if value else ""


def _within(value: Any, start: str | None, end: str | None) -> bool:
    """is this api date inside the asked period (YYYY-MM-DD bounds, both inclusive)? undated items only pass without a period"""
    day = _date(value)
    if not day:
        return not (start or end)
    return (not start or day >= start[:10]) and (not end or day <= end[:10])


def _bad_period(start: str | None, end: str | None) -> str | None:
    """dates are compared as text, so "Jan 2026" would filter silently wrong: refuse anything but YYYY-MM-DD"""
    for name, value in (("start_date", start), ("end_date", end)):
        if value is None or value == "":
            continue
        problem = f"{name} must be a date written as YYYY-MM-DD, for example 2026-01-31 (got {value!r})."
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            return problem
        try:
            date.fromisoformat(str(value))  # also refuses 2026-02-30
        except ValueError:
            return problem
    if start and end and str(start) > str(end):
        return f"start_date {start} is after end_date {end}."
    return None


def _period_label(start: str | None, end: str | None) -> str | None:
    if not (start or end):
        return None
    return f"{start[:10] if start else 'the start of the data'} to {end[:10] if end else 'today'}"


def _name(user: dict[str, Any]) -> str:
    return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p) or user.get("email", "")


def _user_row(user: dict[str, Any]) -> dict[str, Any]:
    score = user.get("current_risk_score")
    return {
        "id": user.get("id"),
        "name": _name(user),
        "email": user.get("email"),
        "department": user.get("department"),
        "job_title": user.get("job_title"),
        "status": user.get("status"),
        "risk_score": _r(score),
        "risk_level": risk_level(score),
        # on users this is already 0-100 (failures per phishing email received, x100)
        "phish_prone_percent": _r(user.get("phish_prone_percentage")),
    }


def ppp_vs_benchmark(value: Any) -> dict[str, Any] | None:
    """compares a phish-prone % with KnowBe4's global benchmark in code; small models get "above/below" wrong"""
    if not isinstance(value, (int, float)):
        return None
    above = [f"{name} ({b}%)" for name, b in PPP_BENCHMARKS if value > b]
    below = [f"{name} ({b}%)" for name, b in PPP_BENCHMARKS if value < b]
    if not below:
        text = "higher than every KnowBe4 global benchmark, including " + above[0]
    elif not above:
        text = "lower than every KnowBe4 global benchmark, including " + below[-1]
    else:
        text = f"higher than the figure {above[0]} but lower than the figure {below[-1]}"
    return {"value": _r(value), "comparison": text, "source": "KnowBe4 2026 global phishing benchmark"}


def _history_stats(history: list[dict[str, Any]], today: date | None = None, current: Any = None) -> dict[str, Any]:
    """trend facts from a risk score history, so the model never has to read the raw points.

    history points are weekly snapshots; the live score (current) can already differ from the newest one,
    so changes are measured from the live score when it is known
    """
    points = sorted(
        ((_date(h.get("date")), h.get("risk_score")) for h in history if isinstance(h.get("risk_score"), (int, float))),
        key=lambda p: p[0],
    )
    if not points:
        return {"points_available": 0}
    # measured from the real date, so a history that stopped months ago is not described as recent
    today = today or date.today()
    latest_date, newest_point = points[-1]
    latest = current if isinstance(current, (int, float)) else newest_point

    def at_or_before(days: int) -> tuple[str, float] | None:
        target = today - timedelta(days=days)
        older = [p for p in points if p[0] <= target.isoformat()]
        if not older or date.fromisoformat(older[-1][0]) < target - timedelta(days=SNAPSHOT_SLACK_DAYS):
            return None
        return older[-1]

    def change(days: int) -> dict[str, Any] | None:
        then = at_or_before(days)
        if not then:
            return None
        return {"from_date": then[0], "from_score": _r(then[1]), "to_score_now": _r(latest), "change": _r(latest - then[1])}

    recent_cutoff = (today - timedelta(days=90)).isoformat()
    recent = [s for d, s in points if d >= recent_cutoff]
    return {
        "note": "History points are weekly snapshots. Changes are measured from the current score.",
        "current_score": _r(latest),
        "current_level": risk_level(latest),
        "change_vs_30_days_ago": change(30),
        "change_vs_90_days_ago": change(90),
        "weekly_snapshots_last_3_months": {
            "average": _r(sum(recent) / len(recent)),
            "lowest": _r(min(recent)),
            "highest": _r(max(recent)),
        } if recent else None,
        "newest_weekly_snapshot": {"date": latest_date, "score": _r(newest_point)},
        "data_gap": (
            f"No weekly snapshots since {latest_date}; changes over time cannot be measured for recent months."
            if date.fromisoformat(latest_date) < today - timedelta(days=30) else None
        ),
        "covers": f"{points[0][0]} to {latest_date}",
        "points_available": len(points),
    }


def _period_stats(history: list[dict[str, Any]], start: str | None, end: str | None, current: Any) -> dict[str, Any] | None:
    """the weekly snapshots inside the asked period, and the change from the first one to now"""
    if not (start or end):
        return None
    points = sorted(
        (_date(h.get("date")), h.get("risk_score")) for h in history
        if isinstance(h.get("risk_score"), (int, float)) and _within(h.get("date"), start, end)
    )
    label = _period_label(start, end)
    if not points:
        return {"period": label, "snapshots": 0, "note": f"No weekly snapshots from {label}."}
    scores = [s for _, s in points]
    # a period running to today ends at the live score; one that ended earlier, at its last snapshot
    live = isinstance(current, (int, float)) and not end
    now = current if live else scores[-1]
    return {
        "period": label,
        "snapshots": len(points),
        "first_snapshot": {"date": points[0][0], "score": _r(points[0][1])},
        "last": {"date": "now" if live else points[-1][0], "score": _r(now)},
        "change": _r(now - points[0][1]),
        "average": _r(sum(scores) / len(scores)),
        "lowest": _r(min(scores)),
        "highest": _r(max(scores)),
    }


def _period_sentence(p: dict[str, Any] | None) -> str:
    if not p:
        return ""
    if not p.get("snapshots"):
        return " " + p["note"]
    return (f" From {p['period']}: {p['snapshots']} weekly snapshots, average {p['average']} (lowest {p['lowest']}, "
            f"highest {p['highest']}); from {p['first_snapshot']['score']} on {p['first_snapshot']['date']} to "
            f"{p['last']['score']} {'now' if p['last']['date'] == 'now' else 'on ' + p['last']['date']} (change {p['change']:+}).")


def _trend_headline(subject: str, stats: dict[str, Any]) -> str:
    """the trend in one sentence: the model once put a 90-day change "in the last 30 days" """
    if not stats.get("points_available") and stats.get("current_score") is None:
        return f"{subject}: no risk score history available."
    parts = [f"{subject}: risk score now {stats.get('current_score')} ({stats.get('current_level')})."]
    for days in (30, 90):
        c = stats.get(f"change_vs_{days}_days_ago")
        if c:
            parts.append(f"{days} days ago it was {c['from_score']} (change {c['change']:+}).")
        else:
            parts.append(f"No snapshot from {days} days ago.")
    if stats.get("data_gap"):
        parts.append(stats["data_gap"])
    return " ".join(parts)


async def user_risk_summary(
    kb: Any, console: str, user_id: int, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    user = await kb.get_user(console, user_id)
    history = await kb.get_user_risk_history(console, user_id, False)
    enrollments = await kb.list_training_enrollments(console, user_id=user_id)
    statuses = Counter(str(e.get("status") or "unknown") for e in enrollments)
    row = _user_row(user) if isinstance(user, dict) else {"id": user_id}
    trend = _history_stats(
        history if isinstance(history, list) else [],
        current=user.get("current_risk_score") if isinstance(user, dict) else None,
    )
    period = _period_stats(history if isinstance(history, list) else [], start_date, end_date,
                           user.get("current_risk_score") if isinstance(user, dict) else None)
    return {
        "console": console,
        "headline": _trend_headline(str(row.get("name") or f"user {user_id}"), trend) + _period_sentence(period),
        "period": period,
        "user": row,
        "risk_trend": trend,
        # the data behind "why": phishing failures and training status
        "why_signals": {
            "phish_prone_percent": _r(user.get("phish_prone_percentage")) if isinstance(user, dict) else None,
            "phish_prone_vs_benchmark": ppp_vs_benchmark(user.get("phish_prone_percentage")) if isinstance(user, dict) else None,
            "training_enrollments": len(enrollments),
            "training_by_status": dict(statuses),
        },
        "scale": RISK_SCALE_NOTE,
    }


async def account_risk_overview(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    account = await kb.get_account(console)
    # a period can reach back further than the short default history
    history = await kb.get_account_risk_history(console, bool(start_date or end_date))
    users = await kb.list_users(console, "active")
    ppp = [u["phish_prone_percentage"] for u in users if isinstance(u.get("phish_prone_percentage"), (int, float))]
    scores = [u["current_risk_score"] for u in users if isinstance(u.get("current_risk_score"), (int, float))]
    score = account.get("current_risk_score") if isinstance(account, dict) else None
    trend = _history_stats(history if isinstance(history, list) else [], current=score)
    period = _period_stats(history if isinstance(history, list) else [], start_date, end_date, score)
    levels = Counter(risk_level(s) for s in scores)
    failed = sum(1 for p in ppp if p > 0)
    # stated outright: the model once read this breakdown as "all 55 users are Low"
    spread = ", ".join(f"{name} {levels[name]}" for _, name in RISK_LEVELS if levels.get(name))
    return {
        "console": console,
        "headline": _trend_headline("The organisation", {**trend, "current_score": _r(score), "current_level": risk_level(score)})
        + _period_sentence(period)
        + (f" Active users per risk level: {spread} ({len(users)} in total); {failed} of them failed a phishing test." if users else ""),
        "period": period,
        "account_name": account.get("name") if isinstance(account, dict) else None,
        "current": {"score": _r(score), "level": risk_level(score)},
        "risk_trend": trend,
        # the data behind "why": how many people fail phishing tests and how risk is spread
        "why_signals": {
            "active_users": len(users),
            "users_who_failed_a_phishing_test": failed,
            "average_user_phish_prone_percent": _r(sum(ppp) / len(ppp)) if ppp else None,
            "average_phish_prone_vs_benchmark": ppp_vs_benchmark(sum(ppp) / len(ppp)) if ppp else None,
            "users_by_risk_level": dict(levels),
        },
        "scale": RISK_SCALE_NOTE,
    }


async def list_users_page(
    kb: Any, console: str, status: str = "active", sort: str = "risk", offset: int = 0, limit: int = 20
) -> dict[str, Any]:
    users = await kb.list_users(console, status or None)
    if sort == "name":
        users.sort(key=lambda u: _name(u).lower())
    else:
        sort = "risk"
        users.sort(key=lambda u: u.get("current_risk_score") if isinstance(u.get("current_risk_score"), (int, float)) else -1, reverse=True)
    offset = max(0, int(offset or 0))
    # pages of at most 20, so every row can be shown as its own table line
    size = max(1, min(int(limit or PAGE_SIZE), PAGE_SIZE))
    page = users[offset: offset + size]
    shown_to = offset + len(page)
    return {
        "console": console,
        "status_filter": status or "all",
        "sort": "highest risk first" if sort == "risk" else "by name",
        "total_users": len(users),
        "showing": f"{offset + 1}-{shown_to} of {len(users)}" if page else f"none (only {len(users)} users)",
        "next_offset": shown_to if shown_to < len(users) else None,
        "users": [{"number": offset + i + 1, **_user_row(u)} for i, u in enumerate(page)],
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
        "metric": "risk_score (higher = riskier)",
        "scale": RISK_SCALE_NOTE,
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
        # the agent stops detail lookups in the same answer when this is set
        "ask_user": len(found) > 1,
        "matches": [_user_row(u) for u in found[: _limit(limit)]],
        "next_step": (
            "Several people match: list them numbered and ask which one. Do not fetch their details yet."
            if len(found) > 1 else "Use user_risk_summary with this id for their risk and history."
        ),
    }


def _test_percent(value: Any) -> float | None:
    # on security tests the api returns failure events / delivered as a fraction
    # (matched 67 of 67 live tests, Nov 2026); users already use 0-100
    return round(value * 100, 2) if isinstance(value, (int, float)) else None


async def phishing_campaign_summary(
    kb: Any, console: str, limit: int = 10, sort: str = "latest", start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    tests = [t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), start_date, end_date)]
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
    # the model averaged these itself once (and got 64.33%); give it the figure instead.
    # weighted by emails delivered = all failures / all delivered emails across every test
    weighted = [(t["phish_prone_percentage"], t["delivered_count"]) for t in tests
                if isinstance(t.get("phish_prone_percentage"), (int, float)) and isinstance(t.get("delivered_count"), int) and t["delivered_count"] > 0]
    delivered = sum(d for _, d in weighted)
    overall = _test_percent(sum(p * d for p, d in weighted) / delivered) if delivered else None
    period = _period_label(start_date, end_date)
    return {
        "console": console,
        "period": period or "all tests",
        "headline": (
            f"{'From ' + period + ': ' if period else ''}{len(tests)} phishing security tests; across all of them "
            f"{overall}% of delivered emails led to a failure." if tests else
            f"No phishing security tests{' from ' + period if period else ''}."
        ),
        "sort": sort,
        "total_security_tests": len(tests),
        "all_tests_phish_prone_percent": overall,
        "all_tests_vs_benchmark": ppp_vs_benchmark(overall),
        "averages_note": (
            "all_tests_phish_prone_percent = all failures / all delivered emails across every test. "
            "KnowBe4's organisation figure is the average over active users (account_risk_overview). "
            "Never calculate averages yourself."
        ),
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
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
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
        score = account.get("current_risk_score") if isinstance(account, dict) else None
        available.append({
            "console": key,
            "display_name": console.display_name,
            "risk_score": _r(score),
            "risk_level": risk_level(score),
        })

    available.sort(key=lambda r: r["risk_score"] if isinstance(r["risk_score"], (int, float)) else -1, reverse=True)
    return {
        "metric": "risk_score (higher = riskier)",
        "scale": RISK_SCALE_NOTE,
        "consoles": available,
        "unavailable": unavailable,
    }


# what counts as failing a phishing test. clicked, data entered, attachment opened and qr code scanned
# reproduce the api's own phish_prone_percentage on 68 of 68 live tests (Nov 2026); macros and replies
# never occurred in that data, so including them is unconfirmed but matches how KnowBe4 describes failures
FAILURE_EVENTS = {
    "clicked_at": "clicked the link",
    "data_entered_at": "entered data",
    "attachment_opened_at": "opened the attachment",
    "macro_enabled_at": "enabled macros",
    "replied_at": "replied",
    "qr_code_scanned": "scanned the QR code",
}
MAX_TESTS = 12
NO_ADVICE = "Start from the headline. Report only these facts; do not add advice or recommendations."


def _failures(recipient: dict[str, Any]) -> list[str]:
    return [label for field, label in FAILURE_EVENTS.items() if recipient.get(field)]


def _recipient_name(recipient: dict[str, Any]) -> str:
    return _name(recipient.get("user") or {}) or "?"


def _pct(part: int, whole: int) -> float | None:
    return round(part * 100 / whole, 2) if whole else None


def _latest_tests(tests: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    return sorted(tests, key=lambda t: str(t.get("started_at") or ""), reverse=True)[:count]


def _ppp_stats(members: list[dict[str, Any]]) -> dict[str, Any]:
    ppp = [m["phish_prone_percentage"] for m in members if isinstance(m.get("phish_prone_percentage"), (int, float))]
    return {
        "average_phish_prone_percent": _r(sum(ppp) / len(ppp)) if ppp else None,
        "users_who_failed_a_phishing_test": sum(1 for p in ppp if p > 0),
    }


async def risk_by_group(kb: Any, console: str, by: str = "group", limit: int = 10) -> dict[str, Any]:
    """where risk sits: KnowBe4 groups (with KnowBe4's own group risk score) or a user field such as department"""
    users = await kb.list_users(console, "active")
    if by in ("department", "location", "division"):
        buckets: dict[str, list[dict[str, Any]]] = {}
        for u in users:
            value = str(u.get(by) or "").strip()
            if value:
                buckets.setdefault(value, []).append(u)
        if not buckets:
            return {
                "console": console,
                "by": by,
                "groups": [],
                "note": f"The {by} field is empty for every active user in KnowBe4, so there is no {by} breakdown. Use by=group.",
            }
        rows = []
        for value, members in buckets.items():
            scores = [m["current_risk_score"] for m in members if isinstance(m.get("current_risk_score"), (int, float))]
            avg = sum(scores) / len(scores) if scores else None
            rows.append({
                "name": value,
                "active_users": len(members),
                "risk_score": _r(avg),
                "risk_level": risk_level(avg),
                **_ppp_stats(members),
            })
        source = f"average risk score of the active users in each {by}"
    else:
        by = "group"
        groups = await kb.list_groups(console)
        members_of: dict[Any, list[dict[str, Any]]] = {}
        for u in users:
            for gid in u.get("groups") or []:
                members_of.setdefault(gid, []).append(u)
        rows = []
        for g in groups:
            members = members_of.get(g.get("id"), [])
            if not members:
                continue
            score = g.get("current_risk_score")
            rows.append({
                "name": g.get("name"),
                "active_users": len(members),
                "risk_score": _r(score),
                "risk_level": risk_level(score),
                **_ppp_stats(members),
            })
        source = "KnowBe4's own risk score for each group"
    rows.sort(key=lambda r: r["risk_score"] if isinstance(r["risk_score"], (int, float)) else -1, reverse=True)
    top = rows[0] if rows else None
    return {
        "console": console,
        # small models garble facts they rephrase; this sentence is built from the data
        "headline": (
            f"Riskiest {by}: {top['name']} (risk score {top['risk_score']}, {top['risk_level']}) with "
            f"{top['active_users']} active users, out of {len(rows)} {by}s that have active users."
            if top else f"No {by}s with active users."
        ),
        "note": NO_ADVICE,
        "by": by,
        "ranked_by": source + " (higher = riskier)",
        "groups_with_active_users": len(rows),
        "scale": RISK_SCALE_NOTE,
        "groups": [{"rank": i + 1, **r} for i, r in enumerate(rows[: _limit(limit)])],
    }


async def repeat_phishing_failures(
    kb: Any, console: str, tests: int = 6, limit: int = 10, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """people who failed more than one of the latest phishing tests (one api request per test, cached)"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    count = max(1, min(int(tests or 6), MAX_TESTS))
    in_period = [t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), start_date, end_date)]
    if start_date or end_date:
        # a period means every test in it, up to the cap
        count = MAX_TESTS
    latest = _latest_tests(in_period, count)
    period = _period_label(start_date, end_date)
    people: dict[Any, dict[str, Any]] = {}
    for t in latest:
        for r in await kb.list_pst_recipients(console, t.get("pst_id")):
            if not r.get("delivered_at"):
                continue
            user = r.get("user") or {}
            key = user.get("id") or user.get("email") or r.get("recipient_id")
            row = people.setdefault(key, {
                "id": user.get("id"), "name": _recipient_name(r), "received": 0, "failed": 0, "last_failed": "", "actions": Counter(),
            })
            row["received"] += 1
            failed = _failures(r)
            if failed:
                row["failed"] += 1
                row["last_failed"] = max(row["last_failed"], _date(t.get("started_at")))
                row["actions"].update(failed)
    repeat = sorted((p for p in people.values() if p["failed"] >= 2), key=lambda p: (p["failed"], p["last_failed"]), reverse=True)
    once = sum(1 for p in people.values() if p["failed"] == 1)
    return {
        "console": console,
        "period": period or f"the last {len(latest)} tests",
        "tests_in_period": len(in_period),
        "headline": (
            f"{'From ' + period + ': ' if period else ''}{len(repeat)} of {len(people)} people failed two or more of "
            f"the {'latest ' if len(latest) < len(in_period) else ''}{len(latest)} phishing tests checked; "
            f"{once} failed once and {len(people) - len(repeat) - once} never failed."
        ),
        "note": NO_ADVICE,
        "tests_checked": len(latest),
        "tests_period": f"{_date(latest[-1].get('started_at'))} to {_date(latest[0].get('started_at'))}" if latest else None,
        "people_who_received_a_test": len(people),
        "failed_two_or_more_tests": len(repeat),
        "failed_exactly_once": once,
        "never_failed": len(people) - len(repeat) - once,
        "failure_means": "clicked the link, entered data, opened the attachment, enabled macros, replied or scanned the QR code",
        "repeat_failures": [
            {
                "rank": i + 1,
                "id": p["id"],
                "name": p["name"],
                "failed": f"{p['failed']} of {p['received']} tests",
                "last_failed": p["last_failed"],
                "what_they_did": dict(p["actions"]),
            }
            for i, p in enumerate(repeat[: _limit(limit)])
        ],
    }


async def phishing_test_detail(
    kb: Any, console: str, pst_id: int | None = None, limit: int = 20, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """one phishing test person by person: who failed, who reported it, and the report rate"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    if pst_id is None:
        tests = [t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), start_date, end_date)]
        latest = _latest_tests(tests, 1)
        if not latest:
            period = _period_label(start_date, end_date)
            return {"console": console, "error": True, "message": f"No phishing security tests found{' from ' + period if period else ''}."}
        test = latest[0]
    else:
        test = await kb.get_phishing_security_test(console, pst_id)
    recipients = await kb.list_pst_recipients(console, test.get("pst_id"))
    delivered = [r for r in recipients if r.get("delivered_at")]
    failed = [r for r in delivered if _failures(r)]
    reported = [r for r in delivered if r.get("reported_at")]
    events = {label: sum(1 for r in delivered if r.get(field)) for field, label in FAILURE_EVENTS.items()}
    return {
        "console": console,
        "headline": (
            f"Phishing test \"{test.get('name')}\" ({_date(test.get('started_at'))}): {len(failed)} of {len(delivered)} people "
            f"failed it ({_pct(len(failed), len(delivered))}%) and {len(reported)} reported it "
            f"(report rate {_pct(len(reported), len(delivered))}%)."
        ),
        "note": NO_ADVICE,
        "pst_id": test.get("pst_id"),
        "name": test.get("name"),
        "started_at": _date(test.get("started_at")),
        "status": test.get("status"),
        "delivered": len(delivered),
        "opened": sum(1 for r in delivered if r.get("opened_at")),
        "people_who_failed": len(failed),
        "people_who_failed_percent": _pct(len(failed), len(delivered)),
        "phish_prone_percent": _test_percent(test.get("phish_prone_percentage")),
        "failures_by_action": {k: v for k, v in events.items() if v},
        "reported": len(reported),
        "report_rate_percent": _pct(len(reported), len(delivered)),
        "report_rate_note": "Report rate = people who reported the email (Phish Alert Button) / emails delivered. Higher is better.",
        "failed_people": [
            {"name": _recipient_name(r), "what_they_did": _failures(r), "also_reported": bool(r.get("reported_at"))}
            for r in failed[: max(1, min(int(limit or 20), MAX_LIMIT))]
        ],
    }


async def overdue_training(
    kb: Any, console: str, limit: int = 10, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """past-due training enrolments of current users: how many, who has the most, which modules"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    enrollments = [e for e in await kb.list_training_enrollments(console, exclude_archived_users=True)
                   if _within(e.get("enrollment_date"), start_date, end_date)]
    period = _period_label(start_date, end_date)
    statuses = Counter(str(e.get("status") or "unknown") for e in enrollments)
    overdue = [e for e in enrollments if e.get("status") == "Past Due"]
    per_user: dict[Any, dict[str, Any]] = {}
    for e in overdue:
        user = e.get("user") or {}
        row = per_user.setdefault(user.get("id"), {"id": user.get("id"), "name": _name(user) or "?", "past_due": 0})
        row["past_due"] += 1
    people = sorted(per_user.values(), key=lambda p: p["past_due"], reverse=True)
    modules = Counter(str(e.get("module_name") or "?") for e in overdue)
    return {
        "console": console,
        "headline": (
            f"{'Enrolled from ' + period + ': ' if period else ''}"
            f"{len(overdue)} of {len(enrollments)} training enrolments ({_pct(len(overdue), len(enrollments))}%) are Past Due, "
            # "held by" came out as "ditahan oleh" (detained by) in indonesian answers
            f"and {len(people)} people have at least one; {people[0]['name']} has the most ({people[0]['past_due']})."
            if people else f"None of the {len(enrollments)} training enrolments is Past Due."
        ),
        "period": f"enrolled {period}" if period else "all enrolments",
        "enrollments": len(enrollments),
        "by_status": dict(statuses),
        "past_due": len(overdue),
        "past_due_percent": _pct(len(overdue), len(enrollments)),
        "people_with_past_due_training": len(people),
        "most_overdue_people": [{"rank": i + 1, **p} for i, p in enumerate(people[: _limit(limit)])],
        "most_overdue_modules": [{"module": m, "past_due": n} for m, n in modules.most_common(_limit(limit))],
        "note": "Past Due = the due date has passed without the training being completed. Archived users are left out. " + NO_ADVICE,
    }
