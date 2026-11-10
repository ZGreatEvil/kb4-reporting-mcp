"""Answers from KnowBe4's product APIs: KSAT GraphQL, PhishER, PasswordIQ, Real-Time Coaching and the User Event API.

Every query is a fixed read-only document in this file; values go in as variables, never into the text. The client
refuses anything but queries (the PhishER key could also change data). Sorting, counting and comparisons happen here,
as in summaries.py, so the chat model only reads small results.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from kb4_mcp.summaries import (
    NO_ADVICE,
    _bad_period,
    _date,
    _limit,
    _period_label,
    _r,
    _within,
)

MAX_PAGES = 5


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"

# ---------------------------------------------------------------- KSAT: industry benchmarks

SIZES = {
    "SMALL": ("small", "fewer than 250 users"),
    "MEDIUM": ("medium", "250-999 users"),
    "LARGE": ("large", "1,000-9,999 users"),
    "XLARGE": ("xlarge", "10,000 or more users"),
}
STAGES = (("baseline", "before training (baseline)"), ("days90", "after 90 days of training"), ("year", "after 1 year"),
          ("year2", "after 2 years"), ("year3", "after 3 years"))
SIZE_FIELDS = "{ small medium large xlarge }"
BENCHMARK_QUERY = (
    "query Benchmarks { account { benchmarkIndustryId benchmarkCompanySize benchmarkTimeframe }"
    " industries(per: 100) { nodes { id name enumName } }"
    " industryBenchmarks(per: 100) { nodes { industry baseline " + SIZE_FIELDS + " days90 " + SIZE_FIELDS + " year "
    + SIZE_FIELDS + " year2 " + SIZE_FIELDS + " year3 " + SIZE_FIELDS + " } } }"
)


def _stages(node: dict[str, Any] | None, size: str) -> dict[str, float | None]:
    if not node:
        return {}
    return {label: _r((node.get(stage) or {}).get(size)) for stage, label in STAGES if (node.get(stage) or {}).get(size) is not None}


async def industry_benchmark(kb: Any, console: str, industry: str | None = None) -> dict[str, Any]:
    """KnowBe4's official phish-prone % benchmark for the account's industry and size, against our own figure"""
    data = await kb.graph(console, "ksat", BENCHMARK_QUERY)
    account = data.get("account") or {}
    industries = (data.get("industries") or {}).get("nodes") or []
    benchmarks = {n.get("industry"): n for n in (data.get("industryBenchmarks") or {}).get("nodes") or []}
    by_id = {i.get("id"): i for i in industries}
    chosen = by_id.get(account.get("benchmarkIndustryId"))
    if industry and industry.strip():
        wanted = industry.strip().lower()
        chosen = next((i for i in industries if wanted in str(i.get("name")).lower() or wanted in str(i.get("enumName")).lower()), None)
        if not chosen:
            return {"console": console, "error": True,
                    "message": f"No KnowBe4 benchmark industry matches '{industry}'. Industries: {', '.join(sorted(str(i.get('name')) for i in industries))}."}
    size_key, size_label = SIZES.get(str(account.get("benchmarkCompanySize") or "SMALL").upper(), SIZES["SMALL"])
    ours_users = await kb.list_users(console, "active")
    ppp = [u["phish_prone_percentage"] for u in ours_users if isinstance(u.get("phish_prone_percentage"), (int, float))]
    ours = _r(sum(ppp) / len(ppp)) if ppp else None
    all_stages = _stages(benchmarks.get("ALL_INDUSTRIES"), size_key)
    fallback = None
    if chosen:
        name, industry_stages = str(chosen.get("name")), _stages(benchmarks.get(chosen.get("enumName")), size_key)
    else:
        # the test account's setting (21) is none of KnowBe4's 19 benchmark industries
        name, industry_stages = "all industries", all_stages
        fallback = (f"The account's benchmark industry setting ({account.get('benchmarkIndustryId')}) is not one of KnowBe4's "
                    "benchmark industries, so the all-industries benchmark is used. Name an industry to compare with it.")
    comparison = None
    if ours is not None and industry_stages:
        below = [f"{label} ({value}%)" for label, value in industry_stages.items() if ours < value]
        above = [f"{label} ({value}%)" for label, value in industry_stages.items() if ours >= value]
        comparison = f"Our {ours}% is " + " and ".join(
            part for part in (f"below the benchmark {', '.join(below)}" if below else "",
                              f"at or above the benchmark {', '.join(above)}" if above else "") if part) + "."
    return {
        "console": console,
        "headline": (
            f"Our average phish-prone % is {ours}%. KnowBe4's benchmark for {name}, organisations with {size_label}: "
            + "; ".join(f"{label} {value}%" for label, value in industry_stages.items()) + "."
            if industry_stages else f"KnowBe4 has no benchmark for {name}."
        ),
        "industry_note": fallback,
        "our_phish_prone_percent": ours,
        "our_figure": "average phish-prone % of the active users (Reporting API)",
        "industry": name,
        "company_size": f"{size_label} (the account's benchmark setting)",
        "account_benchmark_timeframe": account.get("benchmarkTimeframe"),
        "industry_benchmark": industry_stages,
        "all_industries_benchmark": all_stages,
        "comparison": comparison,
        "source": "KnowBe4 industry benchmarks (KSAT API, industryBenchmarks), phish-prone %; lower is better",
        "note": NO_ADVICE,
    }


# ---------------------------------------------------------------- PhishER: reported emails and rules

MESSAGES_QUERY = (
    "query Reported($page: Int, $per: Int) { phisherMessages(query: \"\", page: $page, per: $per, sortField: REPORTED_AT,"
    " sortDirection: DESCENDING) { pagination { totalCount pages } nodes { id subject from reportedBy reportedAt"
    " category severity actionStatus } } }"
)
OPEN_STATUSES = {"RECEIVED", "IN_REVIEW"}


async def _all_messages(kb: Any, console: str) -> tuple[list[dict[str, Any]], int]:
    messages, total = [], 0
    for page in range(1, MAX_PAGES + 1):
        data = (await kb.graph(console, "phisher", MESSAGES_QUERY, {"page": page, "per": 200})).get("phisherMessages") or {}
        pagination = data.get("pagination") or {}
        total = pagination.get("totalCount") or 0
        messages.extend(data.get("nodes") or [])
        if page >= (pagination.get("pages") or 1):
            break
    return messages, total


async def reported_emails(
    kb: Any, console: str, category: str | None = None, status: str | None = None, limit: int = 10,
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    """emails people reported (Phish Alert Button) into PhishER: categories, severity, open vs resolved, reporters"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    messages, total = await _all_messages(kb, console)
    period = _period_label(start_date, end_date)
    rows = [m for m in messages if _within(m.get("reportedAt"), start_date, end_date)]
    if category:
        rows = [m for m in rows if str(m.get("category")).lower() == category.strip().lower()]
    if status:
        rows = [m for m in rows if str(m.get("actionStatus")).lower().replace("_", " ") == status.strip().lower().replace("_", " ")]
    categories = Counter(str(m.get("category")) for m in rows)
    severities = Counter(str(m.get("severity")) for m in rows)
    statuses = Counter(str(m.get("actionStatus")) for m in rows)
    unresolved = sum(statuses[s] for s in OPEN_STATUSES)
    reporters = Counter(str(m.get("reportedBy") or "?") for m in rows)
    months = Counter(_date(m.get("reportedAt"))[:7] for m in rows if m.get("reportedAt"))
    return {
        "console": console,
        "period": period or "all reported emails",
        "headline": (
            f"{'From ' + period + ': ' if period else ''}{len(rows)} emails were reported to PhishER; "
            f"{categories['THREAT']} threat, {categories['SPAM']} spam, {categories['CLEAN']} clean and "
            f"{categories['UNKNOWN']} not yet categorised. {unresolved} are still open (received or in review)."
            if rows else f"No emails were reported to PhishER{' from ' + period if period else ''}."
        ),
        "reported": len(rows),
        "reported_all_time": total,
        "by_category": dict(categories),
        "by_severity": dict(severities),
        "by_status": dict(statuses),
        "still_open": unresolved,
        "per_month": dict(sorted(months.items())),
        "top_reporters": [{"reported_by": r, "emails": n} for r, n in reporters.most_common(_limit(limit))],
        "latest": [
            {"subject": m.get("subject"), "from": m.get("from"), "reported_by": m.get("reportedBy"),
             "reported_at": _date(m.get("reportedAt")), "category": m.get("category"), "severity": m.get("severity"),
             "status": m.get("actionStatus")}
            for m in rows[: _limit(limit)]
        ],
        "meaning": "category UNKNOWN and severity UNKNOWN_SEVERITY = not yet triaged in PhishER; RECEIVED = nobody has reviewed it yet",
        "note": NO_ADVICE,
    }


RULES_QUERY = "query Rules($page: Int) { phisherRules(query: \"\", page: $page, per: 100) { pagination { totalCount pages } nodes { name description active hits target createdAt updatedAt } } }"


async def phisher_rules(kb: Any, console: str, limit: int = 20) -> dict[str, Any]:
    """PhishER rules: which are active and how often each matched a reported email"""
    rules = []
    for page in range(1, MAX_PAGES + 1):
        data = (await kb.graph(console, "phisher", RULES_QUERY, {"page": page})).get("phisherRules") or {}
        rules.extend(data.get("nodes") or [])
        if page >= ((data.get("pagination") or {}).get("pages") or 1):
            break
    rules.sort(key=lambda r: r.get("hits") or 0, reverse=True)
    active = [r for r in rules if r.get("active")]
    return {
        "console": console,
        "headline": (f"PhishER has {len(rules)} rules, {len(active)} active; together they matched {sum(r.get('hits') or 0 for r in rules)} "
                     f"reported emails, most often \"{rules[0].get('name')}\" ({rules[0].get('hits') or 0})." if rules else "PhishER has no rules."),
        "rules": [{"name": r.get("name"), "active": r.get("active"), "hits": r.get("hits"), "target": r.get("target"),
                   "description": (r.get("description") or "")[:160], "updated": _date(r.get("updatedAt"))} for r in rules[: _limit(limit, 20)]],
        "note": NO_ADVICE,
    }


# ---------------------------------------------------------------- KSAT: USB, physical QR and all simulations

USB_QUERY = (
    "query Usb { usbCampaigns(per: 100) { pagination { totalCount } nodes { name status location startedAt completedAt"
    " openedCountTotal macroEnabledCountTotal totalFailures usbCampaignResults { fileType openedAt macroEnabledAt displayName userName } } } }"
)


async def usb_test_results(kb: Any, console: str, limit: int = 10) -> dict[str, Any]:
    """USB drive tests: drives left out, who opened files on them and who enabled macros"""
    campaigns = ((await kb.graph(console, "ksat", USB_QUERY)).get("usbCampaigns") or {}).get("nodes") or []
    rows = []
    for c in campaigns:
        results = c.get("usbCampaignResults") or []
        people = {str(r.get("displayName") or r.get("userName") or "?") for r in results if r.get("openedAt") or r.get("macroEnabledAt")}
        rows.append({
            "name": c.get("name"), "status": c.get("status"), "location": c.get("location"),
            "started": _date(c.get("startedAt")), "completed": _date(c.get("completedAt")),
            "files_opened": c.get("openedCountTotal"), "macros_enabled": c.get("macroEnabledCountTotal"),
            "failures": c.get("totalFailures"), "people": sorted(people)[: _limit(limit)], "people_count": len(people),
            "opened_by_file_type": dict(Counter(str(r.get("fileType")) for r in results if r.get("openedAt"))),
        })
    rows.sort(key=lambda r: r["started"] or "", reverse=True)
    failures = sum(r["failures"] or 0 for r in rows)
    return {
        "console": console,
        "headline": (f"{_count(len(rows), 'USB drive test')}; {sum(1 for r in rows if (r['failures'] or 0) > 0)} had failures, "
                     f"{failures} failures in total (files opened or macros enabled)." if rows else "No USB drive tests in this account."),
        "tests": rows,
        "meaning": "a USB drive test leaves drives with harmless files; opening a file or enabling macros counts as a failure",
        "note": NO_ADVICE,
    }


QR_QUERY = (
    "query Qr { physicalQrCampaigns(per: 100) { pagination { totalCount } nodes { name status startedAt completedAt"
    " physicalQrCampaignLocations { location totalQrCodeScanned totalDataEntered } } } }"
)


async def physical_qr_results(kb: Any, console: str) -> dict[str, Any]:
    """physical QR code tests (posters or flyers): scans and data entered per location"""
    campaigns = ((await kb.graph(console, "ksat", QR_QUERY)).get("physicalQrCampaigns") or {}).get("nodes") or []
    rows = []
    for c in campaigns:
        locations = c.get("physicalQrCampaignLocations") or []
        rows.append({
            "name": c.get("name"), "status": c.get("status"), "started": _date(c.get("startedAt")), "completed": _date(c.get("completedAt")),
            "scans": sum(x.get("totalQrCodeScanned") or 0 for x in locations),
            "data_entered": sum(x.get("totalDataEntered") or 0 for x in locations),
            "locations": [{"location": x.get("location"), "scans": x.get("totalQrCodeScanned"), "data_entered": x.get("totalDataEntered")}
                          for x in locations],
        })
    return {
        "console": console,
        "headline": (f"{_count(len(rows), 'physical QR code test')}; {_count(sum(r['scans'] for r in rows), 'scan')} and data entered "
                     f"{_count(sum(r['data_entered'] for r in rows), 'time')}." if rows else "No physical QR code tests in this account."),
        "tests": rows,
        "meaning": "a physical QR test puts a QR code on a poster or flyer; scanning it, and then entering data, are failures",
        "note": NO_ADVICE,
    }


CAMPAIGNS_QUERY = (
    "query Campaigns($page: Int) { uasCampaigns(page: $page, per: 100, type: ALL, filter: ALL) { pagination { totalCount pages }"
    " nodes { name campaignType active lastRunDate isPhishflip } } }"
)
OVERVIEW_QUERY = (
    "query Overview { usbCampaigns(per: 1) { pagination { totalCount } } physicalQrCampaigns(per: 1) { pagination { totalCount } }"
    " aidaCampaign { disabled createdAt } secondChanceOverview { overviewDays deviceCount abortedCount continuedCount } }"
)


async def simulation_overview(kb: Any, console: str) -> dict[str, Any]:
    """every kind of simulation the account runs: email phishing by type (standard, callback, vishing), USB, QR, AIDA"""
    campaigns = []
    for page in range(1, MAX_PAGES + 1):
        data = (await kb.graph(console, "ksat", CAMPAIGNS_QUERY, {"page": page})).get("uasCampaigns") or {}
        campaigns.extend(data.get("nodes") or [])
        if page >= ((data.get("pagination") or {}).get("pages") or 1):
            break
    extra = await kb.graph(console, "ksat", OVERVIEW_QUERY)
    types = Counter(str(c.get("campaignType") or "?") for c in campaigns)
    active = sum(1 for c in campaigns if c.get("active"))
    usb = ((extra.get("usbCampaigns") or {}).get("pagination") or {}).get("totalCount") or 0
    qr = ((extra.get("physicalQrCampaigns") or {}).get("pagination") or {}).get("totalCount") or 0
    aida = extra.get("aidaCampaign") or {}
    second = extra.get("secondChanceOverview") or {}
    latest = sorted((c for c in campaigns if c.get("lastRunDate")), key=lambda c: str(c.get("lastRunDate")), reverse=True)[:5]
    return {
        "console": console,
        "headline": (
            f"{_count(len(campaigns), 'phishing campaign')} ({', '.join(f'{n} {t}' for t, n in types.most_common())}), {active} active; "
            f"{_count(usb, 'USB drive test')}; {_count(qr, 'physical QR code test')}; AIDA automated training "
            f"{'on' if aida and not aida.get('disabled') else 'off'}; {_second_chance(second.get('deviceCount'))}."
        ),
        "phishing_campaigns": {"total": len(campaigns), "by_type": dict(types), "active": active,
                               "phishflip": sum(1 for c in campaigns if c.get("isPhishflip"))},
        "latest_runs": [{"name": c.get("name"), "type": c.get("campaignType"), "last_run": _date(c.get("lastRunDate"))} for c in latest],
        "usb_tests": usb,
        "physical_qr_tests": qr,
        "aida": {"enabled": bool(aida) and not aida.get("disabled"), "since": _date(aida.get("createdAt"))},
        "second_chance": {"devices": second.get("deviceCount"), "stopped_clicks": second.get("abortedCount"),
                          "continued": second.get("continuedCount"), "over_days": second.get("overviewDays")},
        "meaning": "campaign types: standard = email phishing, callback = email asking to phone a number, vishing = voice calls",
        "note": NO_ADVICE,
    }


# ---------------------------------------------------------------- KSAT: admin audit log

AUDIT_QUERY = (
    "query Audit($first: Int, $after: CursorPaginationCursorAttributes, $timeframe: AuditLogSearchPeriods, $start: ISO8601DateTime,"
    " $end: ISO8601DateTime) { auditLogs(first: $first, after: $after, timeframe: $timeframe, startTime: $start, endTime: $end,"
    " impersonatingUserIds: [], userIds: [], objectCategories: [], objectTypes: [], objectIds: [], activities: [], changes: [])"
    " { pagination { hasNextPage endCursor { sortField ts id text } } nodes { id metadata { timestamp activity }"
    " data { objectCategory objectType actors { systemPresent system user { displayName } } changes { fieldName } } } } }"
)


def _activity(name: Any) -> str:
    # KMSAT_PHISHING_TEMPLATE_UPDATED -> phishing template updated
    text = str(name or "?").lower()
    return text[len("kmsat_"):].replace("_", " ") if text.startswith("kmsat_") else text.replace("_", " ")


async def admin_audit_log(
    kb: Any, console: str, category: str | None = None, limit: int = 15, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """what admins changed in the console (KnowBe4 audit log): who, what and when"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    variables: dict[str, Any] = {"first": 100}
    if start_date or end_date:
        variables.update({"timeframe": "CUSTOM", "start": f"{start_date or '2000-01-01'}T00:00:00Z",
                          "end": f"{end_date or date.today().isoformat()}T23:59:59Z"})
    else:
        variables["timeframe"] = "LAST_90_DAYS"
    entries = []
    for _ in range(MAX_PAGES):
        data = (await kb.graph(console, "ksat", AUDIT_QUERY, variables)).get("auditLogs") or {}
        entries.extend(data.get("nodes") or [])
        pagination = data.get("pagination") or {}
        if not pagination.get("hasNextPage") or not pagination.get("endCursor"):
            break
        variables["after"] = pagination["endCursor"]
    if category:
        entries = [e for e in entries if str((e.get("data") or {}).get("objectCategory")).lower() == category.strip().lower()]
    entries.sort(key=lambda e: str((e.get("metadata") or {}).get("timestamp")), reverse=True)

    def actor(e: dict[str, Any]) -> str:
        actors = (e.get("data") or {}).get("actors") or {}
        return str(((actors.get("user") or {}).get("displayName")) or actors.get("system") or "?")

    period = _period_label(start_date, end_date) or "the last 90 days"
    categories = Counter(str((e.get("data") or {}).get("objectCategory")) for e in entries)
    activities = Counter(_activity((e.get("metadata") or {}).get("activity")) for e in entries)
    people = Counter(actor(e) for e in entries)
    return {
        "console": console,
        "period": period,
        "headline": (f"From {period}: {len(entries)} admin changes in the audit log, most in {categories.most_common(1)[0][0]} "
                     f"({categories.most_common(1)[0][1]}); most active: {people.most_common(1)[0][0]} ({people.most_common(1)[0][1]})."
                     if entries else f"No admin changes in the audit log from {period}."),
        "changes": len(entries),
        "capped": len(entries) >= 100 * MAX_PAGES,
        "by_category": dict(categories),
        "top_activities": [{"activity": a, "count": n} for a, n in activities.most_common(10)],
        "by_admin": [{"admin": p, "changes": n} for p, n in people.most_common(10)],
        "latest": [{"when": str((e.get("metadata") or {}).get("timestamp"))[:16].replace("T", " "),
                    "activity": _activity((e.get("metadata") or {}).get("activity")), "by": actor(e),
                    "fields_changed": [c.get("fieldName") for c in (e.get("data") or {}).get("changes") or [] if c.get("fieldName")][:6]}
                   for e in entries[: _limit(limit, 15)]],
        "note": "Times are UTC. " + NO_ADVICE,
    }


# ---------------------------------------------------------------- Real-Time Coaching, PasswordIQ, User Events

COACH_QUERY = (
    "query Coaching($timeframe: ReportsTimeframe!) { securityCoachSetupStatus { vendorIntegrated rtcCampaignCreated"
    " deliveryMethodAdded detectionRulesReviewed } securityCoachRealTimeCoachingOverview(timeframe: $timeframe) {"
    " coachingDelivered totalUsersCoached newUsersCoached repeatedOffenders riskiestUsers { email count }"
    " riskiestGroups { name count } campaignCounts { name count } } }"
)


async def security_coaching(kb: Any, console: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    """Real-Time Coaching (SecurityCoach): is it set up, how much coaching went out, who triggered it most"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    timeframe = ({"type": "CUSTOM", "customStart": start_date or "2000-01-01", "customEnd": end_date or date.today().isoformat()}
                 if start_date or end_date else {"type": "ENTIRE_HISTORY"})
    data = await kb.graph(console, "coach", COACH_QUERY, {"timeframe": timeframe})
    setup = data.get("securityCoachSetupStatus") or {}
    overview = data.get("securityCoachRealTimeCoachingOverview") or {}
    period = _period_label(start_date, end_date) or "all time"
    missing = [label for key, label in (("vendorIntegrated", "no security tool connected"), ("deliveryMethodAdded", "no delivery method"),
                                        ("detectionRulesReviewed", "detection rules not reviewed"), ("rtcCampaignCreated", "no coaching campaign yet"))
               if not setup.get(key)]
    return {
        "console": console,
        "period": period,
        "headline": (
            f"Real-Time Coaching from {period}: {overview.get('coachingDelivered') or 0} coaching messages to "
            f"{overview.get('totalUsersCoached') or 0} people ({overview.get('repeatedOffenders') or 0} repeat offenders)."
            + (f" Setup is incomplete: {', '.join(missing)}." if missing else " Setup is complete.")
        ),
        "setup": {"security_tool_connected": setup.get("vendorIntegrated"), "delivery_method": setup.get("deliveryMethodAdded"),
                  "detection_rules_reviewed": setup.get("detectionRulesReviewed"), "coaching_campaign": setup.get("rtcCampaignCreated")},
        "coaching_delivered": overview.get("coachingDelivered"),
        "people_coached": overview.get("totalUsersCoached"),
        "new_people_coached": overview.get("newUsersCoached"),
        "repeat_offenders": overview.get("repeatedOffenders"),
        "riskiest_users": (overview.get("riskiestUsers") or [])[:10],
        "riskiest_groups": (overview.get("riskiestGroups") or [])[:10],
        "meaning": "Real-Time Coaching sends a short lesson when a connected security tool sees someone do something risky",
        "note": NO_ADVICE,
    }


PIQ_QUERY = (
    "query Piq { passwordIqDetectionCounts(groups: [], userType: ALL) { lastScan counts { ALL AD_PW_WEAK AD_PW_SHARED"
    " AD_PW_EMPTY AD_PW_CLEAR_TEXT AD_PW_NOT_REQD AD_PW_NEVER_EXPIRES AD_PW_FOUND_IN_BREACH AD_USER_USES_LM_HASH } } }"
)
PIQ_LABELS = {
    "AD_PW_WEAK": "weak passwords", "AD_PW_SHARED": "shared passwords", "AD_PW_EMPTY": "empty passwords",
    "AD_PW_CLEAR_TEXT": "passwords stored in clear text", "AD_PW_NOT_REQD": "accounts that need no password",
    "AD_PW_NEVER_EXPIRES": "passwords that never expire", "AD_PW_FOUND_IN_BREACH": "passwords found in data breaches",
    "AD_USER_USES_LM_HASH": "accounts using old LM hashes",
}


async def password_risks(kb: Any, console: str) -> dict[str, Any]:
    """PasswordIQ: weak, shared, breached or never-expiring Active Directory passwords from the last scan"""
    data = (await kb.graph(console, "piq", PIQ_QUERY)).get("passwordIqDetectionCounts") or {}
    counts = data.get("counts") or {}
    found = {label: counts.get(key) for key, label in PIQ_LABELS.items() if counts.get(key)}
    return {
        "console": console,
        "headline": (
            "PasswordIQ has never scanned this account's Active Directory, so there are no password findings." if not data.get("lastScan")
            else f"PasswordIQ last scanned {_date(data.get('lastScan'))}: {counts.get('ALL') or 0} findings"
                 + (f" ({', '.join(f'{n} {label}' for label, n in found.items())})." if found else ".")
        ),
        "last_scan": _date(data.get("lastScan")) or None,
        "findings_total": counts.get("ALL"),
        "findings": found,
        "meaning": "PasswordIQ checks Active Directory accounts for risky passwords; it needs its scanner installed and run",
        "note": NO_ADVICE,
    }


async def user_events(
    kb: Any, console: str, user_email: str | None = None, limit: int = 10, start_date: str | None = None, end_date: str | None = None
) -> dict[str, Any]:
    """events other security tools pushed into KnowBe4 (User Event API): what happened, to whom, when"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    events: list[dict[str, Any]] = []
    params: dict[str, Any] = {"per_page": 100}
    if user_email:
        params["target_user"] = user_email.strip()
    for page in range(1, MAX_PAGES + 1):
        body = await kb.list_user_events(console, {**params, "page": page})
        batch = body.get("data") if isinstance(body, dict) else body
        events.extend(batch or [])
        if not batch or len(batch) < params["per_page"]:
            break
    period = _period_label(start_date, end_date)
    rows = [e for e in events if _within(e.get("occurred_date") or e.get("created_at"), start_date, end_date)]
    types = Counter(str(e.get("event_type") or "?") for e in rows)
    sources = Counter(str(e.get("source") or "?") for e in rows)
    # field names from the api's event schema (target_user, event_type, source, occurred_date); no live events to check yet
    users = Counter(str(e.get("target_user") or (e.get("user") or {}).get("email") or "?") for e in rows)
    return {
        "console": console,
        "period": period or "all events",
        "headline": (f"{len(rows)} events from other security tools{' from ' + period if period else ''}, "
                     f"mostly {types.most_common(1)[0][0]} ({types.most_common(1)[0][1]})." if rows
                     else f"No events from other security tools{' from ' + period if period else ''}; nothing has been sent to the User Event API."),
        "events": len(rows),
        "by_type": dict(types),
        "by_source": dict(sources),
        "top_users": [{"user": u, "events": n} for u, n in users.most_common(_limit(limit))],
        "latest": [{k: e.get(k) for k in ("event_type", "source", "occurred_date", "description")} for e in rows[: _limit(limit)]],
        "meaning": "the User Event API lets other tools (DLP, EDR, HR systems) add events to a person's KnowBe4 record",
        "note": NO_ADVICE,
    }


# ---------------------------------------------------------------- which products are set up

# plain product names: an english explanation in the label ended up inside indonesian answers
STATUS_CHECKS = (
    ("phisher", "PhishER", "query { phisherMessages(query: \"\", per: 1) { pagination { totalCount } } }"),
    ("piq", "PasswordIQ", "query { passwordIqDetectionCounts(groups: [], userType: ALL) { lastScan counts { ALL } } }"),
    ("coach", "Real-Time Coaching", "query { securityCoachSetupStatus { rtcCampaignCreated vendorIntegrated } }"),
    ("ksat", "KSAT", "query { aidaCampaign { disabled } secondChanceOverview { deviceCount } }"),
)


def _second_chance(devices: Any) -> str:
    # "Second Chance on 0 devices" came out as "aktif untuk 0 perangkat"
    return f"Second Chance installed on {devices} devices" if devices else "Second Chance not installed on any device"


async def product_status(kb: Any, console: str) -> dict[str, Any]:
    """which KnowBe4 products this console can read, and whether each is actually in use"""
    rows = []
    for product, label, query in STATUS_CHECKS:
        if not kb.has_product(console, product):
            rows.append({"product": label, "key": False, "in_use": None, "detail": "no API key configured"})
            continue
        try:
            data = await kb.graph(console, product, query)
        except Exception as exc:  # one product failing must not hide the others
            rows.append({"product": label, "key": True, "in_use": None, "detail": f"could not be read ({type(exc).__name__})"})
            continue
        if product == "phisher":
            n = ((data.get("phisherMessages") or {}).get("pagination") or {}).get("totalCount") or 0
            rows.append({"product": label, "key": True, "in_use": n > 0, "detail": f"{n} reported emails"})
        elif product == "piq":
            scan = (data.get("passwordIqDetectionCounts") or {}).get("lastScan")
            rows.append({"product": label, "key": True, "in_use": bool(scan), "detail": f"last scan {_date(scan)}" if scan else "never scanned"})
        elif product == "coach":
            s = data.get("securityCoachSetupStatus") or {}
            rows.append({"product": label, "key": True, "in_use": bool(s.get("rtcCampaignCreated")),
                         "detail": "coaching campaign running" if s.get("rtcCampaignCreated") else
                         ("security tool connected, but no coaching campaign yet" if s.get("vendorIntegrated") else "not set up")})
        else:
            aida = data.get("aidaCampaign") or {}
            devices = (data.get("secondChanceOverview") or {}).get("deviceCount") or 0
            rows.append({"product": label, "key": True, "in_use": True,
                         "detail": f"benchmarks, USB / QR tests, audit log; AIDA {'on' if aida and not aida.get('disabled') else 'off'}; "
                                   f"{_second_chance(devices)}"})
    if kb.has_product(console, "events"):
        try:
            body = await kb.list_user_events(console, {"per_page": 1})
            n = len(body.get("data") or []) if isinstance(body, dict) else len(body or [])
            rows.append({"product": "User Event API", "key": True, "in_use": n > 0, "detail": "events received" if n else "no events sent yet"})
        except Exception as exc:
            rows.append({"product": "User Event API", "key": True, "in_use": None, "detail": f"could not be read ({type(exc).__name__})"})
    else:
        rows.append({"product": "User Event API", "key": False, "in_use": None, "detail": "no API key configured"})
    used = [r["product"] for r in rows if r["in_use"]]
    idle = [r["product"] for r in rows if r["key"] and r["in_use"] is False]

    def joined(names: list[str]) -> str:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]

    return {
        "console": console,
        # whole sentences: the label style "In use: ..." was copied untranslated into indonesian answers
        "headline": (
            (f"The account uses {joined(used)}. " if used else "The account uses none of the extra KnowBe4 products. ")
            + (f"{joined(idle)} {'is' if len(idle) == 1 else 'are'} connected but not used yet. " if idle else "")
            + "Users, risk scores, phishing tests and training are always available."
        ),
        "products": rows,
        "note": NO_ADVICE,
    }
