import csv

import pytest

from kb4_mcp import outputs, summaries

CAMPAIGNS = [
    {"campaign_id": 1, "name": "Awareness Training ", "start_date": "2026-10-07T07:00:00.000Z", "status": "Completed",
     "groups": [{"group_id": 10, "name": "Group-A1"}, {"group_id": 11, "name": "Group-B1"}], "content": [{"name": "Danger Zone"}]},
    {"campaign_id": 2, "name": "Awareness Training (Language B)", "start_date": "2026-10-07T07:00:00.000Z",
     "status": "Completed", "groups": [{"group_id": 12, "name": "Group-C1"}]},
    {"campaign_id": 3, "name": "Older campaign", "start_date": "2025-01-01T00:00:00.000Z", "status": "Closed",
     "groups": [{"group_id": 10, "name": "Group-A1"}]},
]
GROUPS = [{"id": 10, "name": "Group-A1"}, {"id": 11, "name": "Group-B1"}, {"id": 12, "name": "Group-C1"},
          {"id": 13, "name": "Group-B10"}]
USERS = [
    {"id": 100, "status": "active", "groups": [10]},
    {"id": 101, "status": "active", "groups": [10, 11]},   # in two groups: both rows, once in the totals
    {"id": 102, "status": "active", "groups": [11]},
    {"id": 103, "status": "archived", "groups": [10]},
    {"id": 104, "status": "active", "groups": [12]},
]


def enrol(uid, status, campaign=1):
    return {"campaign_id": campaign, "status": status, "user": {"id": uid}}


ENROLMENTS = [
    enrol(100, "Passed"), enrol(100, "Passed"),
    enrol(101, "Passed"), enrol(101, "Past Due"),          # one Past Due module: Past Due
    enrol(102, "In Progress"), enrol(102, "Not Started"),  # the least finished one counts: Not Started
    enrol(103, "Past Due"), enrol(103, "Past Due"),        # archived
    enrol(104, "Passed", campaign=2),
]


class FakeKB:
    def __init__(self):
        self.calls = []

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [dict(c) for c in CAMPAIGNS]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u["status"] == status]

    async def list_training_enrollments(self, console, *args, **kwargs):
        self.calls.append(kwargs)
        return [dict(e) for e in ENROLMENTS]


QUESTION = "tarik data campaign 2026-10-07 untuk group Group-A1, Group-B1 berapa user complete, in progress, past due"


async def test_the_question_picks_the_campaign_and_its_groups():
    r = await summaries.training_by_group(FakeKB(), "main", campaign_date="2026-10-07", text=QUESTION)
    # two campaigns started that day; only one is aimed at these groups
    assert r["campaign"]["campaign_id"] == 1 and r["campaign"]["modules"] == ["Danger Zone"]
    rows = {g["group"]: g for g in r["groups"]}
    assert set(rows) == {"Group-A1", "Group-B1"}   # "Group-B10" is not "Group-B1"
    assert rows["Group-A1"] == {"group": "Group-A1", "total": 2, "completed": 1, "in_progress": 0, "not_started": 0,
                                     "past_due": 1, "percent_complete": 50.0, "percent_past_due": 50.0,
                                     "archived_not_counted": 1}
    assert rows["Group-B1"]["past_due"] == 1 and rows["Group-B1"]["not_started"] == 1
    assert r["totals"] == {"total": 3, "completed": 1, "in_progress": 0, "not_started": 1, "past_due": 1, "percent_complete": 33.33,
                           "percent_past_due": 33.33}
    assert r["archived_not_counted"] == 1 and r["unknown_groups"] == []
    assert r["headline"] == ("Awareness Training (started 2026-10-07, Completed): 3 people in 2 groups; 1 completed, "
                             "0 in progress, 1 not started, 1 Past Due (33.33% complete). 1 archived people in these groups are not counted.")


async def test_archived_people_counted_when_asked_and_enrolments_mode():
    r = await summaries.training_by_group(FakeKB(), "main", campaign="1", include_archived=True)
    usg2 = next(g for g in r["groups"] if g["group"] == "Group-A1")
    assert usg2["total"] == 3 and usg2["past_due"] == 2 and "archived_not_counted" not in usg2
    by_enrolment = await summaries.training_by_group(FakeKB(), "main", campaign="1", by="enrolment")
    assert by_enrolment["totals"]["total"] == 6 and by_enrolment["counted_by"] == "enrolment"


async def test_a_date_alone_takes_every_campaign_of_that_day():
    r = await summaries.training_by_group(FakeKB(), "main", campaign_date="2026-10-07")
    assert r["campaign"]["campaign_ids"] == [1, 2]
    assert [g["group"] for g in r["groups"]] == ["Group-A1", "Group-B1", "Group-C1"]
    assert r["campaign"]["name"] == "Awareness Training (2 campaigns)"


async def test_groups_across_same_day_campaigns_are_all_reported():
    # live 2026-11-12: a question naming groups from the main campaign and its language versions left five groups out
    r = await summaries.training_by_group(FakeKB(), "main", campaign_date="2026-10-07", text=QUESTION + ", Group-C1")
    rows = {g["group"]: g for g in r["groups"]}
    assert set(rows) == {"Group-A1", "Group-B1", "Group-C1"} and r["campaign"]["campaign_ids"] == [1, 2]
    assert rows["Group-C1"]["completed"] == 1 and rows["Group-C1"]["total"] == 1


async def test_an_ambiguous_name_still_asks_which():
    r = await summaries.training_by_group(FakeKB(), "main", campaign="awareness training")
    assert r["ask_user"] is True and [m["campaign_id"] for m in r["matches"]] == [1, 2]


async def test_a_named_group_outside_these_campaigns_is_listed_not_zeroed():
    r = await summaries.training_by_group(FakeKB(), "main", campaign="1", groups="Group-A1, Group-B10")
    assert [g["group"] for g in r["groups"]] == ["Group-A1"] and r["not_in_these_campaigns"] == ["Group-B10"]


async def test_campaign_by_name_groups_by_list_and_unknown_names():
    r = await summaries.training_by_group(FakeKB(), "main", campaign="language b", groups="Group-C1, Marketing")
    assert r["campaign"]["campaign_id"] == 2 and [g["group"] for g in r["groups"]] == ["Group-C1"]
    assert r["unknown_groups"] == ["Marketing"] and r["totals"]["completed"] == 1


async def test_a_campaign_by_name_uses_its_own_groups():
    r = await summaries.training_by_group(FakeKB(), "main", campaign="older")
    assert r["campaign"]["campaign_id"] == 3 and [g["group"] for g in r["groups"]] == ["Group-A1"]


async def test_no_campaign_named_takes_the_newest():
    r = await summaries.training_by_group(FakeKB(), "main", groups="Group-B1")
    assert r["campaign"]["start_date"] == "2026-10-07" and [g["group"] for g in r["groups"]] == ["Group-B1"]


@pytest.mark.parametrize("args,message", [
    ({"campaign_date": "7 oktober"}, "campaign_date must be a date"),
    ({"campaign_date": "2026-01-01"}, "No training campaign starting 2026-01-01"),
    ({"campaign": "nothing like this"}, "No training campaign named 'nothing like this'"),
])
async def test_bad_campaign_arguments(args, message):
    r = await summaries.training_by_group(FakeKB(), "main", **args)
    assert r["error"] is True and message in r["message"]


async def test_csv_export_has_every_group_and_the_total(tmp_path, monkeypatch):
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)
    r = await outputs.export_csv(FakeKB(), "main", "training_by_group", campaign_date="2026-10-07", text=QUESTION)
    path = tmp_path / r["download_url"].split("/")[-1].split("?")[0]
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0][:6] == ["group", "people", "completed", "in_progress", "not_started", "past_due"]
    assert [row[0] for row in rows[1:]] == ["Group-A1", "Group-B1", "Total (each person once)"]
    # an ambiguous campaign name: the question goes back, no file
    ask = await outputs.export_csv(FakeKB(), "main", "training_by_group", campaign="awareness training")
    assert ask.get("ask_user") is True and "download_url" not in ask


def test_raw_lists_come_newest_first():
    from kb4_mcp.server_impl import _newest_first
    items = [{"name": "a", "start_date": "2025-01-01"}, {"name": "b", "start_date": "2026-10-07"}, {"name": "c", "start_date": None}]
    assert [i["name"] for i in _newest_first(items, "start_date")] == ["b", "a", "c"]
    assert [i["name"] for i in _newest_first(items, "start_date", max_records=1)] == ["b"]
    tests = [{"name": "old", "last_run": None, "create_date": "2024-01-01"}, {"name": "new", "last_run": "2026-10-26"}]
    assert [i["name"] for i in _newest_first(tests, "last_run", "create_date")] == ["new", "old"]


async def test_groups_keep_the_order_of_the_question():
    r = await summaries.training_by_group(FakeKB(), "main", campaign_date="2026-10-07", text="campaign 2026-10-07 grup Group-C1, Group-B1, Group-A1")
    assert [g["group"] for g in r["groups"]] == ["Group-C1", "Group-B1", "Group-A1"]


async def test_a_person_in_two_same_day_campaigns_is_explained():
    # live: four campaigns of 2026-10-07 add up to 945 people, but one person was in two of them: 944 different people
    extra = ENROLMENTS + [enrol(101, "Passed", campaign=2)]

    class KB(FakeKB):
        async def list_training_enrollments(self, console, *args, **kwargs):
            return [dict(e) for e in extra]

    r = await summaries.training_by_group(KB(), "main", campaign_date="2026-10-07", text="grup Group-A1, Group-C1")
    assert r["totals"]["total"] == 3 and r["people_counted_per_campaign"] == 4 and r["people_in_several_campaigns"] == 1
    assert r["headline"].endswith("The campaigns add up to 4 people because 1 person(s) were enrolled in more than one of them.")
