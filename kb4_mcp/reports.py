"""Reports across a user field, a manager's team, one group in full, and the organisation with every group side by side.

The counting is the same as in the other tools: a phishing failure is any unsafe action (summaries.FAILURE_EVENTS), the
phish-prone % is failure actions ÷ emails delivered as KnowBe4 defines it, "failed" is emails with at least one failure;
training counts a person once per campaign by their least finished module, as training_by_group does (945, not 944).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from kb4_mcp.lookups import ATTRIBUTES, normalise_attribute
from kb4_mcp.summaries import (
    MAX_TESTS,
    NO_ADVICE,
    RISK_SCALE_NOTE,
    STATUS_COLUMN,
    STATUS_RANK,
    _bad_period,
    _date,
    _failures,
    _find_group,
    _history_stats,
    _limit,
    _median,
    _minutes_to_fail,
    _name,
    _pct,
    _period_label,
    _period_stats,
    _pick_campaigns,
    _r,
    _trend_headline,
    _within,
    _words_match,
    account_risk_overview,
    risk_level,
)

EMPTY = "(kosong)"
SMALL_SAMPLE = 5
ROW_LIMIT = 20
# report tools not offered for these fields: they identify a person, not a team
NOT_GROUPABLE = {"employee_number"}


def _active(user: dict[str, Any] | None, include_archived: bool) -> bool:
    return bool(user) and (include_archived or user.get("status") != "archived")


def _value(user: dict[str, Any], attribute: str) -> str:
    text = str(user.get(attribute) or "").strip()
    return text or EMPTY


def _check_attribute(console: str, attribute: str) -> dict[str, Any] | None:
    if attribute not in ATTRIBUTES or attribute in NOT_GROUPABLE:
        allowed = [a for a in ATTRIBUTES if a not in NOT_GROUPABLE]
        return {"console": console, "error": True, "message": f"attribute must be one of: {', '.join(allowed)}."}
    return None


def _empty_field(console: str, attribute: str, users: list[dict[str, Any]], group_tool: str) -> dict[str, Any] | None:
    """nobody has the field: one "(kosong)" row says nothing, the groups may be what is meant"""
    if users and all(_value(u, attribute) == EMPTY for u in users):
        return {"console": console, "error": True, "attribute": attribute,
                "message": (f"No active user has a {attribute} filled in KnowBe4 ({len(users)} active users), so there is nothing "
                            f"to break down by. If teams are set up as KnowBe4 groups, use {group_tool} instead.")}
    return None


# ---------------------------------------------------------------- shared counting

async def _tests_in_scope(kb: Any, console: str, pst_id: int | None, test: str | None, start: str | None,
                          end: str | None) -> tuple[list[dict[str, Any]], int]:
    """the same choice as phishing_by_group: an id, a name, a period, or else the latest test; newest MAX_TESTS kept"""
    tests = await kb.list_phishing_security_tests(console)
    if pst_id is not None:
        tests = [t for t in tests if t.get("pst_id") == pst_id]
    elif test and str(test).strip():
        tests = [t for t in tests if _words_match(t.get("name"), str(test).strip())]
    if start or end:
        tests = [t for t in tests if _within(t.get("started_at"), start, end)]
    tests = sorted(tests, key=lambda t: str(t.get("started_at") or ""), reverse=True)
    if not (pst_id is not None or test or start or end):
        tests = tests[:1]
    return tests[:MAX_TESTS], max(0, len(tests) - MAX_TESTS)


async def _delivered(kb: Any, console: str, tests: list[dict[str, Any]], people: dict[Any, dict[str, Any]],
                     include_archived: bool) -> tuple[list[tuple[Any, dict[str, Any]]], int]:
    """(person id, recipient) for every delivered email; one person in two tests counts twice, as in KnowBe4's rates"""
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
    return pairs, archived


def _phish_tally(rows: list[tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
    events = sum(len(_failures(r)) for _, r in rows)
    failed = sum(1 for _, r in rows if _failures(r))
    reported = sum(1 for _, r in rows if r.get("reported_at"))
    return {"people": len({uid for uid, _ in rows}), "delivered": len(rows), "failure_actions": events,
            "phish_prone_percent": _pct(events, len(rows)), "failed": failed, "failed_percent": _pct(failed, len(rows)),
            "reported": reported, "report_percent": _pct(reported, len(rows))}


def _tests_label(tests: list[dict[str, Any]], left_out: int) -> str:
    if not tests:
        return "no phishing test"
    what = (f"phishing test \"{tests[0].get('name')}\" ({_date(tests[0].get('started_at'))})" if len(tests) == 1 else
            f"{len(tests)} phishing tests from {_date(tests[-1].get('started_at'))} to {_date(tests[0].get('started_at'))}")
    return what + (f" (newest {MAX_TESTS}; {left_out} older ones left out)" if left_out else "")


async def _enrolments_in_scope(kb: Any, console: str, campaign: str | None, campaign_date: str | None, start: str | None,
                               end: str | None) -> dict[str, Any]:
    """{"enrolments", "label"} for one campaign (a day's campaigns) or every enrolment of a period; or an error / ask"""
    if campaign or campaign_date:
        chosen = await _pick_campaigns(kb, console, campaign, campaign_date, [])
        if "picked" not in chosen:
            return chosen
        ids = {c.get("campaign_id") for c in chosen["picked"]}
        enrolments = [e for e in await kb.list_training_enrollments(console, include_campaign_id=True) if e.get("campaign_id") in ids]
        names = " + ".join(dict.fromkeys(str(c.get("name") or "").strip() for c in chosen["picked"]))
        return {"enrolments": enrolments, "label": f"training campaign {names} ({_date(chosen['picked'][0].get('start_date'))})"}
    enrolments = [e for e in await kb.list_training_enrollments(console, include_campaign_id=True)
                  if _within(e.get("enrollment_date"), start, end)]
    period = _period_label(start, end)
    return {"enrolments": enrolments, "label": f"training enrolled {period}" if period else "all training enrolments"}


def _training_pairs(enrolments: list[dict[str, Any]], people: dict[Any, dict[str, Any]],
                    include_archived: bool) -> dict[tuple[Any, Any], list[str]]:
    pairs: dict[tuple[Any, Any], list[str]] = {}
    for e in enrolments:
        uid = (e.get("user") or {}).get("id")
        if _active(people.get(uid), include_archived):
            pairs.setdefault((uid, e.get("campaign_id")), []).append(str(e.get("status") or ""))
    return pairs


def _training_tally(units: list[list[str]]) -> dict[str, Any]:
    counts = Counter(STATUS_COLUMN.get(max(s, key=lambda x: STATUS_RANK.get(x, 1)), "other") for s in units if s)
    total = sum(counts.values())
    return {"total": total, "completed": counts["completed"], "in_progress": counts["in_progress"],
            "not_started": counts["not_started"], "past_due": counts["past_due"],
            "percent_complete": _pct(counts["completed"], total), "percent_past_due": _pct(counts["past_due"], total)}


def _sorted_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """highest first, "(kosong)" last"""
    return sorted(rows, key=lambda r: (r["value"] == EMPTY, -(r.get(key) if isinstance(r.get(key), (int, float)) else -1),
                                       str(r["value"]).casefold()))


# ---------------------------------------------------------------- per user field

async def phishing_by_attribute(kb: Any, console: str, attribute: str = "department", pst_id: int | None = None,
                                test: str | None = None, start_date: str | None = None, end_date: str | None = None,
                                include_archived: bool = False, limit: int = ROW_LIMIT) -> dict[str, Any]:
    """phishing results per department, location, manager, job title, division, organisation or custom field"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    attribute = normalise_attribute(attribute)
    if bad := _check_attribute(console, attribute):
        return bad
    users = await kb.list_users(console)
    if empty := _empty_field(console, attribute, [u for u in users if u.get("status") == "active"], "phishing_by_group"):
        return empty
    tests, left_out = await _tests_in_scope(kb, console, pst_id, test, start_date, end_date)
    if not tests:
        return {"console": console, "error": True, "message": "No phishing test matches; name it, give its id or a period."}
    people = {u.get("id"): u for u in users}
    pairs, archived = await _delivered(kb, console, tests, people, include_archived)
    buckets: dict[str, list[tuple[Any, dict[str, Any]]]] = {}
    for uid, r in pairs:
        buckets.setdefault(_value(people[uid], attribute), []).append((uid, r))
    rows = _sorted_rows([{"value": v, **_phish_tally(b), "small_sample": len({u for u, _ in b}) < SMALL_SAMPLE}
                         for v, b in buckets.items()], "phish_prone_percent")
    totals = _phish_tally(pairs)
    shown = rows[: _limit(limit, ROW_LIMIT)]
    return {
        "console": console,
        "attribute": attribute,
        "tests": [{"pst_id": t.get("pst_id"), "name": t.get("name"), "started_at": _date(t.get("started_at"))} for t in tests],
        "headline": (f"{_tests_label(tests, left_out)} per {attribute}: {totals['delivered']} emails delivered to "
                     f"{totals['people']} people in {len(rows)} {attribute} values; phish-prone {totals['phish_prone_percent']}% "
                     f"({totals['failure_actions']} failure actions), {totals['failed']} emails failed "
                     f"({totals['failed_percent']}%), {totals['reported']} reported ({totals['report_percent']}%)."
                     + (f" {archived} emails to archived people are not counted." if archived else "")),
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "totals": totals,
        "archived_not_counted": archived,
        "definitions": ["phish_prone_percent = failure actions ÷ emails delivered (one email can fail more than once)",
                        "failed_percent = emails with at least one failure ÷ emails delivered",
                        f"small_sample = fewer than {SMALL_SAMPLE} people", f"{EMPTY} = people with no {attribute} in KnowBe4"],
        "note": "The table is added to the answer automatically: do not list the rows again; explain the totals. " + NO_ADVICE,
    }


async def training_by_attribute(kb: Any, console: str, attribute: str = "department", campaign: str | None = None,
                                campaign_date: str | None = None, start_date: str | None = None, end_date: str | None = None,
                                include_archived: bool = False, limit: int = ROW_LIMIT) -> dict[str, Any]:
    """training status per department, location, manager, job title, division, organisation or custom field"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    attribute = normalise_attribute(attribute)
    if bad := _check_attribute(console, attribute):
        return bad
    users = await kb.list_users(console)
    if empty := _empty_field(console, attribute, [u for u in users if u.get("status") == "active"], "training_by_group"):
        return empty
    scope = await _enrolments_in_scope(kb, console, campaign, campaign_date, None if campaign or campaign_date else start_date,
                                       None if campaign or campaign_date else end_date)
    if "enrolments" not in scope:
        return scope
    people = {u.get("id"): u for u in users}
    pairs = _training_pairs(scope["enrolments"], people, include_archived)
    buckets: dict[str, list[list[str]]] = {}
    for (uid, _), statuses in pairs.items():
        buckets.setdefault(_value(people[uid], attribute), []).append(statuses)
    rows = _sorted_rows([{"value": v, **_training_tally(b), "small_sample": len(b) < SMALL_SAMPLE} for v, b in buckets.items()],
                        "percent_past_due")
    totals = _training_tally(list(pairs.values()))
    shown = rows[: _limit(limit, ROW_LIMIT)]
    return {
        "console": console,
        "attribute": attribute,
        "headline": (f"{scope['label']} per {attribute}: {totals['total']} people (once per campaign) in {len(rows)} {attribute} "
                     f"values; {totals['completed']} completed ({totals['percent_complete']}%), {totals['in_progress']} in "
                     f"progress, {totals['not_started']} not started, {totals['past_due']} Past Due ({totals['percent_past_due']}%)."
                     if totals["total"] else f"No training enrolments for {scope['label']}."),
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "totals": totals,
        "rule": "a person counts once per campaign, by their least finished module (one Past Due module = Past Due)",
        "definitions": [f"small_sample = fewer than {SMALL_SAMPLE} people", f"{EMPTY} = people with no {attribute} in KnowBe4"],
        "note": "The table is added to the answer automatically: do not list the rows again; explain the totals. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- per manager

async def manager_report(kb: Any, console: str, manager: str | None = None, start_date: str | None = None,
                         end_date: str | None = None, limit: int = ROW_LIMIT) -> dict[str, Any]:
    """each manager's team: who has Past Due training (any time) and who failed phishing in the period"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    users = await kb.list_users(console, "active")
    if empty := _empty_field(console, "manager_name", users, "group_members"):
        return empty
    teams: dict[str, list[dict[str, Any]]] = {}
    for u in users:
        if str(u.get("manager_name") or "").strip():
            teams.setdefault(str(u["manager_name"]).strip(), []).append(u)
    if manager and manager.strip():
        wanted = manager.strip()
        exact = [m for m in teams if m.casefold() == wanted.casefold()]
        found = exact or [m for m in teams if _words_match(m, wanted) or wanted.casefold() in m.casefold()]
        if not found:
            return {"console": console, "error": True,
                    "message": f"No manager named '{wanted}'. Managers: {', '.join(sorted(teams)[:15])}."}
        if len(found) > 1:
            return {"console": console, "ask_user": True, "message": "Several managers match; ask which one.",
                    "managers": sorted(found)[:10]}
        teams = {found[0]: teams[found[0]]}
    in_teams = {u.get("id") for team in teams.values() for u in team}
    overdue = Counter((e.get("user") or {}).get("id") for e in await kb.list_training_enrollments(console)
                      if e.get("status") == "Past Due" and (e.get("user") or {}).get("id") in in_teams)
    # without a period: every test (newest MAX_TESTS), not only the latest one
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date or ("2000-01-01" if not end_date else None), end_date)
    people = {u.get("id"): u for u in users}
    pairs, _ = await _delivered(kb, console, tests, people, False)
    failed = Counter(uid for uid, r in pairs if uid in in_teams and _failures(r))
    period = f"phishing in {_tests_label(tests, left_out)}"
    if len(teams) == 1:
        name, team = next(iter(teams.items()))
        rows = sorted(({"name": _name(u), "email": u.get("email"), "job_title": u.get("job_title"),
                        "past_due_modules": overdue[u.get("id")], "failed_phishing_emails": failed[u.get("id")]} for u in team),
                      key=lambda r: (-(r["past_due_modules"] + r["failed_phishing_emails"]), r["name"].casefold()))
        late = sum(1 for r in rows if r["past_due_modules"])
        fell = sum(1 for r in rows if r["failed_phishing_emails"])
        shown = rows[: _limit(limit, ROW_LIMIT)]
        return {
            "console": console,
            "mode": "team",
            "manager": name,
            "headline": (f"{name}'s team: {len(team)} active people; {late} have Past Due training and {fell} failed at least one "
                         f"phishing email ({period})."),
            "rows": shown,
            "total_rows": len(rows),
            "truncated": len(rows) > len(shown),
            "note": "The table is added to the answer automatically: do not list the people again. " + NO_ADVICE,
        }
    rows = []
    for name, team in teams.items():
        ids = [u.get("id") for u in team]
        rows.append({"manager": name, "team": len(team), "people_with_past_due": sum(1 for i in ids if overdue[i]),
                     "past_due_modules": sum(overdue[i] for i in ids), "people_who_failed_phishing": sum(1 for i in ids if failed[i]),
                     "failed_phishing_emails": sum(failed[i] for i in ids)})
    rows.sort(key=lambda r: (-(r["people_with_past_due"] + r["people_who_failed_phishing"]), -r["team"], r["manager"].casefold()))
    shown = rows[: _limit(limit, ROW_LIMIT)]
    without = len(users) - len(in_teams)
    return {
        "console": console,
        "mode": "managers",
        "headline": (f"{len(teams)} managers with {len(in_teams)} active people; {sum(r['people_with_past_due'] for r in rows)} "
                     f"have Past Due training and {sum(r['people_who_failed_phishing'] for r in rows)} failed at least one phishing "
                     f"email ({period}). {without} active people have no manager in KnowBe4."),
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "rule": "Past Due training counts every enrolment still Past Due, of any date; phishing counts the tests in the period",
        "note": "The table is added to the answer automatically: do not list the managers again. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- one group in full

async def group_report(kb: Any, console: str, group: str, start_date: str | None = None, end_date: str | None = None,
                       include_archived: bool = False) -> dict[str, Any]:
    """one group: risk now and its trend, phishing and training in the period, the riskiest members and repeat clickers"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    all_groups = await kb.list_groups(console, "all")
    wanted = str(group or "").strip()
    if not wanted:
        return {"console": console, "error": True, "message": "Name the group (find_group lists them)."}
    g = _find_group(wanted, all_groups)
    if g is None:
        close = [x for x in all_groups if wanted.casefold() in str(x.get("name") or "").casefold() or _words_match(x.get("name"), wanted)]
        if len(close) > 1:
            return {"console": console, "ask_user": True, "message": "Several groups match; ask which one.",
                    "groups": [x.get("name") for x in close[:10]]}
        return {"console": console, "error": True, "message": f"No group matches '{wanted}' (find_group lists them)."}
    users = await kb.list_users(console)
    people = {u.get("id"): u for u in users}
    members = [u for u in users if g.get("id") in (u.get("groups") or []) and _active(u, include_archived)]
    ids = {u.get("id") for u in members}
    full = bool(start_date or end_date)
    history = await kb.get_group_risk_history(console, g.get("id"), full)
    history = history if isinstance(history, list) else []
    trend = _history_stats(history, current=g.get("current_risk_score"))
    period_risk = _period_stats(history, start_date, end_date, g.get("current_risk_score"))
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date or ("2000-01-01" if not end_date else None), end_date)
    pairs, _ = await _delivered(kb, console, tests, people, include_archived)
    mine = [(uid, r) for uid, r in pairs if uid in ids]
    phishing = _phish_tally(mine)
    per_person = Counter(uid for uid, r in mine if _failures(r))
    repeat = sorted(({"name": _name(people[uid]), "failed_phishing_emails": n} for uid, n in per_person.items() if n >= 2),
                    key=lambda r: (-r["failed_phishing_emails"], r["name"].casefold()))
    enrolments = [e for e in await kb.list_training_enrollments(console, include_campaign_id=True)
                  if (e.get("user") or {}).get("id") in ids and _within(e.get("enrollment_date"), start_date, end_date)]
    training = _training_tally(list(_training_pairs(enrolments, people, include_archived).values()))
    riskiest = sorted((u for u in members if isinstance(u.get("current_risk_score"), (int, float))),
                      key=lambda u: -u["current_risk_score"])[:5]
    period = _period_label(start_date, end_date)
    return {
        "console": console,
        "group": {"id": g.get("id"), "name": g.get("name"), "status": g.get("status"), "active_members": len(members),
                  "risk_score": _r(g.get("current_risk_score")), "risk_level": risk_level(g.get("current_risk_score"))},
        "headline": (f"Group {g.get('name')}: {len(members)} active members, risk score {_r(g.get('current_risk_score'))} "
                     f"({risk_level(g.get('current_risk_score'))}). Phishing ({_tests_label(tests, left_out)}): "
                     f"{phishing['delivered']} emails delivered, phish-prone {phishing['phish_prone_percent']}%, "
                     f"{phishing['failed']} failed ({phishing['failed_percent']}%), {phishing['reported']} reported "
                     f"({phishing['report_percent']}%). Training{' enrolled ' + period if period else ''}: {training['total']} people "
                     f"(once per campaign), {training['completed']} completed ({training['percent_complete']}%), "
                     f"{training['past_due']} Past Due."),
        "risk_trend": {"headline": _trend_headline(f"Group {g.get('name')}", trend), **({"period": period_risk} if period_risk else {})},
        "phishing": phishing,
        "training": training,
        "rows": [{"name": _name(u), "job_title": u.get("job_title"), "risk_score": _r(u.get("current_risk_score")),
                  "risk_level": risk_level(u.get("current_risk_score"))} for u in riskiest],
        "repeat_clickers": repeat[:10],
        "scale": RISK_SCALE_NOTE,
        "definitions": ["phish_prone_percent = failure actions ÷ emails delivered", "repeat clicker = 2 or more failed emails"],
        "note": ("The five riskiest members are added as a table automatically. Start from the headline; give the risk trend, "
                 "phishing and training, and name the repeat clickers if any. " + NO_ADVICE),
    }


# ---------------------------------------------------------------- the organisation, every group side by side

async def organisation_summary(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None,
                               limit: int = 30) -> dict[str, Any]:
    """risk, phishing and training for the organisation, then every group with members side by side"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    overview = await account_risk_overview(kb, console, start_date, end_date)
    users = await kb.list_users(console)
    people = {u.get("id"): u for u in users}
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date or ("2000-01-01" if not end_date else None), end_date)
    pairs, _ = await _delivered(kb, console, tests, people, False)
    enrolments = [e for e in await kb.list_training_enrollments(console, include_campaign_id=True)
                  if _within(e.get("enrollment_date"), start_date, end_date)]
    training_pairs = _training_pairs(enrolments, people, False)
    phishing, training = _phish_tally(pairs), _training_tally(list(training_pairs.values()))
    groups = [g for g in await kb.list_groups(console, "active") if g.get("member_count")]
    member_of = {uid: set(u.get("groups") or []) for uid, u in people.items() if _active(u, False)}
    rows = []
    for g in groups:
        gid = g.get("id")
        ph = _phish_tally([(uid, r) for uid, r in pairs if gid in member_of.get(uid, set())])
        tr = _training_tally([s for (uid, _), s in training_pairs.items() if gid in member_of.get(uid, set())])
        rows.append({"group": g.get("name"), "people": sum(1 for s in member_of.values() if gid in s),
                     "risk_score": _r(g.get("current_risk_score")), "risk_level": risk_level(g.get("current_risk_score")),
                     "phish_prone_percent": ph["phish_prone_percent"], "report_percent": ph["report_percent"],
                     "percent_complete": tr["percent_complete"], "past_due": tr["past_due"],
                     "small_sample": sum(1 for s in member_of.values() if gid in s) < SMALL_SAMPLE})
    rows.sort(key=lambda r: (-(r["risk_score"] if isinstance(r["risk_score"], (int, float)) else -1), str(r["group"]).casefold()))
    shown = rows[: _limit(limit, 30)]
    current = overview.get("current") or {}
    period = _period_label(start_date, end_date)
    return {
        "console": console,
        "headline": (f"Organisation risk score {current.get('score')} ({current.get('level')}). Phishing "
                     f"({_tests_label(tests, left_out)}): {phishing['delivered']} emails delivered, phish-prone "
                     f"{phishing['phish_prone_percent']}%, {phishing['reported']} reported ({phishing['report_percent']}%). "
                     f"Training{' enrolled ' + period if period else ''}: {training['total']} people (once per campaign), "
                     f"{training['percent_complete']}% completed, {training['past_due']} Past Due. {len(rows)} groups with members."),
        "risk": {"headline": overview.get("headline"), "current": current},
        "phishing": phishing,
        "training": training,
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "scale": RISK_SCALE_NOTE,
        "definitions": ["group risk_score = KnowBe4's own group score", "phish_prone_percent = failure actions ÷ emails delivered",
                        "a person in two groups counts in both rows"],
        "note": "Every group is added as a table automatically: do not list the groups again; explain the totals. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- phishing over time, per template, reporting, devices

INTERVALS = ("month", "quarter")


def _bucket(day: str, interval: str) -> str:
    year, month = day[:4], int(day[5:7])
    return f"{year}-Q{(month - 1) // 3 + 1}" if interval == "quarter" else day[:7]


async def _people_filter(kb: Any, console: str, group: str | None, attribute: str | None, value: str | None,
                         users: list[dict[str, Any]]) -> dict[str, Any]:
    """{"ids", "label"} for a group or a user-field value, {} for everyone, or an error / ask to return as it is"""
    if group and str(group).strip():
        g = _find_group(str(group).strip(), await kb.list_groups(console, "all"))
        if g is None:
            return {"console": console, "error": True, "message": f"No group matches '{group}' (find_group lists them)."}
        return {"ids": {u.get("id") for u in users if g.get("id") in (u.get("groups") or [])}, "label": f"group {g.get('name')}"}
    if attribute and str(attribute).strip():
        attribute = normalise_attribute(attribute)
        if bad := _check_attribute(console, attribute):
            return bad
        if not (value and str(value).strip()):
            return {"console": console, "error": True, "message": f"Give the {attribute} value as well (list_dimension_values lists them)."}
        wanted = str(value).strip().casefold()
        ids = {u.get("id") for u in users if str(u.get(attribute) or "").strip().casefold() == wanted}
        if not ids:
            return {"console": console, "error": True, "message": f"No user has {attribute} '{value}' (list_dimension_values lists them)."}
        return {"ids": ids, "label": f"{attribute} {value}"}
    return {}


async def phishing_trend(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None, interval: str = "month",
                         group: str | None = None, attribute: str | None = None, value: str | None = None) -> dict[str, Any]:
    """phish-prone % and report rate per month or quarter; the whole organisation from KnowBe4's own test counts, a group or a
    user-field value from the recipients of the newest MAX_TESTS tests"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    interval = (interval or "month").strip().lower()
    if interval not in INTERVALS:
        return {"console": console, "error": True, "message": "interval must be month or quarter."}
    tests = sorted((t for t in await kb.list_phishing_security_tests(console) if _within(t.get("started_at"), start_date, end_date)),
                   key=lambda t: str(t.get("started_at") or ""))
    users = await kb.list_users(console)
    who = await _people_filter(kb, console, group, attribute, value, users)
    if "error" in who:
        return who
    rows: dict[str, dict[str, Any]] = {}
    left_out = 0
    if not who:
        for t in tests:
            delivered = t.get("delivered_count") if isinstance(t.get("delivered_count"), int) else 0
            ppp = t.get("phish_prone_percentage") if isinstance(t.get("phish_prone_percentage"), (int, float)) else 0
            r = rows.setdefault(_bucket(_date(t.get("started_at")), interval), {"tests": 0, "delivered": 0, "failure_actions": 0.0, "reported": 0})
            r["tests"] += 1
            r["delivered"] += delivered
            # the api's fraction is failure actions / delivered for that test
            r["failure_actions"] += ppp * delivered
            r["reported"] += t.get("reported_count") if isinstance(t.get("reported_count"), int) else 0
        source = "KnowBe4's own counts per test"
    else:
        left_out = max(0, len(tests) - MAX_TESTS)
        tests = tests[-MAX_TESTS:]
        people = {u.get("id"): u for u in users}
        for t in tests:
            mine = [r for r in await kb.list_pst_recipients(console, t.get("pst_id"))
                    if r.get("delivered_at") and (r.get("user") or {}).get("id") in who["ids"]
                    and _active(people.get((r.get("user") or {}).get("id")), False)]
            if not mine:
                continue
            r = rows.setdefault(_bucket(_date(t.get("started_at")), interval), {"tests": 0, "delivered": 0, "failure_actions": 0.0, "reported": 0})
            r["tests"] += 1
            r["delivered"] += len(mine)
            r["failure_actions"] += sum(len(_failures(x)) for x in mine)
            r["reported"] += sum(1 for x in mine if x.get("reported_at"))
        source = f"recipients in {who['label']}" + (f" (newest {MAX_TESTS} tests; {left_out} older left out)" if left_out else "")
    points = [{"period": k, "tests": v["tests"], "delivered": v["delivered"],
               "phish_prone_percent": _pct(round(v["failure_actions"]), v["delivered"]),
               "report_percent": _pct(v["reported"], v["delivered"])} for k, v in sorted(rows.items())]
    scored = [p for p in points if p["phish_prone_percent"] is not None]
    period = _period_label(start_date, end_date) or "all data"
    if len(scored) >= 2:
        first, last = scored[0], scored[-1]
        change = round(last["phish_prone_percent"] - first["phish_prone_percent"], 2)
        how = "fell" if change < 0 else "rose" if change > 0 else "stayed the same"
        trend = (f"phish-prone {how} from {first['phish_prone_percent']}% ({first['period']}) to {last['phish_prone_percent']}% "
                 f"({last['period']})" + (f", {abs(change)} points" if change else ""))
    elif scored:
        trend = f"only one {interval} with tests: phish-prone {scored[0]['phish_prone_percent']}% ({scored[0]['period']})"
    else:
        trend = "no phishing email was delivered"
    target = who.get("label", "the organisation")
    return {
        "console": console,
        "headline": f"Phishing per {interval} for {target}, {period}: {trend}.",
        "interval": interval,
        "rows": points,
        "total_rows": len(points),
        "source": source,
        "definitions": ["phish_prone_percent = failure actions ÷ emails delivered", "report_percent = emails reported ÷ delivered",
                        "months without a test are left out"],
        "note": "The table is added to the answer automatically. Start from the headline. " + NO_ADVICE,
    }


async def phishing_by_template(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None,
                               limit: int = 10) -> dict[str, Any]:
    """templates (and difficulty levels) ranked by phish-prone %, from the recipients of the newest MAX_TESTS tests"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date or ("2000-01-01" if not end_date else None), end_date)
    if not tests:
        return {"console": console, "error": True, "message": "No phishing test in this period."}
    people = {u.get("id"): u for u in await kb.list_users(console)}
    pairs, _ = await _delivered(kb, console, tests, people, False)
    by_template: dict[Any, list[tuple[Any, dict[str, Any]]]] = {}
    info: dict[Any, dict[str, Any]] = {}
    for uid, r in pairs:
        t = r.get("template") if isinstance(r.get("template"), dict) else {}
        key = t.get("id") or t.get("name") or "?"
        by_template.setdefault(key, []).append((uid, r))
        info.setdefault(key, t)
    rows = []
    for key, items in by_template.items():
        t = info[key]
        tally = _phish_tally(items)
        rows.append({"template": t.get("name") or "(unknown template)", "type": t.get("type"), "difficulty": t.get("difficulty"),
                     "sent": tally["delivered"], "people": tally["people"], "phish_prone_percent": tally["phish_prone_percent"],
                     "failed_percent": tally["failed_percent"], "report_percent": tally["report_percent"],
                     "small_sample": tally["people"] < SMALL_SAMPLE})
    # a template sent to one person at 100% is not "the most fooling": small samples go after the rest (still listed, marked)
    rows.sort(key=lambda r: (r["small_sample"], -(r["phish_prone_percent"] or 0), -r["sent"], str(r["template"]).casefold()))
    levels: dict[Any, list[tuple[Any, dict[str, Any]]]] = {}
    for key, items in by_template.items():
        levels.setdefault(info[key].get("difficulty"), []).extend(items)
    difficulty = [{"difficulty": d, "templates": sum(1 for k in by_template if info[k].get("difficulty") == d),
                   **{k: v for k, v in _phish_tally(items).items() if k in ("delivered", "phish_prone_percent", "report_percent")}}
                  for d, items in sorted(levels.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))]
    shown = rows[: _limit(limit)]
    return {
        "console": console,
        "headline": (f"{len(rows)} templates in {_tests_label(tests, left_out)}; most fooled: {rows[0]['template']} "
                     f"(phish-prone {rows[0]['phish_prone_percent']}%, {rows[0]['sent']} sent)." if rows else
                     f"No delivered emails in {_tests_label(tests, left_out)}."),
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "by_difficulty": difficulty,
        "definitions": ["phish_prone_percent = failure actions ÷ emails sent with that template",
                        "difficulty = KnowBe4's template difficulty (1 easiest to 5 hardest)", f"small_sample = fewer than {SMALL_SAMPLE} people"],
        "note": "The table is added to the answer automatically. Mention the difficulty levels from by_difficulty. " + NO_ADVICE,
    }


def _minutes_between(start: Any, end: Any) -> float | None:
    try:
        return max(0.0, (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds() / 60)
    except (TypeError, ValueError):
        return None


async def reporting_behaviour(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None,
                              group: str | None = None, limit: int = ROW_LIMIT) -> dict[str, Any]:
    """how people report simulated phishing: report rate, time to report, and who reports, fails or never reports"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    users = await kb.list_users(console)
    who = await _people_filter(kb, console, group, None, None, users)
    if "error" in who:
        return who
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date or ("2000-01-01" if not end_date else None), end_date)
    if not tests:
        return {"console": console, "error": True, "message": "No phishing test in this period."}
    people = {u.get("id"): u for u in users}
    pairs, _ = await _delivered(kb, console, tests, people, False)
    if who:
        pairs = [(uid, r) for uid, r in pairs if uid in who["ids"]]
    per: dict[Any, dict[str, int]] = {}
    minutes = []
    for uid, r in pairs:
        p = per.setdefault(uid, {"received": 0, "reported": 0, "failed": 0, "failed_and_reported": 0})
        p["received"] += 1
        failed, reported = bool(_failures(r)), bool(r.get("reported_at"))
        p["failed"] += failed
        p["reported"] += reported
        p["failed_and_reported"] += failed and reported
        if reported and (m := _minutes_between(r.get("delivered_at"), r.get("reported_at"))) is not None:
            minutes.append(m)
    reported = sum(p["reported"] for p in per.values())
    never = sorted((uid for uid, p in per.items() if not p["reported"]), key=lambda u: (-per[u]["received"], _name(people[u]).casefold()))
    counts = {
        "people": len(per),
        "reported_and_never_failed": sum(1 for p in per.values() if p["reported"] and not p["failed"]),
        "failed_and_reported": sum(1 for p in per.values() if p["failed_and_reported"]),
        "failed_never_reported": sum(1 for p in per.values() if p["failed"] and not p["reported"]),
        "never_reported": len(never),
    }
    median = _median(minutes)
    rows = [{"name": _name(people[u]), "received": per[u]["received"], "failed": per[u]["failed"]} for u in never]
    shown = rows[: _limit(limit, ROW_LIMIT)]
    target = who.get("label", "everyone")
    return {
        "console": console,
        "headline": (f"Reporting in {_tests_label(tests, left_out)} ({target}): {reported} of {len(pairs)} emails reported "
                     f"({_pct(reported, len(pairs))}%)"
                     + (f", median {round(median)} minutes from delivery to report" if median is not None else "")
                     + f"; {counts['never_reported']} of {counts['people']} people never reported one." if pairs else
                     f"No emails delivered in {_tests_label(tests, left_out)} ({target})."),
        "report_percent": _pct(reported, len(pairs)),
        "median_minutes_to_report": _r(median),
        "counts": counts,
        "rows": shown,
        "total_rows": len(rows),
        "truncated": len(rows) > len(shown),
        "definitions": ["report_percent = emails reported ÷ emails delivered",
                        "failed_and_reported = people who failed an email and also reported it",
                        "rows = people who never reported, most emails received first"],
        "note": "The people who never reported are added as a table automatically. Start from the headline. " + NO_ADVICE,
    }


async def phishing_click_details(kb: Any, console: str, pst_id: int | None = None, test: str | None = None,
                                 start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """failures by operating system and browser, and how fast people failed; no ip addresses or locations"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    tests, left_out = await _tests_in_scope(kb, console, pst_id, test, start_date, end_date)
    if not tests:
        return {"console": console, "error": True, "message": "No phishing test matches; name it, give its id or a period."}
    people = {u.get("id"): u for u in await kb.list_users(console)}
    pairs, _ = await _delivered(kb, console, tests, people, False)
    failed = [r for _, r in pairs if _failures(r)]
    systems = Counter(str(r.get("os") or "").strip() or EMPTY for r in failed)
    browsers = Counter(str(r.get("browser") or "").strip() or EMPTY for r in failed)
    minutes = [m for r in failed if (m := _minutes_to_fail(r)) is not None]
    known = sum(n for k, n in systems.items() if k != EMPTY)
    rows = [{"kind": "os", "value": k, "failures": n, "percent": _pct(n, len(failed))} for k, n in systems.most_common()]
    rows += [{"kind": "browser", "value": k, "failures": n, "percent": _pct(n, len(failed))} for k, n in browsers.most_common()]
    median = _median(minutes)
    return {
        "console": console,
        "headline": (f"{len(failed)} failed emails in {_tests_label(tests, left_out)}"
                     + (f"; KnowBe4 recorded the device for {known} of them" if failed else "")
                     + (f"; median {round(median)} minutes from delivery to the first failure" if median is not None else "") + "."
                     + (" KnowBe4 recorded no operating system or browser for these failures." if failed and not known else "")),
        "rows": rows if known else [],
        "median_minutes_to_fail": _r(median),
        "fastest_minutes_to_fail": _r(min(minutes)) if minutes else None,
        "definitions": [f"{EMPTY} = no device recorded", "ip addresses and locations are left out on purpose"],
        "note": ("The table is added to the answer automatically. Do not mention ip addresses or locations. " + NO_ADVICE),
    }


# ---------------------------------------------------------------- the subscription, a monthly report, policies

async def subscription_status(kb: Any, console: str) -> dict[str, Any]:
    """licence level, end date and days left, seats licensed against active users, and the admins (names only)"""
    account = await kb.get_account(console)
    account = account if isinstance(account, dict) else {}
    users = await kb.list_users(console, "active")
    end = _date(account.get("subscription_end_date"))
    days = None
    if end:
        try:
            days = (date.fromisoformat(end) - date.today()).days
        except ValueError:
            days = None
    seats = account.get("number_of_seats") if isinstance(account.get("number_of_seats"), int) else None
    # names only: _name falls back to the email, which an admin list must not show
    admins = [" ".join(x for x in (a.get("first_name"), a.get("last_name")) if x) or "(admin with no name)"
              for a in account.get("admins") or [] if isinstance(a, dict)]
    if days is None:
        when = "no end date recorded"
    elif days < 0:
        when = f"ended on {end} ({-days} days ago)"
    else:
        when = f"ends on {end} ({days} days left)"
    over = len(users) - seats if seats is not None and len(users) > seats else 0
    return {
        "console": console,
        "headline": (f"Subscription {account.get('subscription_level') or '?'}: {when}. Seats: {seats if seats is not None else '?'} "
                     f"licensed, {len(users)} active users" + (f" ({over} more than the seats)" if over else "") +
                     f"; {len(admins)} admins."),
        "subscription_level": account.get("subscription_level"),
        "subscription_end_date": end or None,
        # an ended subscription: how long ago, not a negative "days left" (the model repeated "-487 days")
        "days_left": days if days is not None and days >= 0 else None,
        "days_since_end": -days if days is not None and days < 0 else None,
        "seats_licensed": seats,
        "active_users": len(users),
        "users_over_seats": over,
        "admins": admins,
        "note": ("Report these facts as they are; an end date in the past is what KnowBe4 returns, so say so without guessing "
                 "why. " + NO_ADVICE),
    }


def _last_full_month(today: date | None = None) -> tuple[str, str]:
    first = (today or date.today()).replace(day=1)
    end = first - timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


async def executive_report(kb: Any, console: str, month: str | None = None, start_date: str | None = None,
                           end_date: str | None = None) -> dict[str, Any]:
    """a fixed monthly summary for management: risk, phishing, training, the five riskiest groups and repeat clickers"""
    if month and str(month).strip():
        text = str(month).strip()
        try:
            first = date.fromisoformat(f"{text[:7]}-01")
        except ValueError:
            return {"console": console, "error": True, "message": "month must look like 2026-10."}
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        start_date, end_date = first.isoformat(), (nxt - timedelta(days=1)).isoformat()
    elif not (start_date or end_date):
        start_date, end_date = _last_full_month()
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    summary = await organisation_summary(kb, console, start_date, end_date, limit=5)
    if summary.get("error"):
        return summary
    users = await kb.list_users(console)
    people = {u.get("id"): u for u in users}
    tests, left_out = await _tests_in_scope(kb, console, None, None, start_date, end_date)
    pairs, _ = await _delivered(kb, console, tests, people, False)
    per = Counter(uid for uid, r in pairs if _failures(r))
    repeat = sorted((_name(people[u]) for u, n in per.items() if n >= 2), key=str.casefold)
    sub = await subscription_status(kb, console)
    period = _period_label(start_date, end_date)
    return {
        "console": console,
        "period": period,
        "headline": f"Security report {period}: " + summary["headline"],
        "risk": summary["risk"],
        "phishing": {**summary["phishing"], "tests": len(tests), "latest_test": tests[0].get("name") if tests else None},
        "training": summary["training"],
        "rows": summary["rows"],
        "total_rows": summary["total_rows"],
        "repeat_clickers": repeat[:10],
        "repeat_clickers_total": len(repeat),
        "subscription": {k: sub.get(k) for k in ("subscription_level", "subscription_end_date", "days_left", "days_since_end",
                                                  "seats_licensed", "active_users")},
        "structure": ["risk", "phishing", "training", "the five riskiest groups (table)", "repeat clickers", "subscription"],
        "note": ("Write a short management report in this order: risk, phishing, training, the riskiest groups (the table is "
                 "added automatically), repeat clickers, subscription. " + NO_ADVICE),
    }


def _is_policy(enrolment: dict[str, Any], names: set[str]) -> bool:
    # the content type of a policy enrolment is not documented and no account here has policies: match either way
    return "polic" in str(enrolment.get("content_type") or "").casefold() or str(enrolment.get("module_name") or "").casefold() in names


async def policy_acknowledgement(kb: Any, console: str, policy: str | None = None, group: str | None = None,
                                 limit: int = ROW_LIMIT) -> dict[str, Any]:
    """per policy: how many enrolled people acknowledged it; with one policy named, who has not"""
    policies = await kb.list_policies(console)
    if not policies:
        return {"console": console, "headline": "This account has no training policies in KnowBe4, so there is nothing to acknowledge.",
                "rows": [], "policies": 0, "note": NO_ADVICE}
    names = {str(x.get("name") or "").casefold() for x in policies if x.get("name")}
    users = await kb.list_users(console, "active")
    who = await _people_filter(kb, console, group, None, None, users)
    if "error" in who:
        return who
    active = {u.get("id"): u for u in users if not who or u.get("id") in who["ids"]}
    by_policy: dict[str, dict[Any, bool]] = {}
    for e in await kb.list_training_enrollments(console):
        uid = (e.get("user") or {}).get("id")
        if uid in active and _is_policy(e, names):
            seen = by_policy.setdefault(str(e.get("module_name") or "?").strip(), {})
            seen[uid] = seen.get(uid, False) or bool(e.get("policy_acknowledged"))
    if policy and str(policy).strip():
        wanted = str(policy).strip()
        found = [n for n in by_policy if _words_match(n, wanted) or wanted.casefold() in n.casefold()]
        if not found:
            return {"console": console, "error": True, "message": f"No policy enrolment matches '{wanted}'. Policies: "
                    f"{', '.join(sorted(by_policy)[:15]) or 'none with enrolments'}."}
        if len(found) > 1:
            return {"console": console, "ask_user": True, "message": "Several policies match; ask which one.", "policies": sorted(found)[:10]}
        by_policy = {found[0]: by_policy[found[0]]}
    rows = sorted(({"policy": n, "enrolled": len(s), "acknowledged": sum(s.values()), "not_acknowledged": len(s) - sum(s.values()),
                    "percent_acknowledged": _pct(sum(s.values()), len(s))} for n, s in by_policy.items()),
                  key=lambda r: (-(r["not_acknowledged"]), r["policy"].casefold()))
    pending = []
    if len(by_policy) == 1:
        only = next(iter(by_policy.values()))
        pending = sorted((_name(active[u]) for u, ok in only.items() if not ok), key=str.casefold)
    target = who.get("label", "everyone")
    return {
        "console": console,
        "headline": (f"{len(rows)} policies with enrolments ({target}); {sum(r['not_acknowledged'] for r in rows)} acknowledgements "
                     f"still missing." if rows else f"No policy enrolments ({target})."),
        "rows": rows[: _limit(limit, ROW_LIMIT)],
        "total_rows": len(rows),
        "not_acknowledged_people": pending[:50],
        "definitions": ["acknowledged = KnowBe4's policy_acknowledged on any of the person's enrolments in that policy"],
        "note": NO_ADVICE,
    }
