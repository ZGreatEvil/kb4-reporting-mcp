import pytest

from kb4_mcp import reports

GROUPS = [{"id": 1, "name": "Finance", "member_count": 2, "status": "active"}, {"id": 2, "name": "IT", "member_count": 1, "status": "active"}]
USERS = [
    {"id": 10, "first_name": "Ana", "last_name": "A", "status": "active", "groups": [1], "department": "Finance"},
    {"id": 11, "first_name": "Budi", "last_name": "B", "status": "active", "groups": [1], "department": "Finance"},
    {"id": 12, "first_name": "Citra", "last_name": "C", "status": "active", "groups": [2], "department": "IT"},
    {"id": 13, "first_name": "Dodi", "last_name": "D", "status": "archived", "groups": [1], "department": "Finance"},
]
# test-level counts as the api gives them: phish_prone_percentage is a fraction (failure actions / delivered)
TESTS = [
    {"pst_id": 100, "name": "Invoice", "started_at": "2026-09-05T00:00:00Z", "delivered_count": 4, "reported_count": 1,
     "phish_prone_percentage": 0.5},
    {"pst_id": 101, "name": "Parcel", "started_at": "2026-10-03T00:00:00Z", "delivered_count": 3, "reported_count": 2,
     "phish_prone_percentage": 1 / 3},
    {"pst_id": 102, "name": "Old", "started_at": "2025-01-01T00:00:00Z", "delivered_count": 2, "reported_count": 0,
     "phish_prone_percentage": 0.0},
]
EASY = {"id": 1, "name": "Invoice due", "difficulty": 1, "type": "Phishing"}
HARD = {"id": 2, "name": "Parcel held", "difficulty": 4, "type": "Phishing"}


def rec(uid, template, clicked=False, data=False, reported=None, os=None, browser=None):
    return {"user": {"id": uid}, "template": template, "delivered_at": "2026-09-05T08:00:00Z",
            "clicked_at": "2026-09-05T08:10:00Z" if clicked else None, "data_entered_at": "2026-09-05T08:12:00Z" if data else None,
            "reported_at": reported, "os": os, "browser": browser}


RECIPIENTS = {
    100: [rec(10, EASY, clicked=True, data=True, os="Android", browser="Chrome"), rec(11, EASY, reported="2026-09-05T08:30:00Z"),
          rec(12, HARD, clicked=True, os="Windows", browser="Edge"), rec(13, EASY, clicked=True)],
    101: [rec(10, HARD, clicked=True, reported="2026-09-05T09:00:00Z", os="Android", browser="Chrome"),
          rec(11, HARD, reported="2026-09-05T08:20:00Z"), rec(12, HARD)],
    102: [rec(10, EASY), rec(12, EASY)],
}


class FakeKB:
    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u["status"] == status]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [dict(t) for t in TESTS]

    async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
        return [dict(r) for r in RECIPIENTS[pst_id]]


# ---------------------------------------------------------------- trend

async def test_the_organisation_trend_uses_knowbe4s_own_counts():
    r = await reports.phishing_trend(FakeKB(), "main", start_date="2026-01-01")
    assert r["rows"] == [{"period": "2026-09", "tests": 1, "delivered": 4, "phish_prone_percent": 50.0, "report_percent": 25.0},
                         {"period": "2026-10", "tests": 1, "delivered": 3, "phish_prone_percent": 33.33, "report_percent": 66.67}]
    assert "fell from 50.0% (2026-09) to 33.33% (2026-10), 16.67 points" in r["headline"]
    assert r["source"] == "KnowBe4's own counts per test"


async def test_a_trend_per_group_or_department_comes_from_the_recipients():
    finance = await reports.phishing_trend(FakeKB(), "main", start_date="2026-01-01", group="finance")
    # Ana (2 actions) and Budi in September; Dodi is archived. October: Ana clicked, Budi reported
    assert [(p["period"], p["delivered"], p["phish_prone_percent"]) for p in finance["rows"]] == [("2026-09", 2, 100.0), ("2026-10", 2, 50.0)]
    it = await reports.phishing_trend(FakeKB(), "main", start_date="2026-01-01", attribute="departemen", value="it")
    assert [p["phish_prone_percent"] for p in it["rows"]] == [100.0, 0.0] and "department it" in it["headline"]
    quarters = await reports.phishing_trend(FakeKB(), "main", interval="quarter")
    assert [p["period"] for p in quarters["rows"]] == ["2025-Q1", "2026-Q3", "2026-Q4"]


@pytest.mark.parametrize("args,message", [({"interval": "week"}, "interval must be"), ({"group": "Marketing"}, "No group matches"),
                                          ({"attribute": "department"}, "Give the department value"),
                                          ({"attribute": "department", "value": "Sales"}, "No user has department"),
                                          ({"start_date": "Oktober"}, "must be a date")])
async def test_trend_bad_input(args, message):
    r = await reports.phishing_trend(FakeKB(), "main", **args)
    assert r["error"] is True and message in r["message"]


async def test_a_period_with_no_tests_says_so():
    r = await reports.phishing_trend(FakeKB(), "main", start_date="2027-01-01")
    assert r["rows"] == [] and "no phishing email was delivered" in r["headline"]


# ---------------------------------------------------------------- templates

async def test_templates_ranked_by_how_many_they_fooled():
    r = await reports.phishing_by_template(FakeKB(), "main", start_date="2026-01-01")
    rows = {x["template"]: x for x in r["rows"]}
    # easy: Ana (2 actions) + Budi = 2 emails, 2 actions -> 100%; hard: Citra, Ana, Budi, Citra = 4 emails, 2 actions -> 50%
    assert [x["template"] for x in r["rows"]] == ["Invoice due", "Parcel held"]
    assert rows["Invoice due"]["phish_prone_percent"] == 100.0 and rows["Invoice due"]["sent"] == 2
    assert rows["Parcel held"]["phish_prone_percent"] == 50.0 and rows["Parcel held"]["difficulty"] == 4
    assert [d["difficulty"] for d in r["by_difficulty"]] == [1, 4] and "most fooled: Invoice due" in r["headline"]


# ---------------------------------------------------------------- reporting

async def test_reporting_behaviour():
    r = await reports.reporting_behaviour(FakeKB(), "main", start_date="2026-01-01")
    # 6 emails to active people, 3 reported: Budi twice (never failed), Ana once after failing; Citra never reported
    assert r["report_percent"] == 50.0 and r["counts"] == {"people": 3, "reported_and_never_failed": 1, "failed_and_reported": 1,
                                                          "failed_never_reported": 1, "never_reported": 1}
    assert r["rows"] == [{"name": "Citra C", "received": 2, "failed": 1}]
    # delivery 08:00 -> reports at 08:30, 09:00 and 08:20: median 30 minutes
    assert r["median_minutes_to_report"] == 30.0 and "median 30 minutes" in r["headline"]
    finance = await reports.reporting_behaviour(FakeKB(), "main", start_date="2026-01-01", group="Finance")
    assert finance["counts"]["people"] == 2 and finance["rows"] == []


async def test_reporting_with_no_tests():
    r = await reports.reporting_behaviour(FakeKB(), "main", start_date="2027-01-01")
    assert r["error"] is True and "No phishing test" in r["message"]


# ---------------------------------------------------------------- devices

async def test_failures_by_device_and_browser_without_ip():
    r = await reports.phishing_click_details(FakeKB(), "main", start_date="2026-01-01")
    os_rows = {x["value"]: x["failures"] for x in r["rows"] if x["kind"] == "os"}
    assert os_rows == {"Android": 2, "Windows": 1} and r["median_minutes_to_fail"] == 10.0
    assert all("ip" not in key for row in r["rows"] for key in row)


async def test_no_device_recorded_says_so():
    class NoDevices(FakeKB):
        async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
            return [dict(r, os=None, browser=None) for r in RECIPIENTS[pst_id]]

    r = await reports.phishing_click_details(NoDevices(), "main", pst_id=100)
    assert r["rows"] == [] and "recorded no operating system or browser" in r["headline"]



async def test_small_template_samples_rank_after_the_rest():
    # live: a template sent once at 100% was called the most fooling, above one sent to 49 people at 14%
    many = [{"user": {"id": 1000 + i}, "template": HARD, "delivered_at": "2026-09-05T08:00:00Z",
             "clicked_at": "2026-09-05T08:10:00Z" if i < 2 else None} for i in range(10)]

    class Mixed(FakeKB):
        async def list_users(self, console, status=None, group_id=None, max_records=None):
            return [dict(u) for u in USERS] + [{"id": 1000 + i, "status": "active", "groups": []} for i in range(10)]

        async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
            return [dict(r) for r in many] + [rec(10, EASY, clicked=True)] if pst_id == 101 else []

    r = await reports.phishing_by_template(Mixed(), "main", start_date="2026-10-01")
    assert [x["template"] for x in r["rows"]] == ["Parcel held", "Invoice due"]
    assert r["rows"][1]["small_sample"] is True and "most fooled: Parcel held" in r["headline"]
