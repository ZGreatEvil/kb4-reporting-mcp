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
