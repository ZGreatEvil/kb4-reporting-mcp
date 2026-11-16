import pytest

from kb4_mcp import lookups

GROUPS = [
    {"id": 1, "name": "Finance", "group_type": "console_group", "member_count": 12, "current_risk_score": 44.2, "status": "active"},
    {"id": 2, "name": "Finance Jakarta", "group_type": "console_group", "member_count": 4, "current_risk_score": 51.0, "status": "active"},
    {"id": 3, "name": "Team-Security", "group_type": "smart_group", "member_count": 30, "current_risk_score": 38.0, "status": "active"},
    {"id": 4, "name": "Old team", "group_type": "console_group", "member_count": 0, "current_risk_score": None, "status": "archived"},
]
PHISHING = [
    {"campaign_id": 10, "name": "Monthly phish", "status": "Active", "frequency": "Monthly", "last_run": "2026-10-05T03:00:00Z",
     "create_date": "2025-01-01T00:00:00Z", "psts_count": 12, "last_phish_prone_percentage": 0.25, "groups": [{"name": "Finance"}]},
    {"campaign_id": 11, "name": "Invoice test", "status": "Closed", "frequency": "One Time", "last_run": None,
     "create_date": "2024-03-01T00:00:00Z", "psts_count": 0, "last_phish_prone_percentage": None, "groups": []},
]
TRAINING = [
    {"campaign_id": 20, "name": "Awareness 2026", "status": "In Progress", "start_date": "2026-10-07T07:00:00Z",
     "end_date": "2026-11-07T07:00:00Z", "completion_percentage": 57.4, "groups": [{"name": "Finance"}]},
]
USERS = [
    {"id": 100, "status": "active", "department": "Finance", "job_title": "Analyst", "manager_name": "Rina"},
    {"id": 101, "status": "active", "department": "Finance", "job_title": "", "manager_name": "Rina"},
    {"id": 102, "status": "active", "department": "IT", "job_title": "Engineer", "manager_name": None},
    {"id": 103, "status": "active", "department": "  ", "job_title": "Engineer"},
]


class FakeKB:
    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS if status is None or g["status"] == status]

    async def list_phishing_campaigns(self, console, campaign_type=None, max_records=None):
        return [dict(c) for c in PHISHING]

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [dict(c) for c in TRAINING]

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u["status"] == status]


async def test_all_groups_largest_first():
    r = await lookups.find_group(FakeKB(), "main")
    assert [g["name"] for g in r["groups"]] == ["Team-Security", "Finance", "Finance Jakarta"]
    assert r["headline"] == "3 groups (active)." and r["ask_user"] is False
    assert r["groups"][1] == {"id": 1, "name": "Finance", "type": "console_group", "members": 12, "risk_score": 44.2,
                              "risk_level": "Medium", "status": "active"}


async def test_an_exact_group_name_is_chosen_and_a_vague_one_asks():
    exact = await lookups.find_group(FakeKB(), "main", "finance")
    assert exact["chosen"] == 1 and exact["ask_user"] is False and exact["groups"][0]["name"] == "Finance"
    vague = await lookups.find_group(FakeKB(), "main", "fin")
    assert vague["ask_user"] is True and "chosen" not in vague and vague["total"] == 2
    # the text anywhere in the name, not only at a word start
    assert [g["name"] for g in (await lookups.find_group(FakeKB(), "main", "security"))["groups"]] == ["Team-Security"]


async def test_group_search_edge_cases():
    none = await lookups.find_group(FakeKB(), "main", "marketing")
    assert none["total"] == 0 and none["headline"].startswith("No group name matches 'marketing'")
    archived = await lookups.find_group(FakeKB(), "main", status="archived")
    assert [g["name"] for g in archived["groups"]] == ["Old team"]
    capped = await lookups.find_group(FakeKB(), "main", limit=1)
    assert capped["shown"] == 1 and capped["truncated"] is True
    bad = await lookups.find_group(FakeKB(), "main", status="gone")
    assert bad["error"] is True

    class Empty(FakeKB):
        async def list_groups(self, console, status=None, max_records=None):
            return []

    assert (await lookups.find_group(Empty(), "main"))["headline"] == "This console has no groups."


async def test_phishing_campaigns_newest_first_with_percent():
    r = await lookups.find_campaign(FakeKB(), "main")
    assert [c["campaign_id"] for c in r["campaigns"]] == [10, 11]
    # the api gives a fraction on campaigns, like on tests
    assert r["campaigns"][0]["last_phish_prone_percent"] == 25.0 and r["campaigns"][0]["groups"] == ["Finance"]
    # never run: dated by its creation
    assert r["campaigns"][1]["last_run"] is None and r["campaigns"][1]["created"] == "2024-03-01"


async def test_campaigns_by_name_and_period_and_kind():
    october = await lookups.find_campaign(FakeKB(), "main", start_date="2026-10-01", end_date="2026-10-31")
    assert [c["campaign_id"] for c in october["campaigns"]] == [10] and "2026-10-01 to 2026-10-31" in october["headline"]
    named = await lookups.find_campaign(FakeKB(), "main", "invoice")
    assert [c["campaign_id"] for c in named["campaigns"]] == [11]
    training = await lookups.find_campaign(FakeKB(), "main", "awareness", kind="training")
    assert training["campaigns"][0]["completion_percent"] == 57.4 and training["campaigns"][0]["start_date"] == "2026-10-07"
    none = await lookups.find_campaign(FakeKB(), "main", "nothing like it")
    assert none["total"] == 0 and none["headline"].startswith("No phishing campaign(s) matching")


@pytest.mark.parametrize("args,message", [({"kind": "email"}, "kind must be"), ({"start_date": "Oktober"}, "must be a date")])
async def test_campaign_search_bad_input(args, message):
    r = await lookups.find_campaign(FakeKB(), "main", **args)
    assert r["error"] is True and message in r["message"]


async def test_dimension_values_count_people_and_empty_ones():
    r = await lookups.list_dimension_values(FakeKB(), "main", "department")
    assert r["values"] == [{"value": "Finance", "users": 2}, {"value": "IT", "users": 1}]
    # blank text is empty too
    assert r["empty"] == 1 and r["with_value"] == 3 and r["active_users"] == 4
    managers = await lookups.list_dimension_values(FakeKB(), "main", "manager")
    assert managers["attribute"] == "manager_name" and managers["values"] == [{"value": "Rina", "users": 2}] and managers["empty"] == 2
    assert (await lookups.list_dimension_values(FakeKB(), "main", "jabatan"))["attribute"] == "job_title"


async def test_dimension_values_when_nobody_has_one_and_bad_attribute():
    r = await lookups.list_dimension_values(FakeKB(), "main", "location")
    assert r["distinct"] == 0 and r["headline"] == "No active user has a location filled in (4 active users)."
    bad = await lookups.list_dimension_values(FakeKB(), "main", "salary")
    assert bad["error"] is True and "department" in bad["message"]


@pytest.mark.parametrize("name,keys", [
    ("risk score", ["risk_score"]),
    ("phish-prone", ["phish_prone"]),
    ("phish_prone, users_failed", ["phish_prone", "users_failed"]),
    ("risk score dan phish-prone", ["risk_score", "phish_prone"]),
    ("past due", ["training_status"]),
    ("campaign vs test", ["campaign_vs_test"]),
])
def test_metric_names_find_their_definitions(name, keys):
    r = lookups.explain_metric(name, "id")
    assert [d["metric"] for d in r["definitions"]] == keys


def test_definitions_exist_in_both_languages_and_unknown_names_say_so():
    for key, text in lookups.METRICS.items():
        assert text["id"] and text["en"] and text["id"] != text["en"], key
    en = lookups.explain_metric("phish_prone", "en")
    assert en["definitions"][0]["text"].startswith("Phish-prone % = failures")
    # risk levels match the ones the summaries use
    assert "Low 10–40, Medium 41–47, High 48–53, Critical 54–90" in lookups.METRICS["risk_score"]["en"]
    unknown = lookups.explain_metric("salary")
    assert unknown["error"] is True and "risk_score" in unknown["message"]
