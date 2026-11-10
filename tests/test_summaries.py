from datetime import date

import pytest

from config.settings import AppConfig, ConsoleConfig
from kb4_mcp import summaries

USERS = [
    {"id": 1, "first_name": "Ana", "last_name": "Low", "email": "ana@example.com", "job_title": "Clerk", "department": "Finance", "status": "active", "current_risk_score": 10.0, "phish_prone_percentage": 0.0},
    {"id": 2, "first_name": "Budi", "last_name": "High", "email": "budi@example.com", "job_title": "IT Admin", "department": "IT", "status": "active", "current_risk_score": 80.5, "phish_prone_percentage": 50.0},
    {"id": 3, "first_name": "Citra", "last_name": "Mid", "email": "citra@example.com", "job_title": "Analyst", "department": "IT", "status": "active", "current_risk_score": 40.0, "phish_prone_percentage": 25.0},
    {"id": 4, "first_name": "Dewi", "last_name": "None", "email": "dewi@example.com", "job_title": "Intern", "department": "HR", "status": "active", "current_risk_score": None, "phish_prone_percentage": None},
]

TESTS = [
    {"pst_id": 11, "campaign_id": 1, "name": "Old test", "started_at": "2026-01-05T08:00:00.000Z", "status": "Closed", "delivered_count": 50, "clicked_count": 10, "data_entered_count": 1, "reported_count": 5, "phish_prone_percentage": 0.2},
    {"pst_id": 12, "campaign_id": 1, "name": "Newest test", "started_at": "2026-10-01T08:00:00.000Z", "status": "In Progress", "delivered_count": 55, "clicked_count": 2, "data_entered_count": 0, "reported_count": 9, "phish_prone_percentage": 0.036},
    {"pst_id": 13, "campaign_id": 2, "name": "Worst test", "started_at": "2026-05-01T08:00:00.000Z", "status": "Closed", "delivered_count": 40, "clicked_count": 20, "data_entered_count": 4, "reported_count": 1, "phish_prone_percentage": 1.25},
]

CAMPAIGNS = [
    {"campaign_id": 101, "name": "Q1 training", "status": "Closed", "start_date": "2026-01-10T00:00:00.000Z", "end_date": "2026-02-10T00:00:00.000Z", "completion_percentage": 90.0},
    {"campaign_id": 102, "name": "Q3 training", "status": "In Progress", "start_date": "2026-07-01T00:00:00.000Z", "end_date": None, "completion_percentage": 60.0},
    {"campaign_id": 103, "name": "Undated", "status": "Created", "start_date": None, "end_date": None, "completion_percentage": None},
]


class FakeKB:
    def __init__(self):
        self.calls = []

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        self.calls.append(("list_users", console, status))
        return [u for u in USERS if status is None or u["status"] == status]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return list(TESTS)

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [dict(c) for c in CAMPAIGNS]

    async def list_training_enrollments(self, console, **kwargs):
        self.calls.append(("enrollments", kwargs))
        return [{"campaign_id": 101, "status": "Passed"}, {"campaign_id": 101, "status": "Past Due"},
                {"campaign_id": 102, "status": "Past Due"}, {"campaign_id": None, "status": "Passed"}]

    async def get_account(self, console):
        if console == "broken":
            raise RuntimeError("boom")
        return {"name": console, "current_risk_score": {"main": 39.4, "second": 55.1, "broken": 0}[console]}


async def test_top_users_ranked_and_unscored_counted():
    result = await summaries.top_users_by_risk(FakeKB(), "main", limit=2)
    assert [u["id"] for u in result["users"]] == [2, 3]
    assert [u["rank"] for u in result["users"]] == [1, 2]
    assert result["users_considered"] == 4
    assert result["users_without_score"] == 1
    assert result["users"][0]["name"] == "Budi High"


@pytest.mark.parametrize("limit,expected", [(0, 1), (-5, 1), (999, 3), (None, 3)])
async def test_limit_is_clamped(limit, expected):
    result = await summaries.top_users_by_risk(FakeKB(), "main", limit=limit)
    assert len(result["users"]) == expected


async def test_empty_status_means_all_users():
    kb = FakeKB()
    await summaries.top_users_by_risk(kb, "main", status="")
    assert kb.calls[-1] == ("list_users", "main", None)


@pytest.mark.parametrize("query,ids", [
    ("budi", [2]),
    ("IT admin", [2]),
    ("example.com", [1, 2, 3, 4]),
    ("citra mid", [3]),
    ("nobody", []),
])
async def test_find_user(query, ids):
    result = await summaries.find_user(FakeKB(), "main", query)
    assert [m["id"] for m in result["matches"]] == ids
    assert result["match_count"] == len(ids)


async def test_find_user_empty_query():
    result = await summaries.find_user(FakeKB(), "main", "   ")
    assert result["matches"] == []


async def test_phishing_latest_first():
    result = await summaries.phishing_campaign_summary(FakeKB(), "main")
    assert [t["pst_id"] for t in result["tests"]] == [12, 13, 11]
    assert result["tests"][0]["started_at"] == "2026-10-01"
    assert result["total_security_tests"] == 3


async def test_phishing_highest_ppp():
    result = await summaries.phishing_campaign_summary(FakeKB(), "main", limit=1, sort="highest_ppp")
    assert result["tests"][0]["name"] == "Worst test"
    assert result["sort"] == "highest_ppp"


async def test_phishing_fraction_becomes_percent():
    # the api's test-level value is a fraction and can exceed 1
    result = await summaries.phishing_campaign_summary(FakeKB(), "main", sort="highest_ppp")
    assert [t["phish_prone_percent"] for t in result["tests"]] == [125.0, 20.0, 3.6]
    assert "phish_prone_percentage" not in result["tests"][0]


async def test_phishing_unknown_sort_falls_back_to_latest():
    result = await summaries.phishing_campaign_summary(FakeKB(), "main", sort="bogus")
    assert result["sort"] == "latest"


async def test_training_newest_first_with_average():
    result = await summaries.training_completion_summary(FakeKB(), "main")
    assert [c["campaign_id"] for c in result["campaigns"]] == [102, 101, 103]
    assert result["average_completion_percentage"] == 75.0


async def test_training_filters():
    kb = FakeKB()
    by_id = await summaries.training_completion_summary(kb, "main", campaign_id=101)
    assert [c["campaign_id"] for c in by_id["campaigns"]] == [101]
    ranged = await summaries.training_completion_summary(kb, "main", start_date="2026-06-01", end_date="2026-12-31")
    assert [c["campaign_id"] for c in ranged["campaigns"]] == [102]
    none = await summaries.training_completion_summary(kb, "main", campaign_id=999)
    assert none["campaigns"] == [] and none["average_completion_percentage"] is None


async def test_training_campaigns_carry_their_enrolment_statuses():
    # the model once guessed why a campaign was at 0%; the statuses say why
    kb = FakeKB()
    result = await summaries.training_completion_summary(kb, "main")
    by_id = {c["campaign_id"]: c["enrolments_by_status"] for c in result["campaigns"]}
    assert by_id == {102: {"Past Due": 1}, 101: {"Passed": 1, "Past Due": 1}, 103: {}}
    assert ("enrollments", {"exclude_archived_users": True, "include_campaign_id": True}) in kb.calls
    assert "do not guess" in result["note"]


async def test_compare_consoles(monkeypatch):
    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    monkeypatch.setenv("KB4_T_SECOND", "real-token")
    monkeypatch.setenv("KB4_T_BROKEN", "real-token")
    monkeypatch.setenv("KB4_T_OFF", "xxxxxxxx")
    cfg = AppConfig(consoles={
        "main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN"),
        "second": ConsoleConfig(display_name="Second", api_key_env="KB4_T_SECOND"),
        "broken": ConsoleConfig(display_name="Broken", api_key_env="KB4_T_BROKEN"),
        "off": ConsoleConfig(display_name="Off", api_key_env="KB4_T_OFF"),
    })
    result = await summaries.compare_consoles_risk(FakeKB(), cfg)
    assert [c["console"] for c in result["consoles"]] == ["second", "main"]
    reasons = {u["console"]: u["reason"] for u in result["unavailable"]}
    assert reasons == {"broken": "request failed (RuntimeError)", "off": "no API key configured"}


# readable summaries: levels, trends, why-signals, paging



@pytest.mark.parametrize("score,level", [(10, "Low"), (40, "Low"), (40.24, "Low"), (40.5, "Medium"), (47, "Medium"), (47.4, "Medium"), (48, "High"), (53, "High"), (53.6, "Critical"), (54, "Critical"), (90, "Critical"), (None, None)])
def test_risk_levels(score, level):
    assert summaries.risk_level(score) == level


HISTORY = [
    {"date": "2026-08-03T00:00:00.000Z", "risk_score": 45.123456},
    {"date": "2026-10-05T00:00:00.000Z", "risk_score": 42.0},
    {"date": "2026-10-26T00:00:00.000Z", "risk_score": 40.5},
    {"date": "2026-11-02T00:00:00.000Z", "risk_score": 39.39812},
]


def test_history_stats():
    stats = summaries._history_stats(HISTORY, today=date(2026, 11, 2))
    assert stats["current_score"] == 39.4 and stats["current_level"] == "Low"
    # 30 days before 2026-11-02 is 2026-10-03; the newest earlier point (2026-08-03) is too old to stand for it
    assert stats["change_vs_30_days_ago"] is None
    # 90 days before is 2026-08-04; 2026-08-03 is close enough
    assert stats["change_vs_90_days_ago"] == {"from_date": "2026-08-03", "from_score": 45.12, "to_score_now": 39.4, "change": -5.73}
    assert stats["data_gap"] is None
    assert stats["weekly_snapshots_last_3_months"] == {"average": 40.63, "lowest": 39.4, "highest": 42.0}
    assert stats["newest_weekly_snapshot"] == {"date": "2026-11-02", "score": 39.4}
    assert summaries._history_stats([])["points_available"] == 0


def test_trend_uses_live_score_when_snapshot_lags():
    # the live account score was 39.4 while the newest weekly snapshot still said 45.25
    history = [{"date": "2026-10-05T00:00:00.000Z", "risk_score": 45.8}, {"date": "2026-11-02T00:00:00.000Z", "risk_score": 45.25}]
    stats = summaries._history_stats(history, today=date(2026, 11, 6), current=39.398)
    assert stats["current_score"] == 39.4 and stats["current_level"] == "Low"
    assert stats["change_vs_30_days_ago"]["change"] == -6.4
    assert stats["newest_weekly_snapshot"]["score"] == 45.25


class RichKB(FakeKB):
    async def get_user(self, console, user_id):
        return USERS[1]

    async def get_user_risk_history(self, console, user_id, full=False):
        return list(HISTORY)

    async def list_training_enrollments(self, console, user_id=None, **kw):
        return [{"status": "Past Due"}, {"status": "Past Due"}, {"status": "Passed"}]

    async def get_account_risk_history(self, console, full=False):
        return list(HISTORY)

    async def get_account(self, console):
        return {"name": "Acct", "current_risk_score": 39.39812}


async def test_user_risk_summary_has_why_signals():
    s = await summaries.user_risk_summary(RichKB(), "main", 2)
    assert s["user"]["name"] == "Budi High" and s["user"]["risk_level"] == "Critical"
    w = s["why_signals"]
    assert (w["phish_prone_percent"], w["training_enrollments"], w["training_by_status"]) == (50.0, 3, {"Past Due": 2, "Passed": 1})
    assert w["phish_prone_vs_benchmark"]["comparison"].startswith("higher than every KnowBe4 global benchmark")
    assert s["risk_trend"]["current_score"] == 80.5 and s["risk_trend"]["current_level"] == "Critical"
    assert "Low 10-40" in s["scale"]


async def test_account_overview():
    s = await summaries.account_risk_overview(RichKB(), "main")
    assert s["current"] == {"score": 39.4, "level": "Low"}
    assert s["risk_trend"]["current_score"] == 39.4
    w = s["why_signals"]
    assert w["active_users"] == 4 and w["users_who_failed_a_phishing_test"] == 2
    assert w["average_user_phish_prone_percent"] == 25.0
    assert w["users_by_risk_level"] == {"Low": 2, "Critical": 1}


async def test_list_users_page_and_next():
    capped = await summaries.list_users_page(FakeKB(), "main", limit=100)
    assert len(capped["users"]) == 4  # only 4 fake users; the cap is 20
    first = await summaries.list_users_page(FakeKB(), "main", limit=2)
    assert first["showing"] == "1-2 of 4" and first["next_offset"] == 2
    assert [u["id"] for u in first["users"]] == [2, 3]
    assert [u["number"] for u in first["users"]] == [1, 2]
    second = await summaries.list_users_page(FakeKB(), "main", offset=first["next_offset"], limit=2)
    assert second["showing"] == "3-4 of 4" and second["next_offset"] is None
    by_name = await summaries.list_users_page(FakeKB(), "main", sort="name")
    assert [u["name"] for u in by_name["users"]][:2] == ["Ana Low", "Budi High"]
    past_end = await summaries.list_users_page(FakeKB(), "main", offset=10)
    assert past_end["users"] == [] and past_end["next_offset"] is None


def test_user_rows_are_rounded_and_readable():
    row = summaries._user_row({"id": 1, "first_name": "A", "current_risk_score": 52.0618896484375, "phish_prone_percentage": 11.11111})
    assert row["risk_score"] == 52.06 and row["risk_level"] == "High" and row["phish_prone_percent"] == 11.11
    assert "current_risk_score" not in row


async def test_find_user_tells_model_to_ask_when_several_match():
    several = await summaries.find_user(FakeKB(), "main", "IT")
    assert several["match_count"] > 1 and "ask which one" in several["next_step"]
    one = await summaries.find_user(FakeKB(), "main", "budi")
    assert "user_risk_summary" in one["next_step"]



def test_stale_history_is_flagged_not_described_as_recent():
    # a person whose snapshots stopped in june, asked about in november
    history = [{"date": "2026-05-04T00:00:00.000Z", "risk_score": 46.08}, {"date": "2026-06-15T00:00:00.000Z", "risk_score": 40.0}]
    stats = summaries._history_stats(history, today=date(2026, 11, 6), current=37.92)
    assert stats["change_vs_30_days_ago"] is None and stats["change_vs_90_days_ago"] is None
    assert stats["weekly_snapshots_last_3_months"] is None
    assert "No weekly snapshots since 2026-06-15" in stats["data_gap"]


@pytest.mark.parametrize("value,expected", [
    (14.31, "higher than the figure after 12 months of training (4.2%) but lower than the figure after 90 days of training (20.1%)"),
    (100, "higher than every KnowBe4 global benchmark, including before training (33.2%)"),
    (0, "lower than every KnowBe4 global benchmark, including after 12 months of training (4.2%)"),
    (25, "higher than the figure after 90 days of training (20.1%) but lower than the figure before training (33.2%)"),
])
def test_ppp_benchmark_comparison(value, expected):
    assert summaries.ppp_vs_benchmark(value)["comparison"] == expected
    assert summaries.ppp_vs_benchmark(None) is None


async def test_find_user_flags_ask_user():
    assert (await summaries.find_user(FakeKB(), "main", "IT"))["ask_user"] is True
    assert (await summaries.find_user(FakeKB(), "main", "budi"))["ask_user"] is False


def test_trend_headline_states_each_period_exactly():
    stats = {"points_available": 9, "current_score": 40.24, "current_level": "Low",
             "change_vs_30_days_ago": None,
             "change_vs_90_days_ago": {"from_score": 48.39, "change": -8.15}, "data_gap": None}
    assert summaries._trend_headline("Rina", stats) == (
        "Rina: risk score now 40.24 (Low). No snapshot from 30 days ago. 90 days ago it was 48.39 (change -8.15)."
    )
    assert summaries._trend_headline("Rina", {"points_available": 0}) == "Rina: no risk score history available."


async def test_overview_headline_states_users_per_level():
    class KB(FakeKB):
        async def get_account_risk_history(self, console, full=False):
            return []

    result = await summaries.account_risk_overview(KB(), "main")
    # active users: 10.0 Low, 80.5 Critical, 40.0 Low, one without a score
    assert result["headline"].endswith("Active users per risk level: Low 2, Critical 1 (4 in total); 2 of them failed a phishing test.")
