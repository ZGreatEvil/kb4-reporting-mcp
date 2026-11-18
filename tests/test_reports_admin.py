from datetime import date as real_date

import pytest

from kb4_mcp import reports

USERS = [
    {"id": 10, "first_name": "Ana", "last_name": "A", "status": "active", "groups": [1], "current_risk_score": 50.0},
    {"id": 11, "first_name": "Budi", "last_name": "B", "status": "active", "groups": [1], "current_risk_score": 30.0},
    {"id": 12, "first_name": "Citra", "last_name": "C", "status": "active", "groups": [2], "current_risk_score": 20.0},
]
ACCOUNT = {"name": "Example", "subscription_level": "Diamond", "subscription_end_date": "2025-07-17", "number_of_seats": 2,
           "current_risk_score": 38.0, "admins": [{"id": 1, "first_name": "Rina", "last_name": "Admin", "email": "rina@example.com"},
                                                  {"id": 2, "first_name": "", "last_name": None, "email": "it-admin@example.com"}]}
GROUPS = [{"id": 1, "name": "Finance", "member_count": 2, "current_risk_score": 50.0, "status": "active"},
          {"id": 2, "name": "IT", "member_count": 1, "current_risk_score": 30.0, "status": "active"}]
TESTS = [{"pst_id": 100, "name": "October test", "started_at": "2026-10-05T00:00:00Z"},
         {"pst_id": 101, "name": "September test", "started_at": "2026-09-05T00:00:00Z"}]


def rec(uid, clicked=False):
    return {"user": {"id": uid}, "delivered_at": "2026-10-05T01:00:00Z", "clicked_at": "x" if clicked else None}


RECIPIENTS = {100: [rec(10, True), rec(11), rec(12)], 101: [rec(10, True)]}
POLICIES = [{"policy_id": 1, "name": "Password Policy"}, {"policy_id": 2, "name": "Acceptable Use"}]
ENROLMENTS = [
    {"user": {"id": 10}, "module_name": "Password Policy", "content_type": "Policy", "policy_acknowledged": True, "status": "Passed"},
    {"user": {"id": 11}, "module_name": "Password Policy", "content_type": "Policy", "policy_acknowledged": False, "status": "Passed"},
    {"user": {"id": 12}, "module_name": "Acceptable Use", "content_type": "Store Purchase", "policy_acknowledged": False, "status": "Not Started"},
    {"user": {"id": 10}, "module_name": "Danger Zone", "content_type": "Store Purchase", "policy_acknowledged": False, "status": "Passed",
     "enrollment_date": "2026-10-06T00:00:00Z", "campaign_id": 7},
]


class FakeKB:
    async def get_account(self, console):
        return dict(ACCOUNT)

    async def get_account_risk_history(self, console, full=False):
        return [{"date": "2026-10-01", "risk_score": 40.0}, {"date": "2026-11-01", "risk_score": 38.0}]

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u["status"] == status]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [dict(t) for t in TESTS]

    async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
        return [dict(r) for r in RECIPIENTS[pst_id]]

    async def list_training_enrollments(self, console, *args, **kwargs):
        return [dict(e) for e in ENROLMENTS]

    async def list_policies(self, console, max_records=None):
        return [dict(p) for p in POLICIES]


@pytest.fixture
def today(monkeypatch):
    class Today(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 11, 16)

    monkeypatch.setattr(reports, "date", Today)


async def test_subscription_status_says_an_ended_subscription_and_seats_over(today):
    r = await reports.subscription_status(FakeKB(), "main")
    assert "days_left" not in r and r["days_since_end"] == 487 and "ended on 2025-07-17 (487 days ago)" in r["headline"]
    assert r["seats_licensed"] == 2 and r["active_users"] == 3 and r["users_over_seats"] == 1
    # admins by name only, never their emails
    # live: an admin with no name in KnowBe4 was shown by email address
    assert r["admins"] == ["Rina Admin", "(admin with no name)"] and "example.com" not in str(r)


async def test_subscription_with_no_end_date():
    class NoEnd(FakeKB):
        async def get_account(self, console):
            return {"subscription_level": "Gold", "number_of_seats": 10}

    r = await reports.subscription_status(NoEnd(), "main")
    assert "days_left" not in r and "days_since_end" not in r and "no end date recorded" in r["headline"] and r["users_over_seats"] == 0


async def test_executive_report_defaults_to_the_last_full_month(today):
    r = await reports.executive_report(FakeKB(), "main")
    assert r["period"] == "2026-10-01 to 2026-10-31"
    assert r["phishing"]["tests"] == 1 and r["phishing"]["latest_test"] == "October test"
    assert [g["group"] for g in r["rows"]] == ["Finance", "IT"] and r["repeat_clickers"] == []
    assert r["subscription"]["seats_licensed"] == 2 and r["headline"].startswith("Security report 2026-10-01 to 2026-10-31: ")


async def test_executive_report_for_a_named_month_and_bad_input(today):
    september = await reports.executive_report(FakeKB(), "main", month="2026-09")
    assert september["period"] == "2026-09-01 to 2026-09-30" and september["phishing"]["latest_test"] == "September test"
    assert (await reports.executive_report(FakeKB(), "main", month="Oktober"))["error"] is True
    # a period passed by the agent works as well
    q3 = await reports.executive_report(FakeKB(), "main", start_date="2026-07-01", end_date="2026-10-31")
    assert q3["phishing"]["tests"] == 2 and q3["repeat_clickers"] == ["Ana A"]


async def test_policy_acknowledgement_per_policy_and_one_policy():
    r = await reports.policy_acknowledgement(FakeKB(), "main")
    rows = {x["policy"]: x for x in r["rows"]}
    # matched by content type and by the policy list's names; Danger Zone is not a policy
    assert set(rows) == {"Password Policy", "Acceptable Use"}
    assert rows["Password Policy"] == {"policy": "Password Policy", "enrolled": 2, "acknowledged": 1, "not_acknowledged": 1,
                                       "percent_acknowledged": 50.0}
    one = await reports.policy_acknowledgement(FakeKB(), "main", "password")
    assert one["not_acknowledged_people"] == ["Budi B"] and one["total_rows"] == 1
    it = await reports.policy_acknowledgement(FakeKB(), "main", group="IT")
    assert [x["policy"] for x in it["rows"]] == ["Acceptable Use"]


async def test_policy_edge_cases():
    class NoPolicies(FakeKB):
        async def list_policies(self, console, max_records=None):
            return []

    none = await reports.policy_acknowledgement(NoPolicies(), "main")
    assert none["rows"] == [] and "no training policies" in none["headline"]
    assert (await reports.policy_acknowledgement(FakeKB(), "main", "travel"))["error"] is True
    ask = await reports.policy_acknowledgement(FakeKB(), "main", "a")   # in both names
    assert ask["ask_user"] is True and ask["policies"] == ["Acceptable Use", "Password Policy"]
