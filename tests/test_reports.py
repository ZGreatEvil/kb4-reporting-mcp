import pytest

from kb4_mcp import reports

GROUPS = [
    {"id": 1, "name": "Finance", "member_count": 3, "current_risk_score": 50.0, "status": "active"},
    {"id": 2, "name": "Finance Jakarta", "member_count": 1, "current_risk_score": 40.0, "status": "active"},
    {"id": 3, "name": "IT", "member_count": 2, "current_risk_score": 30.0, "status": "active"},
]
USERS = [
    {"id": 10, "first_name": "Ana", "last_name": "A", "email": "ana@example.com", "status": "active", "groups": [1],
     "department": "Finance", "job_title": "Analyst", "manager_name": "Rina", "current_risk_score": 55.0},
    {"id": 11, "first_name": "Budi", "last_name": "B", "email": "budi@example.com", "status": "active", "groups": [1, 2],
     "department": "Finance", "job_title": "Clerk", "manager_name": "Rina", "current_risk_score": 41.0},
    {"id": 12, "first_name": "Citra", "last_name": "C", "email": "citra@example.com", "status": "active", "groups": [3],
     "department": "IT", "job_title": "Engineer", "manager_name": "Sari", "current_risk_score": 30.0},
    {"id": 13, "first_name": "Dodi", "last_name": "D", "email": "dodi@example.com", "status": "archived", "groups": [1],
     "department": "Finance", "manager_name": "Rina"},
    {"id": 14, "first_name": "Eka", "last_name": "E", "email": "eka@example.com", "status": "active", "groups": [3],
     "department": "", "job_title": "Engineer", "current_risk_score": 20.0},
]
TESTS = [
    {"pst_id": 100, "name": "Invoice", "started_at": "2026-10-01T00:00:00Z"},
    {"pst_id": 101, "name": "Old test", "started_at": "2026-04-01T00:00:00Z"},
]


def rec(uid, clicked=False, data=False, reported=False, delivered=True):
    return {"user": {"id": uid}, "delivered_at": "2026-10-01T01:00:00Z" if delivered else None,
            "clicked_at": "x" if clicked else None, "data_entered_at": "x" if data else None,
            "reported_at": "x" if reported else None}


RECIPIENTS = {
    # Ana clicks and enters data (2 failure actions, 1 failed email); Dodi is archived; Eka was never delivered
    100: [rec(10, clicked=True, data=True), rec(11, reported=True), rec(12), rec(13, clicked=True), rec(14, delivered=False)],
    101: [rec(10, clicked=True), rec(12, clicked=True)],
}
CAMPAIGNS = [{"campaign_id": 7, "name": "Onboarding", "start_date": "2026-09-01T00:00:00Z", "groups": [{"group_id": 1}]},
             {"campaign_id": 8, "name": "Refresher", "start_date": "2026-09-01T00:00:00Z", "groups": [{"group_id": 3}]}]


def enrol(uid, status, campaign=7, when="2026-09-02T00:00:00Z"):
    return {"campaign_id": campaign, "status": status, "user": {"id": uid}, "enrollment_date": when}


ENROLMENTS = [enrol(10, "Passed"), enrol(10, "Past Due"), enrol(11, "Passed"), enrol(11, "Passed", campaign=8),
              enrol(12, "Not Started", campaign=8), enrol(13, "Past Due"), enrol(14, "In Progress", campaign=8, when="2025-01-01T00:00:00Z")]


class FakeKB:
    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u["status"] == status]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [dict(t) for t in TESTS]

    async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
        return [dict(r) for r in RECIPIENTS[pst_id]]

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [dict(c) for c in CAMPAIGNS]

    async def list_training_enrollments(self, console, *args, **kwargs):
        return [dict(e) for e in ENROLMENTS]

    async def get_group_risk_history(self, console, group_id, full=False):
        return [{"date": "2026-08-01", "risk_score": 60.0}, {"date": "2026-11-01", "risk_score": 50.0}]

    async def get_account(self, console):
        return {"name": "Example", "current_risk_score": 38.0}

    async def get_account_risk_history(self, console, full=False):
        return [{"date": "2026-08-01", "risk_score": 45.0}, {"date": "2026-11-01", "risk_score": 38.0}]


# ---------------------------------------------------------------- phishing per field

async def test_phishing_per_department_counts_actions_and_failed_emails_separately():
    r = await reports.phishing_by_attribute(FakeKB(), "main", "departemen")
    assert r["attribute"] == "department" and [t["pst_id"] for t in r["tests"]] == [100]   # the latest test
    rows = {x["value"]: x for x in r["rows"]}
    # Ana: one email, two failure actions -> phish-prone 100% for Finance (2 actions / 2 emails), 1 failed email (50%)
    assert rows["Finance"]["delivered"] == 2 and rows["Finance"]["failure_actions"] == 2
    assert rows["Finance"]["phish_prone_percent"] == 100.0 and rows["Finance"]["failed_percent"] == 50.0
    assert rows["Finance"]["report_percent"] == 50.0 and rows["Finance"]["small_sample"] is True
    assert rows["IT"]["phish_prone_percent"] == 0.0
    # Dodi is archived, Eka (no department) never got it
    assert r["archived_not_counted"] == 1 and "(kosong)" not in rows and r["totals"]["delivered"] == 3


async def test_phishing_per_field_over_a_period_and_the_empty_value_last():
    r = await reports.phishing_by_attribute(FakeKB(), "main", "job_title", start_date="2026-01-01")
    assert len(r["tests"]) == 2
    assert [x["value"] for x in r["rows"]][:1] == ["Analyst"]   # 2 failed emails of 2
    with_archived = await reports.phishing_by_attribute(FakeKB(), "main", "department", include_archived=True)
    assert {x["value"]: x["delivered"] for x in with_archived["rows"]}["Finance"] == 3


@pytest.mark.parametrize("attribute,message", [("salary", "attribute must be one of"), ("employee_number", "attribute must be one of"),
                                               ("location", "No active user has a location")])
async def test_phishing_per_field_bad_or_empty_field(attribute, message):
    r = await reports.phishing_by_attribute(FakeKB(), "main", attribute)
    assert r["error"] is True and message in r["message"]
    if attribute == "location":
        assert "phishing_by_group" in r["message"]


# ---------------------------------------------------------------- training per field

async def test_training_per_department_counts_people_once_per_campaign():
    r = await reports.training_by_attribute(FakeKB(), "main", "department", start_date="2026-01-01")
    rows = {x["value"]: x for x in r["rows"]}
    # Ana Past Due (one late module), Budi passed two campaigns = 2; Dodi archived; Eka enrolled in 2025
    assert rows["Finance"]["total"] == 3 and rows["Finance"]["past_due"] == 1 and rows["Finance"]["completed"] == 2
    assert rows["IT"]["total"] == 1 and rows["IT"]["not_started"] == 1
    assert "(kosong)" not in rows and r["totals"]["total"] == 4


async def test_training_per_field_for_one_campaign_ignores_the_period():
    r = await reports.training_by_attribute(FakeKB(), "main", "department", campaign="onboarding", start_date="2027-01-01")
    assert {x["value"]: x["total"] for x in r["rows"]} == {"Finance": 2} and "Onboarding" in r["headline"]
    day = await reports.training_by_attribute(FakeKB(), "main", "department", campaign_date="2026-09-01")
    # a day with two campaigns: both count, as a day's rollout does (Eka's 2025 enrolment is in one of them)
    assert day["totals"]["total"] == 5 and "Onboarding + Refresher" in day["headline"]


# ---------------------------------------------------------------- per manager

async def test_managers_and_their_teams():
    r = await reports.manager_report(FakeKB(), "main")
    rows = {x["manager"]: x for x in r["rows"]}
    # Rina: Ana (Past Due, failed twice) and Budi; Dodi is archived
    assert rows["Rina"] == {"manager": "Rina", "team": 2, "people_with_past_due": 1, "past_due_modules": 1,
                            "people_who_failed_phishing": 1, "failed_phishing_emails": 2}
    assert rows["Sari"]["people_who_failed_phishing"] == 1 and "1 active people have no manager" in r["headline"]
    team = await reports.manager_report(FakeKB(), "main", "rina")
    assert team["mode"] == "team" and [p["name"] for p in team["rows"]] == ["Ana A", "Budi B"]
    assert team["rows"][0]["past_due_modules"] == 1 and team["rows"][0]["failed_phishing_emails"] == 2


async def test_manager_names_that_match_nothing_or_several():
    none = await reports.manager_report(FakeKB(), "main", "Zed")
    assert none["error"] is True and "Rina" in none["message"]

    class TwoRinas(FakeKB):
        async def list_users(self, console, status=None, group_id=None, max_records=None):
            return [dict(u, manager_name="Rina Putri") if u["id"] == 12 else dict(u) for u in USERS if status is None or u["status"] == status]

    ask = await reports.manager_report(TwoRinas(), "main", "rin")
    assert ask["ask_user"] is True and ask["managers"] == ["Rina", "Rina Putri"]

    class NoManagers(FakeKB):
        async def list_users(self, console, status=None, group_id=None, max_records=None):
            return [dict(u, manager_name=None) for u in USERS if status is None or u["status"] == status]

    assert "No active user has a manager_name" in (await reports.manager_report(NoManagers(), "main"))["message"]


# ---------------------------------------------------------------- one group

async def test_group_report_in_full():
    r = await reports.group_report(FakeKB(), "main", "finance", start_date="2026-01-01")
    assert r["group"]["name"] == "Finance" and r["group"]["active_members"] == 2 and r["group"]["risk_level"] == "High"
    # Ana and Budi over both tests: 3 emails, Ana fails twice (a repeat clicker)
    assert r["phishing"]["delivered"] == 3 and r["phishing"]["failed"] == 2
    assert r["repeat_clickers"] == [{"name": "Ana A", "failed_phishing_emails": 2}]
    assert r["training"]["total"] == 3 and r["training"]["past_due"] == 1
    assert [m["name"] for m in r["rows"]] == ["Ana A", "Budi B"] and "Group Finance" in r["risk_trend"]["headline"]


async def test_group_report_names():
    ask = await reports.group_report(FakeKB(), "main", "fin")
    assert ask["ask_user"] is True and ask["groups"] == ["Finance", "Finance Jakarta"]
    assert (await reports.group_report(FakeKB(), "main", "Marketing"))["error"] is True
    assert (await reports.group_report(FakeKB(), "main", ""))["error"] is True


# ---------------------------------------------------------------- the organisation

async def test_organisation_summary_has_every_group_side_by_side():
    r = await reports.organisation_summary(FakeKB(), "main", start_date="2026-01-01")
    assert [g["group"] for g in r["rows"]] == ["Finance", "Finance Jakarta", "IT"]   # riskiest first
    finance = r["rows"][0]
    assert finance["people"] == 2 and finance["past_due"] == 1 and finance["risk_level"] == "High" and finance["small_sample"] is True
    assert r["risk"]["current"] == {"score": 38.0, "level": "Low"} and r["phishing"]["delivered"] == 5
    assert "38.0 (Low)" in r["headline"]


@pytest.mark.parametrize("tool", ["phishing_by_attribute", "training_by_attribute", "manager_report", "organisation_summary"])
async def test_reports_refuse_bad_dates(tool):
    r = await getattr(reports, tool)(FakeKB(), "main", start_date="Oktober")
    assert r["error"] is True and "must be a date" in r["message"]


async def test_reports_on_an_account_with_no_tests():
    class NoTests(FakeKB):
        async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
            return []

    assert (await reports.phishing_by_attribute(NoTests(), "main"))["error"] is True
    summary = await reports.organisation_summary(NoTests(), "main")
    assert summary["phishing"]["delivered"] == 0 and "no phishing test" in summary["headline"]
