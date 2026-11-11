"""Small, pre-computed answers for the chat model.

Each function pulls the full collection through KnowBe4Client, does the sorting and
arithmetic in Python and returns a compact result, so a local model with a small
context never has to read thousands of raw records.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
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
    # "Dewi Lestari" also matched an archived "Lestari Dewi Lestari": one active person with exactly that name is the one meant
    exact = [u for u in found if _name(u).lower() == " ".join(needle.split()) and u.get("status") == "active"]
    chosen = exact[0] if len(found) > 1 and len(exact) == 1 else None
    if chosen:
        found = [chosen] + [u for u in found if u is not chosen]
    ask = len(found) > 1 and not chosen
    return {
        "console": console,
        "query": query,
        "searched": len(users),
        "match_count": len(found),
        # the agent stops detail lookups in the same answer when this is set
        "ask_user": ask,
        **({"chosen": chosen.get("id")} if chosen else {}),
        "matches": [_user_row(u) for u in found[: _limit(limit)]],
        "next_step": (
            "Several people match: list them numbered and ask which one. Do not fetch their details yet." if ask else
            "One active person has exactly this name (the first match); use their id. The others only partly match or are archived."
            if chosen else "Use user_risk_summary with this id for their risk and history."
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
    # the model made up why a campaign sat at 0% ("those are phishing tests"); the enrolment statuses say why
    statuses: dict[Any, Counter] = {}
    for e in await kb.list_training_enrollments(console, exclude_archived_users=True, include_campaign_id=True):
        statuses.setdefault(e.get("campaign_id"), Counter())[str(e.get("status") or "unknown")] += 1
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
                "enrolments_by_status": dict(statuses.get(c.get("campaign_id"), {})),
            }
            for c in shown
        ],
        "order": "newest start_date first",
        "note": ("A campaign's completion % comes from its enrolments: enrolments_by_status shows how many passed, are Past Due, "
                 "not started or in progress (current users). Explain a completion % only from these counts; do not guess other reasons."),
    }


# a person's status over the campaign's modules: the one that still needs work counts
STATUS_RANK = {"Past Due": 4, "Not Started": 3, "In Progress": 2, "Passed": 0, "Completed": 0}
STATUS_COLUMN = {"Passed": "completed", "Completed": "completed", "In Progress": "in_progress", "Not Started": "not_started",
                 "Past Due": "past_due"}


def _group_names(value: Any) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    return [str(v).strip() for v in value or [] if str(v).strip()]


def _find_group(name: str, groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    """exact name first (case-insensitive), then a single word-start match"""
    exact = [g for g in groups if str(g.get("name") or "").casefold() == name.casefold()]
    if exact:
        return exact[0]
    loose = [g for g in groups if _words_match(g.get("name"), name)]
    return loose[0] if len(loose) == 1 else None


def _campaign_targets(c: dict[str, Any]) -> set[Any]:
    return {g.get("group_id") or g.get("id") for g in c.get("groups") or []}


async def _named_groups(kb: Any, console: str, groups: Any, text: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """the groups a question is about: the list the model passed plus the names written in the question.
    archived groups too: naming one gave "not found" while its people still had results"""
    all_groups = await kb.list_groups(console, "all")
    asked = _group_names(groups)
    if text:
        # group names written in the question ("Group-A1, Group-B1, ..."): a model copying 21 names can drop some
        lowered = text.casefold()
        seen = {a.casefold() for a in asked}
        found = []
        for g in all_groups:
            name = str(g.get("name") or "")
            m = re.search(rf"(?<![\w-]){re.escape(name.casefold())}(?![\w-])", lowered) if name else None
            if m and name.casefold() not in seen:
                found.append((m.start(), name))
        # in the order the question lists them, not KnowBe4's order
        asked += [name for _, name in sorted(found)]
    resolved, unknown = [], []
    for name in asked:
        found = _find_group(name, all_groups)
        if found and found not in resolved:
            resolved.append(found)
        elif not found:
            unknown.append(name)
    return all_groups, resolved, unknown


async def _pick_campaigns(kb: Any, console: str, campaign: str | None, campaign_date: str | None,
                          resolved: list[dict[str, Any]]) -> dict[str, Any]:
    """{"picked": [...]} or a result to return as it is (error, or ask which one)"""
    if campaign_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", campaign_date.strip()):
        return {"console": console, "error": True, "message": "campaign_date must be a date like 2026-10-07."}
    picked = await kb.list_training_campaigns(console)
    if campaign and str(campaign).strip():
        wanted = str(campaign).strip()
        picked = [c for c in picked if str(c.get("campaign_id")) == wanted] if wanted.isdigit() else \
            [c for c in picked if _words_match(c.get("name"), wanted)]
    if campaign_date:
        picked = [c for c in picked if _date(c.get("start_date")) == campaign_date.strip()]
    if not (campaign or campaign_date):
        # nothing named: the newest campaign
        picked = sorted(picked, key=lambda c: str(c.get("start_date") or ""), reverse=True)[:1]
    if not picked:
        what = " and ".join(p for p in (f"named '{campaign}'" if campaign else "", f"starting {campaign_date}" if campaign_date else "") if p)
        return {"console": console, "error": True, "message": f"No training campaign {what}."}
    by_date = bool(campaign_date) and not campaign
    if len(picked) > 1 and resolved:
        wanted_ids = {g.get("id") for g in resolved}
        covering = [c for c in picked if wanted_ids & _campaign_targets(c)]
        if covering and by_date:
            # one day's rollout comes in language versions (four campaigns on 2026-10-07): every one aimed at a named group
            # counts. keeping only the best match left five named groups out
            picked = covering
        elif covering:
            best = max(len(wanted_ids & _campaign_targets(c)) for c in covering)
            picked = [c for c in covering if len(wanted_ids & _campaign_targets(c)) == best]
    if len(picked) > 1 and not by_date:
        return {"console": console, "ask_user": True,
                "message": "Several training campaigns match; ask which one.",
                "matches": [{"campaign_id": c.get("campaign_id"), "name": c.get("name"), "start_date": _date(c.get("start_date")),
                             "status": c.get("status"), "groups": [g.get("name") for g in c.get("groups") or []]} for c in picked[:10]]}
    return {"picked": picked}


async def training_by_group(
    kb: Any, console: str, campaign: str | None = None, campaign_date: str | None = None, groups: Any = None,
    by: str = "user", text: str | None = None, include_archived: bool = False,
) -> dict[str, Any]:
    """one training campaign per group: how many completed, are in progress, not started or Past Due.
    the model could not join enrolments, people and groups itself (1,596 enrolments in the first live case)"""
    if campaign_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", campaign_date.strip()):
        return {"console": console, "error": True, "message": "campaign_date must be a date like 2026-10-07."}
    if by not in ("user", "enrolment"):
        by = "user"
    all_groups, resolved, unknown = await _named_groups(kb, console, groups, text)
    chosen = await _pick_campaigns(kb, console, campaign, campaign_date, resolved)
    if "picked" not in chosen:
        return chosen
    picked = chosen["picked"]
    picked.sort(key=lambda c: (str(c.get("start_date") or ""), c.get("campaign_id") or 0))
    camp_ids = {c.get("campaign_id") for c in picked}
    targeted = set().union(*(_campaign_targets(c) for c in picked))
    if not resolved:
        by_id = {g.get("id"): g for g in all_groups}
        seen_ids: set[Any] = set()
        for c in picked:
            for g in c.get("groups") or []:
                gid = g.get("group_id") or g.get("id")
                if gid not in seen_ids:
                    seen_ids.add(gid)
                    resolved.append(by_id.get(gid) or {"id": gid, "name": g.get("name")})

    # every enrolment and every person once, then active / archived in code: two fetches cost ~100 requests on a big account
    enrolments = [e for e in await kb.list_training_enrollments(console, include_campaign_id=True)
                  if e.get("campaign_id") in camp_ids]
    people = {u.get("id"): u for u in await kb.list_users(console)}
    per_user: dict[Any, list[str]] = {}
    archived: dict[Any, list[str]] = {}
    campaigns_of: dict[Any, set[Any]] = {}
    for e in enrolments:
        uid = (e.get("user") or {}).get("id")
        campaigns_of.setdefault(uid, set()).add(e.get("campaign_id"))
        # archived people left the organisation; they are counted only when asked (Group-A1: 17 active, 33 with archived)
        bucket = per_user if include_archived or (people.get(uid) or {}).get("status") != "archived" else archived
        bucket.setdefault(uid, []).append(str(e.get("status") or "unknown"))
    member_of = {uid: set(u.get("groups") or []) for uid, u in people.items()}

    def tally(user_ids: list[Any]) -> dict[str, int]:
        counts = Counter()
        for uid in user_ids:
            statuses = per_user[uid] if by == "enrolment" else [max(per_user[uid], key=lambda s: STATUS_RANK.get(s, 1))]
            for s in statuses:
                counts[STATUS_COLUMN.get(s, "other")] += 1
        row = {k: counts[k] for k in ("completed", "in_progress", "not_started", "past_due")}
        if counts["other"]:
            row["other"] = counts["other"]
        total = sum(counts.values())
        # both shares: the model once put the completed share (53.16%) next to the Past Due count
        return {"total": total, **row, "percent_complete": _r(100 * row["completed"] / total) if total else None,
                "percent_past_due": _r(100 * row["past_due"] / total) if total else None}

    rows, everyone, left_out, not_targeted = [], set(), set(), []
    for g in resolved:
        uids = [uid for uid in per_user if g.get("id") in member_of.get(uid, set())]
        gone = [uid for uid in archived if g.get("id") in member_of.get(uid, set())]
        if not uids and not gone and g.get("id") not in targeted:
            # named, but none of these campaigns was aimed at it: say so instead of a row of zeros
            not_targeted.append(g.get("name"))
            continue
        everyone.update(uids)
        left_out.update(gone)
        rows.append({"group": g.get("name"), **tally(uids), **({"archived_not_counted": len(gone)} if gone else {})})
    totals = tally(sorted(everyone, key=str))
    # KnowBe4 counts a person in every campaign they are in: 945 for the four campaigns of 2026-10-07, 944 different people
    in_several = sorted((uid for uid in everyone if len(campaigns_of.get(uid, ())) > 1), key=str)
    per_campaign = sum(len(campaigns_of.get(uid, ())) for uid in everyone)
    unit = "people" if by == "user" else "enrolments"
    starts = sorted({_date(c.get("start_date")) for c in picked})
    started = starts[0] if len(starts) == 1 else f"{starts[0]} – {starts[-1]}"
    names = list(dict.fromkeys(str(c.get("name") or "").strip() for c in picked))
    # language versions share the main name: "Awareness Training" four times read badly
    shortest = min(names, key=len)
    name = names[0] if len(picked) == 1 else (f"{shortest} ({len(picked)} campaigns)" if all(n.startswith(shortest) for n in names)
                                              else " + ".join(names))
    camp = {"campaign_id": picked[0].get("campaign_id") if len(picked) == 1 else None, "name": name,
            "status": " / ".join(sorted({str(c.get("status")) for c in picked}))}
    return {
        "console": console,
        "campaign": {**camp, "start_date": started, "campaign_ids": sorted(camp_ids),
                     "modules": sorted({m.get("name") for c in picked for m in c.get("content") or [] if m.get("name")})},
        "counted_by": by,
        "headline": (f"{camp.get('name').strip()} (started {started}, {camp.get('status')}): {totals['total']} {unit} in {len(rows)} groups; "
                     f"{totals['completed']} completed, {totals['in_progress']} in progress, {totals['not_started']} not started, "
                     f"{totals['past_due']} Past Due ({totals['percent_complete']}% complete)."
                     + (f" {len(left_out)} archived people in these groups are not counted." if left_out else "")
                     + (f" The campaigns add up to {per_campaign} people because {len(in_several)} person(s) were enrolled in more "
                        f"than one of them." if by == "user" and in_several else "")),
        "people_counted_per_campaign": per_campaign,
        "people_in_several_campaigns": len(in_several),
        "groups": rows,
        "totals": totals,
        "archived_not_counted": len(left_out),
        "unknown_groups": unknown,
        "not_in_these_campaigns": not_targeted,
        "rule": ("each person counts once per group, by the status of their least finished module (one Past Due module makes them "
                 "Past Due); a person in two groups is in both rows but once in the totals") if by == "user" else
                "every module enrolment counts on its own",
        "note": ("The table with every group is added to the answer automatically: do not list the groups again; name at most three "
                 "that stand out and explain the totals. percent_complete "
                 "is the share that completed, percent_past_due the share that is Past Due; never put one next to the other's count. "
                 + NO_ADVICE),
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


def _minutes_to_fail(recipient: dict[str, Any]) -> float | None:
    """delivered -> first failure, in minutes; None when either time is missing or unreadable"""
    try:
        delivered = datetime.fromisoformat(str(recipient.get("delivered_at")))
        times = [datetime.fromisoformat(str(recipient[f])) for f in FAILURE_EVENTS if recipient.get(f)]
    except ValueError:
        return None
    if not times:
        return None
    return max(0.0, (min(times) - delivered).total_seconds() / 60)


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
    speeds = sorted(m for r in failed if (m := _minutes_to_fail(r)) is not None)
    opened_only = [r for r in delivered if r.get("opened_at") and not _failures(r) and not r.get("reported_at")]
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
        "speed_of_failure": {
            "people_timed": len(speeds),
            "fastest_minutes": round(speeds[0], 1) if speeds else None,
            "median_minutes": round(_median(speeds), 1) if speeds else None,
            "within_10_minutes": sum(1 for m in speeds if m <= 10),
            "within_1_hour": sum(1 for m in speeds if m <= 60),
            "meaning": "minutes from the email being delivered to the person's first failure",
        },
        "opened_but_did_nothing": len(opened_only),
        "bounced": sum(1 for r in recipients if r.get("bounced_at")),
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


# enrolment statuses seen live (Nov 2026): Passed, Past Due, Not Started, In Progress
DONE_STATUSES = {"Passed", "Completed"}
# time_spent has no unit in KnowBe4's docs; against 4-10 minute modules the values only make sense as seconds
TIME_SPENT_NOTE = "KnowBe4's docs give time_spent without a unit; the values match seconds, so minutes = time_spent / 60."
MODULE_SORTS = ("least_completed", "most_overdue", "most_enrolled", "most_completed", "longest")


# "The Inside Man: Season 1 Ep 01 - The New Guy" -> "The Inside Man: Season 1"
EPISODE = re.compile(r"\s*(?:[-:–]\s*)?\b(?:Ep(?:isode)?\.?|Part|Bagian)\s*\d+\b.*$", re.I)


def _series(name: str) -> str | None:
    if not EPISODE.search(name):
        return None
    return EPISODE.sub("", name).strip(" -:–") or None


def _module_facts(r: dict[str, Any], length: Any) -> list[str]:
    """reasons the data supports, so a "why" does not get a made-up one ("shorter, mandatory module")"""
    facts = []
    if 0 < r["enrolled"] < 10:
        facts.append(f"only {r['enrolled']} enrolled, so one person changes the completion by about {round(100 / r['enrolled'])} points")
    if r["enrolled"] and r["past_due"] == r["enrolled"]:
        facts.append("every enrolment is Past Due")
    elif r["enrolled"] and r["passed"] == 0:
        facts.append("nobody has passed yet")
    if r["not_started"] and r["not_started"] >= r["enrolled"] / 2:
        facts.append(f"{r['not_started']} of {r['enrolled']} have not started")
    if length:
        facts.append(f"length as KnowBe4 lists it: {length}")
    return facts


def _words_match(name: Any, query: str) -> bool:
    """every word starts a word in the name; numbers match whole ("season 1" matched "Season 2 Ep 01" as a substring)"""
    text = str(name or "").lower()
    return all(re.search(rf"\b{re.escape(w)}\b" if w.isdigit() else rf"\b{re.escape(w)}", text) for w in query.lower().split())


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


async def training_by_module(
    kb: Any, console: str, module: str | None = None, sort: str = "least_completed", limit: int = 10,
    start_date: str | None = None, end_date: str | None = None, group_series: bool = True,
) -> dict[str, Any]:
    """training per module (course, video, policy): enrolled, passed, past due, not started, completion %, typical time.
    episodes of one series count as one row unless a module is asked for by name (twelve near-identical
    "The Inside Man" episodes filled the whole top 10)"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    if sort not in MODULE_SORTS:
        sort = "least_completed"
    enrollments = [e for e in await kb.list_training_enrollments(console, exclude_archived_users=True)
                   if _within(e.get("enrollment_date"), start_date, end_date)]
    period = _period_label(start_date, end_date)
    by_module: dict[str, list[dict[str, Any]]] = {}
    for e in enrollments:
        by_module.setdefault(str(e.get("module_name") or "?"), []).append(e)
    if module and module.strip():
        matched = {name: rows for name, rows in by_module.items() if _words_match(name, module)}
        if not matched:
            return {
                "console": console, "module": module, "modules": [],
                "headline": f"No training module matches '{module}'{' among enrolments from ' + period if period else ''}.",
                "some_module_names": sorted(by_module)[:15],
                "note": "Tell the user no module matches and offer some of these names. " + NO_ADVICE,
            }
        by_module = matched
        group_series = False

    # one row per series when its episodes are several; a named module keeps every episode apart
    groups: dict[str, list[str]] = {}
    for name in by_module:
        groups.setdefault((_series(name) if group_series else None) or name, []).append(name)
    lengths = {}
    try:
        lengths = {str(p.get("name")): p.get("duration") for p in await kb.list_store_purchases(console)}
    except Exception:  # lengths only add a fact; the summary stands without them
        pass

    rows = []
    for key, names in groups.items():
        items = [e for n in names for e in by_module[n]]
        statuses = Counter(str(e.get("status") or "unknown") for e in items)
        passed = sum(statuses[s] for s in DONE_STATUSES)
        minutes = [e["time_spent"] / 60 for e in items
                   if e.get("status") in DONE_STATUSES and isinstance(e.get("time_spent"), (int, float)) and e["time_spent"] > 0]
        typical = _median(minutes)
        series = len(names) > 1
        row = {
            "module": f"{key} ({len(names)} episodes)" if series else key,
            "type": items[0].get("content_type"),
            "enrolled": len(items),
            "passed": passed,
            "past_due": statuses["Past Due"],
            "in_progress": statuses["In Progress"],
            "not_started": statuses["Not Started"],
            "completion_percent": _pct(passed, len(items)),
            "typical_minutes": round(typical, 1) if typical is not None else None,
        }
        if series:
            row["episodes"] = len(names)
        row["facts"] = _module_facts(row, None if series else lengths.get(key))
        rows.append(row)
    key = {
        "least_completed": lambda r: (r["completion_percent"] or 0, -r["enrolled"]),
        "most_completed": lambda r: (-(r["completion_percent"] or 0), -r["enrolled"]),
        "most_overdue": lambda r: (-r["past_due"], -r["enrolled"]),
        "most_enrolled": lambda r: (-r["enrolled"], r["module"]),
        "longest": lambda r: (-(r["typical_minutes"] or 0), r["module"]),
    }[sort]
    rows.sort(key=key)
    passed_all = sum(r["passed"] for r in rows)
    enrolled_all = sum(r["enrolled"] for r in rows)
    result: dict[str, Any] = {"console": console, "period": f"enrolled {period}" if period else "all enrolments", "sort": sort}
    if len(rows) == 1:
        r = rows[0]
        overdue_people = sorted({_name(e.get("user") or {}) or "?" for n in groups[next(iter(groups))] for e in by_module[n]
                                 if e.get("status") == "Past Due"})
        result["headline"] = (
            f"Module \"{r['module']}\"{' (enrolled from ' + period + ')' if period else ''}: {r['enrolled']} enrolments, "
            f"{r['passed']} passed ({r['completion_percent']}%), {r['past_due']} Past Due, {r['not_started']} not started, "
            f"{r['in_progress']} in progress"
            + (f"; people who passed typically spent {r['typical_minutes']} minutes." if r["typical_minutes"] is not None else ".")
        )
        result["past_due_people"] = overdue_people[: _limit(limit, 20)]
        result["past_due_people_total"] = len(overdue_people)
    elif rows:
        # the first item of the asked order leads: a "best module" answer once opened with the lowest instead,
        # and the model filled in a wrong lowest of its own
        def done(r: dict[str, Any]) -> str:
            return f"\"{r['module']}\" ({r['completion_percent']}%, {r['passed']} of {r['enrolled']} passed)"

        best = max(rows, key=lambda r: (r["completion_percent"] or 0, r["enrolled"]))
        least = min(rows, key=lambda r: (r["completion_percent"] or 0, -r["enrolled"]))
        top = rows[0]
        lead = {
            "most_completed": f"Highest completion: {done(best)}; lowest: {done(least)}.",
            "least_completed": f"Lowest completion: {done(least)}; highest: {done(best)}.",
            "most_overdue": f"Most Past Due: \"{top['module']}\" ({top['past_due']} of {top['enrolled']}).",
            "most_enrolled": f"Most enrolments: \"{top['module']}\" ({top['enrolled']}, {top['completion_percent']}% passed).",
            "longest": f"Longest typical time: \"{top['module']}\" ({top['typical_minutes']} minutes).",
        }[sort]
        result["headline"] = (
            f"{'Enrolled from ' + period + ': ' if period else ''}{len(rows)} training modules"
            f"{' match ' + repr(module) if module else ''}{' (each series counted once)' if any('episodes' in r for r in rows) else ''} with "
            f"{enrolled_all} enrolments; {passed_all} passed ({_pct(passed_all, enrolled_all)}%). {lead}"
        )
    else:
        result["headline"] = f"No training enrolments{' from ' + period if period else ''}."
    result.update({
        "modules_total": len(rows),
        "enrolments": enrolled_all,
        "passed": passed_all,
        # limit 0: every module (the csv export)
        "modules": [{"rank": i + 1, **r} for i, r in enumerate(rows if limit == 0 else rows[: _limit(limit)])],
        "series_note": "Rows ending in '(N episodes)' combine the episodes of one series; ask for the series by name for each episode.",
        "time_note": TIME_SPENT_NOTE + " typical_minutes is the median for people who passed.",
        "note": ("completion_percent = passed / enrolled for that module. Archived users are left out. Explain a module's result "
                 "only with its `facts`; never give other reasons (such as a module being mandatory or short). " + NO_ADVICE),
    })
    return result


LIBRARY_SCOPE = "This is the account's own library (content added from ModStore), not the whole ModStore catalogue."
LIBRARY_SORTS = ("most_used", "newest", "recently_purchased")


async def training_library(
    kb: Any, console: str, content_type: str | None = None, limit: int = 20, sort: str = "most_used",
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    """the training content the company has (store purchases): types, length, publish and purchase dates, retired,
    and which were never assigned. "terbaru" once got "there is no date" though KnowBe4 gives both dates"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    if sort not in LIBRARY_SORTS:
        sort = "most_used"
    purchases = await kb.list_store_purchases(console)
    enrollments = await kb.list_training_enrollments(console, exclude_archived_users=True, include_store_purchase_id=True)
    used = Counter(e.get("store_purchase_id") for e in enrollments)
    if content_type:
        purchases = [p for p in purchases if _words_match(p.get("type"), content_type)]
    period = _period_label(start_date, end_date)
    if period:
        # new to us (purchased) or new from KnowBe4 (published) in the period
        purchases = [p for p in purchases if _within(p.get("publish_date"), start_date, end_date)
                     or _within(p.get("purchase_date"), start_date, end_date)]
        if sort == "most_used":
            sort = "newest"
    types = Counter(str(p.get("type") or "?") for p in purchases)
    never = [p for p in purchases if not used.get(p.get("store_purchase_id")) and not p.get("retired")]
    retired = [p for p in purchases if p.get("retired")]
    order = {
        "most_used": lambda p: (-used.get(p.get("store_purchase_id"), 0), str(p.get("name") or "")),
        "newest": lambda p: str(p.get("publish_date") or ""),
        "recently_purchased": lambda p: str(p.get("purchase_date") or ""),
    }[sort]
    items = sorted(purchases, key=order, reverse=sort != "most_used")
    published = sum(1 for p in purchases if _within(p.get("publish_date"), start_date, end_date)) if period else None
    bought = sum(1 for p in purchases if _within(p.get("purchase_date"), start_date, end_date)) if period else None
    return {
        "console": console,
        "period": period or "all content",
        "sort": sort,
        "headline": (
            (f"From {period}: {len(purchases)} training content items are new ({published} published by KnowBe4, "
             f"{bought} added to the account); " if period else
             f"The account has {len(purchases)} training content items{' of type ' + repr(content_type) if content_type else ''} ")
            + f"({', '.join(f'{n} {t}' for t, n in types.most_common())}); {len(retired)} are retired and "
            f"{len(never)} current ones have never been assigned to anyone. " + LIBRARY_SCOPE
            if purchases else f"No training content{' from ' + period if period else ' in the account'}."
        ),
        "by_type": dict(types),
        # the agent builds the answer's first line from these, so a count is never put under the wrong label
        "counts": {"total": len(purchases), "retired": len(retired), "never_assigned": len(never), "published": published,
                   "added": bought, "start_date": start_date[:10] if start_date else None,
                   "end_date": end_date[:10] if end_date else None, "content_type": content_type},
        "items": [
            {
                "name": p.get("name"),
                "type": p.get("type"),
                "length": p.get("duration"),
                "published": _date(p.get("publish_date")),
                "added_to_account": _date(p.get("purchase_date")),
                "enrolments": used.get(p.get("store_purchase_id"), 0),
                "retired": bool(p.get("retired")),
            }
            for p in items[: _limit(limit, 20)]
        ],
        "never_assigned": [p.get("name") for p in never[: _limit(limit, 20)]],
        "length_note": "KnowBe4 lists the length without a unit.",
        "note": ("Content from the KnowBe4 store that the account has, not the whole ModStore catalogue (the API does not "
                 "list it); never call this ModStore-wide. Enrolments counts current users only. For "
                 "'recommend' questions list facts only (new content, content never assigned), not opinions. " + NO_ADVICE),
    }


async def group_risk_trend(
    kb: Any, console: str, group: str | None = None, limit: int = 5, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """one group's risk score over time, or how the riskiest groups changed (one history request per group)"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    groups = [g for g in await kb.list_groups(console, "active") if g.get("member_count")]
    full = bool(start_date or end_date)
    if group and group.strip():
        matches = [g for g in groups if _words_match(g.get("name"), group)]
        if not matches:
            return {"console": console, "error": True,
                    "message": f"No active group matches '{group}'. Some groups: {', '.join(str(g.get('name')) for g in groups[:12])}."}
        if len(matches) > 1:
            return {"console": console, "group": group, "ask_user": True,
                    "matches": [{"group_id": g.get("id"), "name": g.get("name")} for g in matches[:10]],
                    "next_step": "Several groups match: list them numbered and ask which one."}
        g = matches[0]
        history = await kb.get_group_risk_history(console, g.get("id"), full)
        history = history if isinstance(history, list) else []
        trend = _history_stats(history, current=g.get("current_risk_score"))
        period = _period_stats(history, start_date, end_date, g.get("current_risk_score"))
        return {
            "console": console,
            "group_id": g.get("id"),
            "group": g.get("name"),
            "members": g.get("member_count"),
            "headline": _trend_headline(f"Group {g.get('name')}", trend) + _period_sentence(period),
            "period": period,
            "risk_trend": trend,
            "scale": RISK_SCALE_NOTE,
            "note": NO_ADVICE,
        }
    ranked = sorted((g for g in groups if isinstance(g.get("current_risk_score"), (int, float))),
                    key=lambda g: g["current_risk_score"], reverse=True)[: max(1, min(int(limit or 5), 10))]
    rows, gaps = [], set()
    for g in ranked:
        history = await kb.get_group_risk_history(console, g.get("id"), full)
        trend = _history_stats(history if isinstance(history, list) else [], current=g.get("current_risk_score"))
        if trend.get("data_gap"):
            gaps.add(trend["data_gap"])
        change = trend.get("change_vs_90_days_ago") or {}
        rows.append({
            "group_id": g.get("id"),
            "group": g.get("name"),
            "risk_score": _r(g.get("current_risk_score")),
            "risk_level": risk_level(g.get("current_risk_score")),
            "score_90_days_ago": change.get("from_score"),
            "change_vs_90_days": change.get("change"),
        })
    changed = [r for r in rows if isinstance(r["change_vs_90_days"], (int, float))]
    rose = [r for r in changed if r["change_vs_90_days"] > 0]
    fell = [r for r in changed if r["change_vs_90_days"] < 0]
    biggest = max(changed, key=lambda r: abs(r["change_vs_90_days"])) if changed else None
    return {
        "console": console,
        # "0 rose and 1 fell" read as a full picture when 4 of 5 groups had no snapshot to compare with
        "headline": (
            f"Of the {len(rows)} riskiest groups, {len(changed)} can be compared with 90 days ago: {len(rose)} rose and "
            f"{len(fell)} fell"
            + (f"; the biggest change is {biggest['group']} ({biggest['change_vs_90_days']:+})" if biggest else "")
            + (f". The other {len(rows) - len(changed)} have no snapshot from 90 days ago." if len(changed) < len(rows) else ".")
            + (f" {' '.join(sorted(gaps))}" if gaps else "")
            if rows else "No active groups with members."
        ),
        "groups": rows,
        "scale": RISK_SCALE_NOTE,
        "note": "Changes are from KnowBe4's weekly group snapshots to the current group score. " + NO_ADVICE,
    }


async def sign_in_activity(kb: Any, console: str, limit: int = 20) -> dict[str, Any]:
    """who never signed in to KnowBe4 and who has not for a long time (KnowBe4's last_sign_in field, active users)"""
    users = await kb.list_users(console, "active")
    today = date.today()
    never, old, recent, middle = [], [], [], []
    for u in users:
        day = _date(u.get("last_sign_in"))
        if not day:
            never.append(u)
            continue
        age = (today - date.fromisoformat(day)).days
        (recent if age <= 30 else middle if age <= 90 else old).append((age, u))
    old.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "console": console,
        "headline": (
            f"Of {len(users)} active users, {len(never)} have never signed in to KnowBe4, {len(old)} last signed in more than "
            f"90 days ago, {len(middle)} between 31 and 90 days ago and {len(recent)} in the last 30 days."
        ),
        "never_signed_in": len(never),
        "never_signed_in_people": [{"id": u.get("id"), "name": _name(u), "risk_score": _r(u.get("current_risk_score")),
                                    "risk_level": risk_level(u.get("current_risk_score"))}
                                   for u in sorted(never, key=_name)[: _limit(limit, 20)]],
        "longest_since_sign_in": [{"name": _name(u), "last_sign_in": _date(u.get("last_sign_in")), "days_ago": age}
                                  for age, u in old[: _limit(limit, 20)]],
        "note": "Based on KnowBe4's last_sign_in date for each active user. " + NO_ADVICE,
    }


async def new_joiners(
    kb: Any, console: str, limit: int = 10, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """people who joined in the period (start date, or the date they were added to KnowBe4) against everyone else"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    if not (start_date or end_date):
        start_date = (date.today() - timedelta(days=182)).isoformat()
    users = await kb.list_users(console, "active")
    field = "employee_start_date" if any(u.get("employee_start_date") for u in users) else "joined_on"
    joiners = [u for u in users if _date(u.get(field)) and _within(u.get(field), start_date, end_date)]
    others = [u for u in users if u not in joiners]
    enrollments = await kb.list_training_enrollments(console, exclude_archived_users=True)
    past_due = Counter((e.get("user") or {}).get("id") for e in enrollments if e.get("status") == "Past Due")
    period = _period_label(start_date, end_date)

    def stats(people: list[dict[str, Any]]) -> dict[str, Any]:
        scores = [u["current_risk_score"] for u in people if isinstance(u.get("current_risk_score"), (int, float))]
        avg = sum(scores) / len(scores) if scores else None
        return {"people": len(people), "average_risk_score": _r(avg), "average_risk_level": risk_level(avg),
                **_ppp_stats(people), "with_past_due_training": sum(1 for u in people if past_due.get(u.get("id")))}

    mine, rest = stats(joiners), stats(others)
    rows = sorted(joiners, key=lambda u: u.get("current_risk_score") or 0, reverse=True)
    return {
        "console": console,
        "date_used": field + (" (when the user was added to KnowBe4; no employee start dates are filled in)" if field == "joined_on" else ""),
        "period": period,
        "headline": (
            f"{mine['people']} active users joined from {period}; their average risk score is {mine['average_risk_score']} "
            f"({mine['average_risk_level']}) against {rest['average_risk_score']} ({rest['average_risk_level']}) for the other "
            f"{rest['people']}. {mine['users_who_failed_a_phishing_test']} of them failed a phishing test and "
            f"{mine['with_past_due_training']} have Past Due training."
            if joiners else f"No active users joined from {period}."
        ),
        "joiners": mine,
        "everyone_else": rest,
        "people": [{"name": _name(u), "joined": _date(u.get(field)), "risk_score": _r(u.get("current_risk_score")),
                    "risk_level": risk_level(u.get("current_risk_score")), "phish_prone_percent": _r(u.get("phish_prone_percentage")),
                    "past_due_training": past_due.get(u.get("id"), 0)} for u in rows[: _limit(limit)]],
        "scale": RISK_SCALE_NOTE,
        "note": NO_ADVICE,
    }


async def callback_phishing_summary(
    kb: Any, console: str, limit: int = 10, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """callback (phone) phishing: who called the number in the email and who gave data on the call"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    tests = [t for t in await kb.list_phishing_security_tests(console, "callback") if _within(t.get("started_at"), start_date, end_date)]
    period = _period_label(start_date, end_date)
    with_calls = [t for t in tests if t.get("called_count") or t.get("callback_data_entered_count")]
    called = sum(t.get("called_count") or 0 for t in tests)
    gave_data = sum(t.get("callback_data_entered_count") or 0 for t in tests)
    with_calls.sort(key=lambda t: str(t.get("started_at") or ""), reverse=True)
    return {
        "console": console,
        "period": period or "all tests",
        "headline": (
            f"Callback phishing{' from ' + period if period else ''}: {called} calls to the phone number and {gave_data} people "
            f"gave data on the call, across {len(with_calls)} tests with callback results."
            if with_calls else
            f"No callback (phone) phishing results{' from ' + period if period else ''}: nobody called the number in any of the "
            f"{len(tests)} phishing tests, so the account has no callback phishing activity to report."
        ),
        "tests_checked": len(tests),
        "tests_with_callback_results": len(with_calls),
        "called": called,
        "data_entered_on_call": gave_data,
        "tests": [{"name": t.get("name"), "started_at": _date(t.get("started_at")), "delivered": t.get("delivered_count"),
                   "called": t.get("called_count"), "data_entered_on_call": t.get("callback_data_entered_count")}
                  for t in with_calls[: _limit(limit)]],
        "note": "Callback phishing emails ask people to phone a number; 'called' = they phoned it. " + NO_ADVICE,
    }
