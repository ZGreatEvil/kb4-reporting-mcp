import pytest

from kb4_mcp import outputs, summaries

T = "2026-10-01T08:00:00.000Z"

USERS = [
    {"id": 1, "first_name": "Ana", "last_name": "A", "department": "Finance", "groups": [10], "current_risk_score": 60.0, "phish_prone_percentage": 50.0, "status": "active"},
    {"id": 2, "first_name": "Budi", "last_name": "B", "department": "Finance", "groups": [10, 20], "current_risk_score": 30.0, "phish_prone_percentage": 0.0, "status": "active"},
    {"id": 3, "first_name": "Citra", "last_name": "C", "department": "", "groups": [20], "current_risk_score": 20.0, "phish_prone_percentage": 10.0, "status": "active"},
]
GROUPS = [
    {"id": 10, "name": "Sales", "current_risk_score": 55.2, "member_count": 2},
    {"id": 20, "name": "IT", "current_risk_score": 25.0, "member_count": 2},
    {"id": 30, "name": "Empty", "current_risk_score": 90.0, "member_count": 0},
]
TESTS = [
    {"pst_id": 1, "name": "Old", "started_at": "2026-01-01T08:00:00.000Z", "status": "Closed", "phish_prone_percentage": 0.5},
    {"pst_id": 2, "name": "Mid", "started_at": "2026-05-01T08:00:00.000Z", "status": "Closed", "phish_prone_percentage": 0.5},
    {"pst_id": 3, "name": "New", "started_at": "2026-09-01T08:00:00.000Z", "status": "Closed", "phish_prone_percentage": 1.0},
]


def rec(user_id, name, **events):
    return {"recipient_id": user_id * 100, "user": {"id": user_id, "first_name": name, "last_name": ""}, "delivered_at": T, **events}


RECIPIENTS = {
    1: [rec(1, "Ana", clicked_at=T), rec(2, "Budi")],
    2: [rec(1, "Ana", attachment_opened_at=T), rec(2, "Budi", reported_at=T)],
    3: [rec(1, "Ana", clicked_at=T, data_entered_at=T), rec(2, "Budi", clicked_at=T, reported_at=T), rec(3, "Citra", reported_at=T),
        {"recipient_id": 9, "user": {"id": 9, "first_name": "Bounced"}, "delivered_at": None, "bounced_at": T}],
}
ENROLMENTS = [
    {"status": "Past Due", "module_name": "Phishing 101", "user": {"id": 1, "first_name": "Ana", "last_name": "A"}},
    {"status": "Past Due", "module_name": "Phishing 101", "user": {"id": 2, "first_name": "Budi", "last_name": "B"}},
    {"status": "Past Due", "module_name": "Passwords", "user": {"id": 1, "first_name": "Ana", "last_name": "A"}},
    {"status": "Passed", "module_name": "Passwords", "user": {"id": 2, "first_name": "Budi", "last_name": "B"}},
]


class FakeKB:
    def __init__(self, users=USERS, tests=TESTS, enrolments=ENROLMENTS):
        self.users, self.tests, self.enrolments = users, tests, enrolments
        self.calls = []

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in self.users]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [dict(t) for t in self.tests]

    async def get_phishing_security_test(self, console, pst_id, campaign_type=None):
        return next(dict(t) for t in self.tests if t["pst_id"] == pst_id)

    async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
        self.calls.append(("recipients", pst_id))
        return [dict(r) for r in RECIPIENTS.get(pst_id, [])]

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return []

    async def list_training_enrollments(self, console, **kwargs):
        self.calls.append(("enrollments", kwargs))
        return [dict(e) for e in self.enrolments]


async def test_groups_ranked_by_knowbe4_score_and_empty_groups_skipped():
    result = await summaries.risk_by_group(FakeKB(), "main")
    assert [g["name"] for g in result["groups"]] == ["Sales", "IT"]
    sales = result["groups"][0]
    assert sales["risk_level"] == "Critical"
    assert sales["active_users"] == 2
    assert sales["average_phish_prone_percent"] == 25.0
    assert sales["users_who_failed_a_phishing_test"] == 1


async def test_department_breakdown_averages_users_and_ignores_blanks():
    result = await summaries.risk_by_group(FakeKB(), "main", by="department")
    assert result["groups"] == [{
        "rank": 1, "name": "Finance", "active_users": 2, "risk_score": 45.0, "risk_level": "Medium",
        "average_phish_prone_percent": 25.0, "users_who_failed_a_phishing_test": 1,
    }]


async def test_department_breakdown_says_so_when_the_field_is_empty():
    blank = [{**u, "department": None} for u in USERS]
    result = await summaries.risk_by_group(FakeKB(users=blank), "main", by="department")
    assert result["groups"] == []
    assert "empty" in result["note"]


async def test_repeat_failures_counts_tests_failed_per_person():
    kb = FakeKB()
    result = await summaries.repeat_phishing_failures(kb, "main", tests=3)
    assert result["tests_checked"] == 3
    assert result["failed_two_or_more_tests"] == 1
    top = result["repeat_failures"][0]
    assert (top["name"], top["failed"], top["last_failed"]) == ("Ana", "3 of 3 tests", "2026-09-01")
    assert top["what_they_did"] == {"clicked the link": 2, "opened the attachment": 1, "entered data": 1}
    assert result["failed_exactly_once"] == 1  # budi
    assert result["never_failed"] == 1  # citra; the bounced recipient is not counted
    assert result["people_who_received_a_test"] == 3


async def test_repeat_failures_only_fetches_the_latest_tests():
    kb = FakeKB()
    result = await summaries.repeat_phishing_failures(kb, "main", tests=2)
    assert [c[1] for c in kb.calls] == [3, 2]
    assert result["tests_period"] == "2026-05-01 to 2026-09-01"


async def test_repeat_failures_with_no_tests():
    result = await summaries.repeat_phishing_failures(FakeKB(tests=[]), "main")
    assert result["tests_checked"] == 0
    assert result["tests_period"] is None
    assert result["repeat_failures"] == []


async def test_test_detail_uses_latest_and_computes_report_rate():
    result = await summaries.phishing_test_detail(FakeKB(), "main")
    assert result["pst_id"] == 3
    assert result["delivered"] == 3  # bounced one left out
    assert result["people_who_failed"] == 2
    assert result["people_who_failed_percent"] == 66.67
    assert result["reported"] == 2
    assert result["report_rate_percent"] == 66.67
    assert result["phish_prone_percent"] == 100.0
    assert result["failures_by_action"] == {"clicked the link": 2, "entered data": 1}
    budi = next(p for p in result["failed_people"] if p["name"] == "Budi")
    assert budi["also_reported"] is True


async def test_test_detail_for_a_given_test_and_when_there_are_none():
    assert (await summaries.phishing_test_detail(FakeKB(), "main", pst_id=1))["name"] == "Old"
    empty = await summaries.phishing_test_detail(FakeKB(tests=[]), "main")
    assert empty["error"] is True


async def test_overdue_training_per_person_and_module():
    kb = FakeKB()
    result = await summaries.overdue_training(kb, "main")
    assert kb.calls == [("enrollments", {"exclude_archived_users": True})]
    assert result["past_due"] == 3
    assert result["past_due_percent"] == 75.0
    assert result["people_with_past_due_training"] == 2
    assert result["most_overdue_people"][0] == {"rank": 1, "id": 1, "name": "Ana A", "past_due": 2}
    assert result["most_overdue_modules"][0] == {"module": "Phishing 101", "past_due": 2}


async def test_overdue_training_with_no_enrolments():
    result = await summaries.overdue_training(FakeKB(enrolments=[]), "main")
    assert result["past_due"] == 0
    assert result["past_due_percent"] is None


async def test_groups_chart_is_drawn(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "CHART_DIR", tmp_path)
    result = await outputs.make_chart(FakeKB(), "main", "groups", "en")
    assert result["title"] == "Top 2 groups by risk score"
    assert [g["name"] for g in result["summary"]["groups"]] == ["Sales", "IT"]
    assert len(list(tmp_path.glob("*.png"))) == 1


async def test_chart_without_data_says_so_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "CHART_DIR", tmp_path)
    result = await outputs.make_chart(FakeKB(tests=[]), "main", "phishing_tests", "id")
    assert result["error"] is True
    assert "Belum ada data" in result["message"]
    assert list(tmp_path.glob("*.png")) == []


async def test_chart_figure_is_closed_when_a_fetch_fails(monkeypatch):
    import matplotlib.pyplot as plt

    class Broken(FakeKB):
        async def list_users(self, *a, **k):
            raise RuntimeError("down")

    before = len(plt.get_fignums())
    try:
        await outputs.make_chart(Broken(), "main", "top_users")
    except RuntimeError:
        pass
    assert len(plt.get_fignums()) == before


async def test_every_new_tool_has_a_headline_built_from_the_data():
    kb = FakeKB()
    groups = await summaries.risk_by_group(kb, "main")
    assert groups["headline"] == "Riskiest group: Sales (risk score 55.2, Critical) with 2 active users, out of 2 groups that have active users."
    repeat = await summaries.repeat_phishing_failures(kb, "main", tests=3)
    assert repeat["headline"] == "1 of 3 people failed two or more of the 3 phishing tests checked; 1 failed once and 1 never failed."
    detail = await summaries.phishing_test_detail(kb, "main")
    assert detail["headline"] == 'Phishing test "New" (2026-09-01): 2 of 3 people failed it (66.67%) and 2 reported it (report rate 66.67%).'
    overdue = await summaries.overdue_training(kb, "main")
    assert overdue["headline"] == "3 of 4 training enrolments (75.0%) are Past Due, held by 2 people; Ana A has the most (2)."
    for result in (groups, repeat, detail, overdue):
        assert "do not add advice" in result["note"]


async def test_headlines_when_there_is_nothing_to_report():
    assert (await summaries.overdue_training(FakeKB(enrolments=[]), "main"))["headline"] == "None of the 0 training enrolments is Past Due."
    blank = await summaries.risk_by_group(FakeKB(users=[]), "main")
    assert blank["headline"] == "No groups with active users."


async def test_phishing_summary_keeps_only_tests_in_the_period():
    from kb4_mcp import summaries as s

    class KB(FakeKB):
        async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
            return [{**t, "delivered_count": 10} for t in TESTS]

    result = await s.phishing_campaign_summary(KB(), "main", start_date="2026-05-01")
    assert [t["name"] for t in result["tests"]] == ["New", "Mid"]
    assert result["period"] == "2026-05-01 to today"
    assert result["headline"].startswith("From 2026-05-01 to today: 2 phishing security tests")
    none = await s.phishing_campaign_summary(KB(), "main", start_date="2027-01-01")
    assert none["headline"] == "No phishing security tests from 2027-01-01 to today."


async def test_repeat_failures_and_detail_follow_the_period():
    kb = FakeKB()
    result = await summaries.repeat_phishing_failures(kb, "main", start_date="2026-05-01")
    assert result["tests_checked"] == 2 and result["tests_in_period"] == 2
    assert result["headline"].startswith("From 2026-05-01 to today:")
    detail = await summaries.phishing_test_detail(FakeKB(), "main", end_date="2026-06-30")
    assert detail["name"] == "Mid"  # the latest test inside the period, not the latest overall
    empty = await summaries.phishing_test_detail(FakeKB(), "main", start_date="2027-01-01")
    assert empty["error"] is True and "from 2027-01-01" in empty["message"]


async def test_overdue_training_by_enrolment_date():
    dated = [{**e, "enrollment_date": d} for e, d in zip(ENROLMENTS, ["2025-03-01", "2026-02-01", "2026-03-01", "2026-04-01"], strict=True)]
    result = await summaries.overdue_training(FakeKB(enrolments=dated), "main", start_date="2026-01-01")
    assert result["enrollments"] == 3 and result["past_due"] == 2
    assert result["period"] == "enrolled 2026-01-01 to today"
    assert result["headline"].startswith("Enrolled from 2026-01-01 to today: 2 of 3")


async def test_risk_trend_for_a_period():
    history = [{"date": d, "risk_score": s} for d, s in (("2026-01-05", 50.0), ("2026-04-05", 44.0), ("2026-07-05", 41.0))]

    class KB(FakeKB):
        async def get_account(self, console):
            return {"name": "x", "current_risk_score": 39.4}

        async def get_account_risk_history(self, console, full=False):
            return list(history)

    result = await summaries.account_risk_overview(KB(), "main", start_date="2026-04-01")
    p = result["period"]
    assert (p["snapshots"], p["first_snapshot"], p["last"], p["change"]) == (2, {"date": "2026-04-05", "score": 44.0}, {"date": "now", "score": 39.4}, -4.6)
    assert "From 2026-04-01 to today: 2 weekly snapshots, average 42.5 (lowest 41.0, highest 44.0)" in result["headline"]
    ended = await summaries.account_risk_overview(KB(), "main", start_date="2026-01-01", end_date="2026-04-30")
    assert ended["period"]["last"] == {"date": "2026-04-05", "score": 44.0}  # a past period ends at its own last snapshot
    assert (await summaries.account_risk_overview(KB(), "main"))["period"] is None


async def test_charts_and_exports_follow_the_period(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "CHART_DIR", tmp_path)
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)
    chart = await outputs.make_chart(FakeKB(), "main", "phishing_tests", "en", start_date="2026-05-01")
    assert [x["name"] for x in chart["summary"]["tests"]] == ["Mid", "New"]
    assert chart["title"].endswith("(2026-05-01 – today)") and chart["period"] == "2026-05-01 to today"
    current = await outputs.make_chart(FakeKB(), "main", "groups", "en", start_date="2026-05-01")
    assert current["period"] == "all data"  # today's state has no period
    export = await outputs.export_csv(FakeKB(), "main", "phishing_tests", start_date="2026-05-01", end_date="2026-06-30")
    assert export["rows"] == 1 and export["period"] == "2026-05-01 to 2026-06-30"


@pytest.mark.parametrize("start,end,problem", [
    ("Jan 2026", None, "start_date must be a date written as YYYY-MM-DD"),
    ("2026", None, "start_date must be a date"),
    ("2026-02-30", None, "start_date must be a date"),
    (None, "31/12/2026", "end_date must be a date"),
    ("2026-06-01", "2026-01-01", "start_date 2026-06-01 is after end_date 2026-01-01"),
])
async def test_bad_dates_are_refused_by_every_dated_tool(start, end, problem, tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "CHART_DIR", tmp_path)
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)
    kb = FakeKB()
    calls = [
        summaries.phishing_campaign_summary(kb, "main", start_date=start, end_date=end),
        summaries.repeat_phishing_failures(kb, "main", start_date=start, end_date=end),
        summaries.phishing_test_detail(kb, "main", start_date=start, end_date=end),
        summaries.overdue_training(kb, "main", start_date=start, end_date=end),
        summaries.training_completion_summary(kb, "main", start_date=start, end_date=end),
        outputs.make_chart(kb, "main", "phishing_tests", start_date=start, end_date=end),
        outputs.export_csv(kb, "main", "phishing_tests", start_date=start, end_date=end),
    ]
    for call in calls:
        result = await call
        assert result["error"] is True and problem in result["message"]
    assert list(tmp_path.iterdir()) == []  # nothing drawn or written
