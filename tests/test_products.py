import json

import httpx
import pytest

from config.settings import AppConfig, ConsoleConfig
from kb4_mcp import products
from knowbe4 import client as client_module
from knowbe4.client import (
    AsyncRateLimiter,
    KnowBe4Client,
    KnowBe4ProductError,
    KnowBe4ProductKeyMissing,
    readable_error,
    readonly_query,
)

# ------------------------------------------------------------------ read-only guard


@pytest.mark.parametrize("document", [
    "query { account { id } }",
    "{ account { id } }",
    'query Reported($page: Int) { phisherMessages(query: "mutation", page: $page) { nodes { id } } }',
    '# a comment\nquery { x(text: """subscription""") { id } }',
])
def test_plain_queries_are_allowed(document):
    assert readonly_query(document) == document


@pytest.mark.parametrize("document", [
    "mutation { deleteUser(id: 1) { id } }",
    "query { a } mutation { b }",
    "subscription { events { id } }",
    "# query\nmutation { x }",
    "  ",
    "fragment F on User { id }",
])
def test_anything_that_can_write_is_refused(document):
    with pytest.raises(ValueError, match="read-only"):
        readonly_query(document)


# ------------------------------------------------------------------ settings


def test_product_keys_come_from_env_and_placeholders_count_as_none(monkeypatch):
    monkeypatch.setenv("K_MAIN", "real-token")
    monkeypatch.setenv("K_KSAT", "ksat-token")
    monkeypatch.setenv("K_PHISHER", "xxxx")
    cc = ConsoleConfig(display_name="Main", api_key_env="K_MAIN", ksat_key_env="K_KSAT", phisher_key_env="K_PHISHER")
    assert cc.product_key("ksat") == "ksat-token"
    assert cc.product_key("phisher") is None and cc.product_key("piq") is None
    assert cc.graph_url == "https://training.knowbe4.com/graphql" and cc.events_url == "https://api.events.knowbe4.com"
    eu = ConsoleConfig(display_name="EU", region="eu", api_key_env="K_MAIN")
    assert eu.graph_url == "https://eu.knowbe4.com/graphql" and eu.events_url == "https://api-eu.events.knowbe4.com"


# ------------------------------------------------------------------ client


def make_client(monkeypatch, handler, **overrides):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    monkeypatch.setenv("KB4_T_KSAT", "ksat-token")
    monkeypatch.setenv("KB4_T_EVENTS", "events-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN", ksat_key_env="KB4_T_KSAT",
                                                     events_key_env="KB4_T_EVENTS")}, kb4_rate_limit_rps=4, **overrides)
    kb = KnowBe4Client(cfg)
    kb._product_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    kb._limiters["main:products"] = AsyncRateLimiter(1000)
    return kb


def recording(body=None, status=200):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body if body is not None else {"data": {"account": {"id": 1}}})

    return handler, calls


async def test_graph_posts_the_query_with_the_product_key(monkeypatch):
    handler, calls = recording()
    kb = make_client(monkeypatch, handler)
    assert await kb.graph("main", "ksat", "query { account { id } }") == {"account": {"id": 1}}
    request = calls[0]
    assert str(request.url) == "https://training.knowbe4.com/graphql" and request.method == "POST"
    assert request.headers["Authorization"] == "Bearer ksat-token"
    assert json.loads(request.content) == {"query": "query { account { id } }", "variables": {}}
    assert kb.usage.used("main:ksat") == 1 and kb.usage.used("main") == 0


async def test_mutation_is_refused_before_any_request(monkeypatch):
    handler, calls = recording()
    kb = make_client(monkeypatch, handler)
    with pytest.raises(ValueError):
        await kb.graph("main", "ksat", "mutation { deleteUser(id: 1) { id } }")
    assert calls == []


async def test_missing_product_key_is_a_readable_error(monkeypatch):
    handler, calls = recording()
    kb = make_client(monkeypatch, handler)
    with pytest.raises(KnowBe4ProductKeyMissing) as info:
        await kb.graph("main", "phisher", "query { phisherMessages(query: \"\") { nodes { id } } }")
    assert "PhishER API key, which is not configured" in readable_error(info.value) and calls == []


@pytest.mark.parametrize("status,body,expected", [
    (401, {}, "API key was rejected"),
    (403, {}, "rejected or is not allowed"),
    (500, {}, "could not answer this request"),
    (200, {"errors": [{"message": "An unknown error occurred."}], "data": None}, "could not answer this request"),
    (200, {"errors": [{"message": "Field 'x' doesn't exist"}]}, "the request failed"),
])
async def test_product_errors_never_show_the_response(monkeypatch, status, body, expected):
    handler, _ = recording(body, status)
    kb = make_client(monkeypatch, handler, kb4_max_retries=0)
    with pytest.raises(KnowBe4ProductError) as info:
        await kb.graph("main", "ksat", "query { x }")
    assert expected in readable_error(info.value)


async def test_product_answers_are_cached_and_refresh_clears_them(monkeypatch):
    handler, calls = recording()
    kb = make_client(monkeypatch, handler)
    clock = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock[0])
    await kb.graph("main", "ksat", "query { account { id } }")
    await kb.graph("main", "ksat", "query { account { id } }")
    assert len(calls) == 1
    # different variables are a different question
    await kb.graph("main", "ksat", "query { account { id } }", {"page": 2})
    assert len(calls) == 2
    assert kb.clear_cache("main")["cached_answers_dropped"] == 2
    await kb.graph("main", "ksat", "query { account { id } }")
    assert len(calls) == 3


async def test_user_events_is_a_get_on_events(monkeypatch):
    handler, calls = recording({"data": [], "meta": {}})
    kb = make_client(monkeypatch, handler)
    assert await kb.list_user_events("main", {"per_page": 5}) == {"data": [], "meta": {}}
    assert calls[0].method == "GET" and str(calls[0].url) == "https://api.events.knowbe4.com/events?per_page=5"
    assert calls[0].headers["Authorization"] == "Bearer events-token"


# ------------------------------------------------------------------ product tools


class FakeKB:
    def __init__(self, answers=None, keys=("ksat", "phisher", "piq", "coach", "events"), events=None, users=None, fail=()):
        self.answers = answers or {}
        self.keys, self.events, self.fail = set(keys), events or [], set(fail)
        self.users = users if users is not None else [{"phish_prone_percentage": 10.0}, {"phish_prone_percentage": 20.0}]
        self.calls = []

    def has_product(self, console, product):
        return product in self.keys

    async def graph(self, console, product, document, variables=None):
        self.calls.append((product, document.split("{")[0].strip(), dict(variables or {})))
        if product in self.fail:
            raise KnowBe4ProductError(product, 500, "boom")
        for marker, answer in self.answers.items():
            if marker in document:
                return answer(variables or {}) if callable(answer) else answer
        return {}

    async def list_user_events(self, console, params=None):
        self.calls.append(("events", "GET", dict(params or {})))
        page = (params or {}).get("page", 1)
        per = (params or {}).get("per_page", 100)
        return {"data": self.events[(page - 1) * per: page * per]}

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in self.users]


def sizes(small):
    return {"small": small, "medium": small + 1, "large": small + 2, "xlarge": small + 3}


BENCH = {"industryBenchmarks": {
    "account": {"benchmarkIndustryId": 3, "benchmarkCompanySize": "SMALL", "benchmarkTimeframe": "DAYS90"},
    "industries": {"nodes": [{"id": 3, "name": "Banking", "enumName": "BANKING"}, {"id": 4, "name": "Technology", "enumName": "TECHNOLOGY"}]},
    "industryBenchmarks": {"nodes": [
        {"industry": "BANKING", "baseline": sizes(21.33), "days90": sizes(16.23), "year": sizes(2.37), "year2": None, "year3": None},
        {"industry": "ALL_INDUSTRIES", "baseline": sizes(24.73), "days90": sizes(21.77), "year": sizes(4.35), "year2": sizes(4.05), "year3": None},
    ]},
}}


async def test_benchmark_uses_the_accounts_industry_and_size():
    r = await products.industry_benchmark(FakeKB(BENCH), "main")
    assert r["our_phish_prone_percent"] == 15.0 and r["industry"] == "Banking"
    assert r["industry_benchmark"] == {"before training (baseline)": 21.33, "after 90 days of training": 16.23, "after 1 year": 2.37}
    assert r["headline"].startswith("Our average phish-prone % is 15.0%. KnowBe4's benchmark for Banking, organisations with fewer than 250 users")
    assert r["comparison"] == ("Our 15.0% is below the benchmark before training (baseline) (21.33%), after 90 days of training (16.23%) "
                               "and at or above the benchmark after 1 year (2.37%).")


async def test_benchmark_falls_back_to_all_industries_and_takes_a_named_one():
    data = json.loads(json.dumps(BENCH))
    data["industryBenchmarks"]["account"]["benchmarkIndustryId"] = 21
    r = await products.industry_benchmark(FakeKB(data), "main")
    assert r["industry"] == "all industries" and "(21) is not one of KnowBe4's" in r["industry_note"]
    tech = await products.industry_benchmark(FakeKB(data), "main", industry="tech")
    assert tech["industry"] == "Technology" and tech["headline"] == "KnowBe4 has no benchmark for Technology."
    missing = await products.industry_benchmark(FakeKB(data), "main", industry="space travel")
    assert missing["error"] is True and "Banking, Technology" in missing["message"]


def message(day, category="UNKNOWN", status="RECEIVED", by="ana@example.com"):
    return {"id": day, "subject": f"s{day}", "from": "x@example.com", "reportedBy": by, "reportedAt": f"{day}T08:00:00Z",
            "category": category, "severity": "UNKNOWN_SEVERITY" if category == "UNKNOWN" else "HIGH", "actionStatus": status}


MESSAGES = [message("2026-10-02", "THREAT", "RESOLVED"), message("2026-09-15", "SPAM", "IN_REVIEW", "budi@example.com"),
            message("2026-09-01"), message("2025-12-24", "CLEAN", "RESOLVED")]


def phisher_pages(per_page=2):
    def answer(variables):
        page = variables.get("page", 1)
        return {"phisherMessages": {"pagination": {"totalCount": len(MESSAGES), "pages": -(-len(MESSAGES) // per_page)},
                                    "nodes": MESSAGES[(page - 1) * per_page: page * per_page]}}
    return {"phisherMessages": answer}


async def test_reported_emails_counts_every_page():
    kb = FakeKB(phisher_pages())
    r = await products.reported_emails(kb, "main")
    assert [c[2]["page"] for c in kb.calls] == [1, 2]
    assert r["reported"] == 4 and r["by_category"] == {"THREAT": 1, "SPAM": 1, "UNKNOWN": 1, "CLEAN": 1}
    assert r["still_open"] == 2 and r["per_month"] == {"2025-12": 1, "2026-09": 2, "2026-10": 1}
    assert r["headline"] == ("4 emails were reported to PhishER; 1 threat, 1 spam, 1 clean and 1 not yet categorised. "
                             "2 are still open (received or in review).")
    assert r["top_reporters"][0] == {"reported_by": "ana@example.com", "emails": 3}


async def test_reported_emails_period_and_filters():
    r = await products.reported_emails(FakeKB(phisher_pages()), "main", start_date="2026-01-01")
    assert r["reported"] == 3 and r["reported_all_time"] == 4
    threats = await products.reported_emails(FakeKB(phisher_pages()), "main", category="threat")
    assert threats["reported"] == 1
    open_ones = await products.reported_emails(FakeKB(phisher_pages()), "main", status="in review")
    assert open_ones["reported"] == 1
    none = await products.reported_emails(FakeKB(phisher_pages()), "main", start_date="2027-01-01")
    assert none["headline"].startswith("No emails were reported to PhishER from 2027-01-01")
    bad = await products.reported_emails(FakeKB(phisher_pages()), "main", start_date="Jan 2026")
    assert bad["error"] is True


async def test_phisher_rules_ranked_by_hits():
    rules = {"phisherRules": {"phisherRules": {"pagination": {"pages": 1}, "nodes": [
        {"name": "a", "active": True, "hits": 1}, {"name": "b", "active": False, "hits": 4}]}}}
    r = await products.phisher_rules(FakeKB(rules), "main")
    assert [x["name"] for x in r["rules"]] == ["b", "a"]
    assert r["headline"] == 'PhishER has 2 rules, 1 active; together they matched 5 reported emails, most often "b" (4).'


async def test_usb_and_qr_results():
    usb = {"usbCampaigns": {"usbCampaigns": {"nodes": [
        {"name": "Lobby", "status": "started", "startedAt": "2026-03-01T00:00:00Z", "openedCountTotal": 2, "macroEnabledCountTotal": 1,
         "totalFailures": 3, "usbCampaignResults": [{"fileType": "docx", "openedAt": "x", "displayName": "Ana"},
                                                    {"fileType": "docx", "macroEnabledAt": "y", "displayName": "Budi"}]},
        {"name": "Empty", "status": "created", "totalFailures": 0, "usbCampaignResults": []}]}}}
    r = await products.usb_test_results(FakeKB(usb), "main")
    assert r["headline"] == "2 USB drive tests; 1 had failures, 3 failures in total (files opened or macros enabled)."
    assert r["tests"][0]["people"] == ["Ana", "Budi"] and r["tests"][0]["opened_by_file_type"] == {"docx": 1}
    qr = {"physicalQrCampaigns": {"physicalQrCampaigns": {"nodes": [{"name": "Poster", "status": "STARTED", "physicalQrCampaignLocations": [
        {"location": "Canteen", "totalQrCodeScanned": 3, "totalDataEntered": 1}, {"location": "Lift", "totalQrCodeScanned": 1, "totalDataEntered": 0}]}]}}}
    r = await products.physical_qr_results(FakeKB(qr), "main")
    assert r["headline"] == "1 physical QR code test; 4 scans and data entered 1 time."
    empty = await products.physical_qr_results(FakeKB({}), "main")
    assert empty["headline"] == "No physical QR code tests in this account."


async def test_simulation_overview_counts_types():
    answers = {
        "uasCampaigns": {"uasCampaigns": {"pagination": {"pages": 1}, "nodes": [
            {"name": "a", "campaignType": "standard", "active": True, "lastRunDate": "2026-10-01T00:00:00Z"},
            {"name": "b", "campaignType": "callback", "active": False, "lastRunDate": None}]}},
        "Overview": {"usbCampaigns": {"pagination": {"totalCount": 2}}, "physicalQrCampaigns": {"pagination": {"totalCount": 1}},
                     "aidaCampaign": {"disabled": False, "createdAt": "2025-03-17T00:00:00Z"}, "secondChanceOverview": {"deviceCount": 0}},
    }
    r = await products.simulation_overview(FakeKB(answers), "main")
    assert r["headline"] == ("2 phishing campaigns (1 standard, 1 callback), 1 active; 2 USB drive tests; 1 physical QR code test; "
                             "AIDA automated training on; Second Chance not installed on any device.")


async def test_audit_log_follows_the_cursor_and_counts():
    def entry(i, category, who):
        return {"id": str(i), "metadata": {"timestamp": f"2026-10-0{i}T08:00:00Z", "activity": "KMSAT_PHISHING_TEMPLATE_UPDATED"},
                "data": {"objectCategory": category, "actors": {"user": {"displayName": who}}, "changes": [{"fieldName": "name"}]}}

    pages = [
        {"auditLogs": {"pagination": {"hasNextPage": True, "endCursor": {"sortField": "ts", "ts": "t", "id": 2, "text": None}},
                       "nodes": [entry(1, "phishing", "Ana"), entry(2, "users", "Ana")]}},
        {"auditLogs": {"pagination": {"hasNextPage": False}, "nodes": [entry(3, "phishing", "Budi")]}},
    ]
    kb = FakeKB({"auditLogs": lambda variables: pages[1] if variables.get("after") else pages[0]})
    r = await products.admin_audit_log(kb, "main")
    assert kb.calls[0][2]["timeframe"] == "LAST_90_DAYS" and kb.calls[1][2]["after"]["id"] == 2
    assert r["changes"] == 3 and r["by_category"] == {"phishing": 2, "users": 1}
    assert r["latest"][0] == {"when": "2026-10-03 08:00", "activity": "phishing template updated", "by": "Budi", "fields_changed": ["name"]}
    assert r["headline"] == "From the last 90 days: 3 admin changes in the audit log, most in phishing (2); most active: Ana (2)."
    kb = FakeKB({"auditLogs": pages[1]})
    await products.admin_audit_log(kb, "main", start_date="2026-01-01")
    assert kb.calls[0][2]["timeframe"] == "CUSTOM" and kb.calls[0][2]["start"] == "2026-01-01T00:00:00Z"


async def test_coaching_names_what_setup_is_missing():
    data = {"Coaching": {"securityCoachSetupStatus": {"vendorIntegrated": True, "deliveryMethodAdded": True, "detectionRulesReviewed": True,
                                                    "rtcCampaignCreated": False},
                         "securityCoachRealTimeCoachingOverview": {"coachingDelivered": 0, "totalUsersCoached": 0, "repeatedOffenders": 0}}}
    kb = FakeKB(data)
    r = await products.security_coaching(kb, "main")
    assert kb.calls[0][2] == {"timeframe": {"type": "ENTIRE_HISTORY"}}
    assert r["headline"] == ("Real-Time Coaching from all time: 0 coaching messages to 0 people (0 repeat offenders). "
                             "Setup is incomplete: no coaching campaign yet.")
    kb = FakeKB(data)
    await products.security_coaching(kb, "main", start_date="2026-01-01")
    assert kb.calls[0][2]["timeframe"]["type"] == "CUSTOM"


async def test_password_risks_never_scanned_and_with_findings():
    r = await products.password_risks(FakeKB({"Piq": {"passwordIqDetectionCounts": {"lastScan": None, "counts": {"ALL": 0}}}}), "main")
    assert r["headline"].startswith("PasswordIQ has never scanned")
    found = {"Piq": {"passwordIqDetectionCounts": {"lastScan": "2026-10-01T00:00:00Z", "counts": {"ALL": 5, "AD_PW_WEAK": 3, "AD_PW_SHARED": 2}}}}
    r = await products.password_risks(FakeKB(found), "main")
    assert r["headline"] == "PasswordIQ last scanned 2026-10-01: 5 findings (3 weak passwords, 2 shared passwords)."


async def test_user_events_empty_and_counted():
    r = await products.user_events(FakeKB(), "main")
    assert r["headline"] == "No events from other security tools; nothing has been sent to the User Event API."
    events = [{"event_type": "dlp_violation", "source": "DLP", "target_user": "ana@example.com", "occurred_date": "2026-10-01"},
              {"event_type": "dlp_violation", "source": "DLP", "target_user": "ana@example.com", "occurred_date": "2026-10-02"},
              {"event_type": "malware", "source": "EDR", "target_user": "budi@example.com", "occurred_date": "2025-01-01"}]
    r = await products.user_events(FakeKB(events=events), "main", start_date="2026-01-01")
    assert r["events"] == 2 and r["by_type"] == {"dlp_violation": 2} and r["top_users"][0] == {"user": "ana@example.com", "events": 2}


async def test_product_status_keeps_going_when_one_product_fails():
    answers = {"phisherMessages": {"phisherMessages": {"pagination": {"totalCount": 59}}},
               "securityCoachSetupStatus": {"securityCoachSetupStatus": {"rtcCampaignCreated": False, "vendorIntegrated": True}},
               "aidaCampaign": {"aidaCampaign": {"disabled": False}, "secondChanceOverview": {"deviceCount": 0}}}
    r = await products.product_status(FakeKB(answers, fail={"piq"}), "main")
    rows = {x["product"]: x for x in r["products"]}
    assert rows["PhishER"]["detail"] == "59 reported emails"
    assert rows["KSAT"]["detail"] == "benchmarks, USB / QR tests, audit log; AIDA on; Second Chance not installed on any device"
    assert rows["PasswordIQ"]["detail"] == "could not be read (KnowBe4ProductError)"
    assert rows["Real-Time Coaching"]["detail"] == "security tool connected, but no coaching campaign yet"
    assert rows["User Event API"]["detail"] == "no events sent yet"
    assert r["headline"] == ("The account uses PhishER and KSAT. Real-Time Coaching and User Event API are connected but not used yet. "
                             "Users, risk scores, phishing tests and training are always available.")
    no_keys = await products.product_status(FakeKB(keys=()), "main")
    assert all(x["detail"] == "no API key configured" for x in no_keys["products"])



async def test_csv_exports_modules_and_reported_emails(tmp_path, monkeypatch):
    from kb4_mcp import outputs

    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)

    class KB(FakeKB):
        async def list_training_enrollments(self, console, **kwargs):
            return [{"module_name": f"Module {i}", "status": "Passed", "enrollment_date": "2026-10-01T00:00:00Z"} for i in range(60)]

    kb = KB(phisher_pages())
    modules = await outputs.export_csv(kb, "main", "modules")
    # every module, not the 50 a chat answer is capped at
    assert modules["rows"] == 60 and modules["columns"][0] == "module"
    reported = await outputs.export_csv(kb, "main", "reported_emails", start_date="2026-01-01")
    assert reported["rows"] == 3
    text = (tmp_path / reported["download_url"].split("/")[-1].split("?")[0]).read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "reported_at,subject,from,reported_by,category,severity,status"
