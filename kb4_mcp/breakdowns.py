"""Breakdowns the model cannot join itself: phishing per group, who is behind in a campaign, a group's members, one person's
training, who was never tested or trained, and two periods side by side.

Built after a per-group training question was cut off at the token limit: the model tried to join enrolments, people and
groups itself. Counting, sorting and comparing happen here, as in summaries.py; the answers start from a code-built headline.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any

from kb4_mcp.summaries import (
    MAX_TESTS,
    NO_ADVICE,
    STATUS_COLUMN,
    STATUS_RANK,
    _bad_period,
    _date,
    _failures,
    _find_group,
    _limit,
    _name,
    _named_groups,
    _pct,
    _period_label,
    _pick_campaigns,
    _r,
    _within,
    _words_match,
    risk_level,
)

PEOPLE_LIMIT = 50


def _people(users: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    return {u.get("id"): u for u in users}


def _active(user: dict[str, Any] | None, include_archived: bool) -> bool:
    return bool(user) and (include_archived or user.get("status") != "archived")


# ---------------------------------------------------------------- phishing per group

async def phishing_by_group(
    kb: Any, console: str, pst_id: int | None = None, test: str | None = None, start_date: str | None = None,
    end_date: str | None = None, groups: Any = None, text: str | None = None, include_archived: bool = False,
) -> dict[str, Any]:
    """one phishing test (or every test in a period) per group: delivered, failed, reported, and the rates"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    tests = await kb.list_phishing_security_tests(console)
    if pst_id is not None:
        tests = [t for t in tests if t.get("pst_id") == pst_id]
    elif test and str(test).strip():
        tests = [t for t in tests if _words_match(t.get("name"), str(test).strip())]
    if start_date or end_date:
        tests = [t for t in tests if _within(t.get("started_at"), start_date, end_date)]
    tests = sorted(tests, key=lambda t: str(t.get("started_at") or ""), reverse=True)
    if not (pst_id is not None or test or start_date or end_date):
        tests = tests[:1]  # nothing named: the latest test
    if not tests:
        return {"console": console, "error": True, "message": "No phishing test matches; name it, give its id or a period."}
    left_out = max(0, len(tests) - MAX_TESTS)
    tests = tests[:MAX_TESTS]

    all_groups, resolved, unknown = await _named_groups(kb, console, groups, text)
    people = _people(await kb.list_users(console))
    # (test, person) pairs: one person in two tests counts twice, as KnowBe4's own rates do
    pairs, archived = [], 0
    for t in tests:
        for r in await kb.list_pst_recipients(console, t.get("pst_id")):
            if not r.get("delivered_at"):
                continue
            uid = (r.get("user") or {}).get("id")
            if not _active(people.get(uid), include_archived):
                archived += 1
                continue
            pairs.append((uid, r))
    member_of = {uid: set(u.get("groups") or []) for uid, u in people.items()}
    if not resolved:
        # every group that received the test, largest first
        seen = Counter(g for uid, _ in pairs for g in member_of.get(uid, set()))
        by_id = {g.get("id"): g for g in all_groups}
        resolved = [by_id[gid] for gid, _ in seen.most_common() if gid in by_id]

    def tally(rows: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
        failed = sum(1 for _, r in rows if _failures(r))
        reported = sum(1 for _, r in rows if r.get("reported_at"))
        return {"delivered": len(rows), "failed": failed, "clicked": sum(1 for _, r in rows if r.get("clicked_at")),
                "entered_data": sum(1 for _, r in rows if r.get("data_entered_at")),
                "opened_attachment": sum(1 for _, r in rows if r.get("attachment_opened_at")), "reported": reported,
                "failure_percent": _pct(failed, len(rows)), "report_percent": _pct(reported, len(rows))}

    rows, missing = [], []
    for g in resolved:
        mine = [(uid, r) for uid, r in pairs if g.get("id") in member_of.get(uid, set())]
        if not mine:
            missing.append(g.get("name"))
            continue
        rows.append({"group": g.get("name"), **tally(mine)})
    totals = tally(pairs)
    # KnowBe4's own smart groups (Real-Time Coaching "RTC_..." groups) are not in the group list: no row, but counted
    listed = {g.get("id") for g in all_groups}
    in_system_groups = sum(1 for uid, _ in pairs if member_of.get(uid, set()) - listed)
    what = f"\"{tests[0].get('name')}\" ({_date(tests[0].get('started_at'))})" if len(tests) == 1 else \
        f"{len(tests)} phishing tests from {_date(tests[-1].get('started_at'))} to {_date(tests[0].get('started_at'))}"
    return {
        "console": console,
        "tests": [{"pst_id": t.get("pst_id"), "name": t.get("name"), "started_at": _date(t.get("started_at"))} for t in tests],
        "headline": (f"Phishing test {what}: {totals['delivered']} emails delivered in {len(rows)} groups; {totals['failed']} failed "
                     f"({totals['failure_percent']}%) and {totals['reported']} reported ({totals['report_percent']}%)."
                     + (f" {archived} emails to archived people are not counted." if archived else "")
                     + (f" Only the newest {MAX_TESTS} tests are used; {left_out} older ones are left out." if left_out else "")),
        "groups": rows,
        "totals": totals,
        "groups_not_in_these_tests": missing,
        "unknown_groups": unknown,
        "archived_not_counted": archived,
        "emails_to_people_in_unlisted_system_groups": in_system_groups,
        "rule": "failed = clicked, entered data, opened an attachment, enabled macros, replied or scanned the QR code; "
                "each delivered email counts once, so one person in two tests counts twice",
        "note": ("The table with every group is added to the answer automatically: do not list the groups again; name at most "
                 "three that stand out and explain the totals. " + NO_ADVICE),
    }


# ---------------------------------------------------------------- who is behind in a campaign

PEOPLE_STATUSES = {"past_due": "Past Due", "not_started": "Not Started", "in_progress": "In Progress", "completed": "Passed"}
# everyone who has not finished: past due, not started and in progress together ("yang belum selesai")
UNFINISHED = "unfinished"


async def campaign_people_rows(
    kb: Any, console: str, campaign: str | None = None, campaign_date: str | None = None, groups: Any = None,
    status: str = "past_due", text: str | None = None, include_archived: bool = False,
) -> dict[str, Any]:
    """every matching person of the campaign, unlimited: {"rows", "picked", "resolved", "unknown", "status"}, or an error /
    ask-which result to return as it is. the chat tool shows the first rows, the csv export writes them all"""
    status = (status or "past_due").strip().lower().replace(" ", "_")
    allowed = (*PEOPLE_STATUSES, UNFINISHED, "all")
    if status not in allowed:
        return {"console": console, "error": True, "message": f"status must be one of {', '.join(allowed)}."}
    all_groups, resolved, unknown = await _named_groups(kb, console, groups, text)
    chosen = await _pick_campaigns(kb, console, campaign, campaign_date, resolved)
    if "picked" not in chosen:
        return chosen
    picked = chosen["picked"]
    camp_ids = {c.get("campaign_id") for c in picked}
    people = _people(await kb.list_users(console))
    per_user: dict[Any, list[dict[str, Any]]] = {}
    for e in await kb.list_training_enrollments(console, include_campaign_id=True):
        if e.get("campaign_id") in camp_ids:
            per_user.setdefault((e.get("user") or {}).get("id"), []).append(e)
    wanted_ids = {g.get("id") for g in resolved}
    group_name = {g.get("id"): str(g.get("name") or "") for g in all_groups}
    rows = []
    for uid, enrolments in per_user.items():
        user = people.get(uid)
        if not _active(user, include_archived):
            continue
        member_of = list(user.get("groups") or [])
        if wanted_ids and not wanted_ids & set(member_of):
            continue
        worst = max((str(e.get("status") or "") for e in enrolments), key=lambda s: STATUS_RANK.get(s, 1))
        column = STATUS_COLUMN.get(worst, "other")
        if status == UNFINISHED and column == "completed" or status not in ("all", UNFINISHED) and column != status:
            continue
        # only the named groups when some were named (a person in two of them shows both), else every group they are in
        shown = [g for g in member_of if g in wanted_ids] if wanted_ids else member_of
        done = [e for e in enrolments if STATUS_COLUMN.get(str(e.get("status") or "")) == "completed"]
        dates = sorted(d for e in done if (d := _date(e.get("completion_date"))))
        rows.append({"name": _name(user), "email": user.get("email"),
                     "groups": [group_name[g] for g in shown if group_name.get(g)],
                     "status": worst, "modules_completed": len(done), "modules_enrolled": len(enrolments),
                     # the day the last module was finished, only once all are
                     "completed_on": dates[-1] if dates and len(done) == len(enrolments) else None,
                     "archived": user.get("status") == "archived",
                     "modules": [{"module": e.get("module_name"), "status": e.get("status"), "completed": _date(e.get("completion_date")) or None}
                                 for e in enrolments]})
    rows.sort(key=lambda r: (str(r["status"]), r["name"].casefold()))
    return {"rows": rows, "picked": picked, "resolved": resolved, "unknown": unknown, "status": status}


async def campaign_people(
    kb: Any, console: str, campaign: str | None = None, campaign_date: str | None = None, groups: Any = None,
    status: str = "past_due", text: str | None = None, include_archived: bool = False, limit: int = PEOPLE_LIMIT,
) -> dict[str, Any]:
    """the people behind the numbers of one training campaign: who is Past Due, not started, in progress or done"""
    found = await campaign_people_rows(kb, console, campaign, campaign_date, groups, status, text, include_archived)
    if "rows" not in found:
        return found
    rows, picked, resolved, status = found["rows"], found["picked"], found["resolved"], found["status"]
    label = {"all": "enrolled", UNFINISHED: "not finished"}.get(status, PEOPLE_STATUSES.get(status, status))
    names = " + ".join(str(c.get("name") or "").strip() for c in picked)
    in_groups = f" in {', '.join(g.get('name') for g in resolved)}" if resolved else ""
    camp_ids = sorted({c.get("campaign_id") for c in picked})
    return {
        "console": console,
        "campaign": {"campaign_ids": camp_ids, "name": names, "start_date": _date(picked[0].get("start_date"))},
        "status": status,
        "headline": f"{names} ({_date(picked[0].get('start_date'))}): {len(rows)} people{in_groups} are {label}.",
        "people": [{k: v for k, v in r.items() if k != "archived"} for r in rows[: _limit(limit, PEOPLE_LIMIT)]],
        "total": len(rows),
        "shown": min(len(rows), _limit(limit, PEOPLE_LIMIT)),
        "unknown_groups": found["unknown"],
        "rule": "a person's status is their least finished module in this campaign",
        "note": ("The list is added to the answer automatically as a table; summarise it. For every person in a file, "
                 "export_csv with dataset campaign_people. " + NO_ADVICE),
    }


# ---------------------------------------------------------------- a group's members

async def group_members(kb: Any, console: str, group: str | None = None, sort: str = "risk", limit: int = PEOPLE_LIMIT,
                        text: str | None = None) -> dict[str, Any]:
    """who is in a group, with each person's risk score, phish-prone % and late training"""
    all_groups = await kb.list_groups(console, "all")
    found = _find_group(str(group or "").strip(), all_groups) if group else None
    if not found and text:
        # the group named in the question, longest name first ("Group-H10" before "Group-H1")
        lowered = text.casefold()
        found = next((g for g in sorted(all_groups, key=lambda g: -len(str(g.get("name") or "")))
                      if g.get("name") and re.search(rf"(?<![\w-]){re.escape(str(g['name']).casefold())}(?![\w-])", lowered)), None)
    if not found:
        close = [g.get("name") for g in all_groups if group and _words_match(g.get("name"), str(group).split()[0])][:10]
        return {"console": console, "error": True,
                "message": f"No group matches '{group}'." + (f" Similar: {', '.join(close)}." if close else "")}
    members = await kb.list_group_members(console, found.get("id"))
    people = _people(await kb.list_users(console, "active"))
    overdue = Counter((e.get("user") or {}).get("id") for e in await kb.list_training_enrollments(console, exclude_archived_users=True)
                      if e.get("status") == "Past Due")
    rows = []
    for m in members:
        u = people.get(m.get("id"))
        if not u:
            continue  # archived or not active
        score = u.get("current_risk_score")
        rows.append({"name": _name(u), "email": u.get("email"), "risk_score": _r(score), "risk_level": risk_level(score),
                     "phish_prone_percent": _r(u.get("phish_prone_percentage")), "past_due_training": overdue.get(u.get("id"), 0)})
    if sort == "name":
        rows.sort(key=lambda r: r["name"].casefold())
    else:
        rows.sort(key=lambda r: -(r["risk_score"] or 0))
    scores = [r["risk_score"] for r in rows if isinstance(r["risk_score"], (int, float))]
    average = _r(sum(scores) / len(scores)) if scores else None
    late = sum(1 for r in rows if r["past_due_training"])
    phished = sum(1 for r in rows if r["phish_prone_percent"])
    return {
        "console": console,
        "group": found.get("name"),
        "headline": (f"Group {found.get('name')}: {len(rows)} active members, average risk score {average} ({risk_level(average)}); "
                     f"{late} have Past Due training and {phished} have a phish-prone % above 0."),
        "members": rows[: _limit(limit, PEOPLE_LIMIT)],
        "total": len(rows),
        "group_risk_score": _r(found.get("current_risk_score")),
        "sorted_by": "name" if sort == "name" else "risk score, highest first",
        "note": "The list is added to the answer automatically as a table; summarise it. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- one person's training

async def person_training(kb: Any, console: str, user_id: int | None = None, name: str | None = None, limit: int = 30) -> dict[str, Any]:
    """every training enrolment of one person: campaign, module, status and dates"""
    if user_id is None:
        query = str(name or "").strip().casefold()
        if not query:
            return {"console": console, "error": True, "message": "Give user_id or the person's name."}
        users = await kb.list_users(console, "active")
        matches = [u for u in users if query in _name(u).casefold() or query in str(u.get("email") or "").casefold()]
        if not matches:
            return {"console": console, "error": True, "message": f"No active user matches '{name}'."}
        if len(matches) > 1:
            return {"console": console, "ask_user": True, "message": "Several people match; ask which one.",
                    "people": [{"user_id": u.get("id"), "name": _name(u), "email": u.get("email")} for u in matches[:10]]}
        user = matches[0]
    else:
        user = await kb.get_user(console, user_id)
    enrolments = await kb.list_training_enrollments(console, user_id=user.get("id"))
    enrolments.sort(key=lambda e: str(e.get("enrollment_date") or ""), reverse=True)
    statuses = Counter(str(e.get("status") or "unknown") for e in enrolments)
    rows = [{"campaign": e.get("campaign_name"), "module": e.get("module_name"), "status": e.get("status"),
             "enrolled": _date(e.get("enrollment_date")) or None, "completed": _date(e.get("completion_date")) or None,
             # time_spent is in seconds (KnowBe4 does not say; it matches the module lengths)
             "minutes": round(e["time_spent"] / 60, 1) if isinstance(e.get("time_spent"), (int, float)) and e["time_spent"] else None}
            for e in enrolments]
    return {
        "console": console,
        "user_id": user.get("id"),
        "name": _name(user),
        "headline": (f"{_name(user)} has {len(enrolments)} training enrolments: "
                     + ", ".join(f"{n} {s}" for s, n in statuses.most_common()) + "." if enrolments
                     else f"{_name(user)} has no training enrolments."),
        "by_status": dict(statuses),
        "enrolments": rows[: _limit(limit, 30)],
        "order": "newest enrolment first",
        "note": "The list is added to the answer automatically as a table; summarise it. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- who was never tested or trained

async def coverage_gaps(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None, limit: int = PEOPLE_LIMIT) -> dict[str, Any]:
    """active people who got no phishing test, no training, or neither, in a period (KnowBe4's "unphished and untrained")"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    users = await kb.list_users(console, "active")
    tests = sorted((t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), start_date, end_date)),
                   key=lambda t: str(t.get("started_at") or ""), reverse=True)
    left_out = max(0, len(tests) - 3 * MAX_TESTS)
    phished: set[Any] = set()
    for t in tests[: 3 * MAX_TESTS]:
        phished.update((r.get("user") or {}).get("id") for r in await kb.list_pst_recipients(console, t.get("pst_id")) if r.get("delivered_at"))
    trained = {(e.get("user") or {}).get("id") for e in await kb.list_training_enrollments(console, exclude_archived_users=True)
               if _within(e.get("enrollment_date"), start_date, end_date)}
    never_phished = [u for u in users if u.get("id") not in phished]
    never_trained = [u for u in users if u.get("id") not in trained]
    neither = [u for u in never_phished if u.get("id") not in trained]
    period = _period_label(start_date, end_date) or "all time"

    def listed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"name": _name(u), "email": u.get("email"), "joined": _date(u.get("joined_on")) or None}
                for u in sorted(rows, key=lambda u: _name(u).casefold())[: _limit(limit, PEOPLE_LIMIT)]]

    return {
        "console": console,
        "period": period,
        "headline": (f"From {period}, of {len(users)} active users: {len(never_phished)} got no phishing test, {len(never_trained)} "
                     f"were not enrolled in any training, and {len(neither)} got neither."
                     + (f" Only the newest {3 * MAX_TESTS} tests were checked; {left_out} older ones were not." if left_out else "")),
        "active_users": len(users),
        "tests_checked": min(len(tests), 3 * MAX_TESTS),
        "no_phishing_test": len(never_phished),
        "no_training": len(never_trained),
        "neither": len(neither),
        "people_with_neither": listed(neither),
        "people_without_phishing": listed(never_phished),
        "people_without_training": listed(never_trained),
        "note": "The people with neither are added to the answer automatically as a table; summarise the counts. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- two periods side by side

COMPARE_METRICS = ("phishing", "training")


def _previous(start: date, end: date) -> tuple[date, date]:
    """the period just before: a whole year, quarter or month before one that starts on its first day (this quarter so far
    against all of last quarter), otherwise the same number of days"""
    # narrowest first: Q1 against Q4, not against the whole year before
    if start.day == 1 and (end.year, end.month) == (start.year, start.month):
        first = date(start.year - (start.month == 1), (start.month - 2) % 12 + 1, 1)
        return first, start - timedelta(days=1)
    if start.day == 1 and start.month in (1, 4, 7, 10) and end < date(start.year + (start.month == 10), (start.month + 2) % 12 + 1, 1):
        first = date(start.year - (start.month == 1), (start.month - 4) % 12 + 1, 1)
        return first, start - timedelta(days=1)
    if start.month == 1 and start.day == 1 and end.year == start.year:
        return date(start.year - 1, 1, 1), date(start.year - 1, 12, 31)
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


async def compare_periods(
    kb: Any, console: str, metric: str = "phishing", start_date: str | None = None, end_date: str | None = None,
    compare_start: str | None = None, compare_end: str | None = None,
) -> dict[str, Any]:
    """the same numbers for two periods, side by side; without a second period, the one just before"""
    metric = (metric or "phishing").strip().lower()
    if metric not in COMPARE_METRICS:
        return {"console": console, "error": True, "message": "metric must be 'phishing' or 'training'."}
    for a, b in ((start_date, end_date), (compare_start, compare_end)):
        if problem := _bad_period(a, b):
            return {"console": console, "error": True, "message": problem}
    today = date.today()
    end_a = date.fromisoformat(end_date[:10]) if end_date else today
    start_a = date.fromisoformat(start_date[:10]) if start_date else end_a - timedelta(days=89)
    if compare_start or compare_end:
        end_b = date.fromisoformat(compare_end[:10]) if compare_end else start_a - timedelta(days=1)
        start_b = date.fromisoformat(compare_start[:10]) if compare_start else end_b - timedelta(days=(end_a - start_a).days)
    else:
        start_b, end_b = _previous(start_a, end_a)

    async def numbers(start: date, end: date) -> dict[str, Any]:
        s, e = start.isoformat(), end.isoformat()
        if metric == "phishing":
            tests = [t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), s, e)]
            delivered = sum(t.get("delivered_count") or 0 for t in tests)
            # failure events over delivered emails: KnowBe4's phish-prone % for a set of tests
            failed = sum((t.get("phish_prone_percentage") or 0) * (t.get("delivered_count") or 0) for t in tests)
            reported = sum(t.get("reported_count") or 0 for t in tests)
            return {"period": f"{s} to {e}", "tests": len(tests), "delivered": delivered,
                    "phish_prone_percent": _r(100 * failed / delivered) if delivered else None,
                    "reported": reported, "report_percent": _pct(reported, delivered)}
        enrolments = [x for x in await kb.list_training_enrollments(console, exclude_archived_users=True)
                      if _within(x.get("enrollment_date"), s, e)]
        statuses = Counter(str(x.get("status") or "") for x in enrolments)
        done = statuses["Passed"] + statuses["Completed"]
        return {"period": f"{s} to {e}", "enrolments": len(enrolments), "completed": done, "past_due": statuses["Past Due"],
                "completion_percent": _pct(done, len(enrolments)), "past_due_percent": _pct(statuses["Past Due"], len(enrolments))}

    current, earlier = await numbers(start_a, end_a), await numbers(start_b, end_b)
    key = "phish_prone_percent" if metric == "phishing" else "completion_percent"
    change = None
    if isinstance(current.get(key), (int, float)) and isinstance(earlier.get(key), (int, float)):
        change = _r(current[key] - earlier[key])
    better = None if change in (None, 0) else (change < 0 if metric == "phishing" else change > 0)
    label = "phish-prone %" if metric == "phishing" else "training completion %"
    return {
        "console": console,
        "metric": metric,
        "headline": (f"{label.capitalize()}: {current.get(key)} from {current['period']} against {earlier.get(key)} from "
                     f"{earlier['period']}" + (f" ({'+' if change > 0 else ''}{change} points, "
                                               f"{'better' if better else 'worse'})." if change not in (None, 0) else
                                               " (no change)." if change == 0 else " (one period has no data).")),
        "current": current,
        "earlier": earlier,
        "change_points": change,
        "better": better,
        "meaning": "lower phish-prone % is better; higher completion % is better",
        "note": NO_ADVICE,
    }
