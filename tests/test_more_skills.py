from datetime import date, timedelta

import pytest

from kb4_mcp import outputs, summaries

T = "2026-10-01T08:00:00.000Z"
TODAY = date.today()


def ago(days):
    return (TODAY - timedelta(days=days)).isoformat() + "T08:00:00.000Z"


ENROLMENTS = [
    {"status": "Passed", "module_name": "Phishing 101", "content_type": "Store Purchase", "time_spent": 600, "store_purchase_id": 1,
     "enrollment_date": T, "user": {"id": 1, "first_name": "Ana", "last_name": "A"}},
    {"status": "Passed", "module_name": "Phishing 101", "content_type": "Store Purchase", "time_spent": 300, "store_purchase_id": 1,
     "enrollment_date": T, "user": {"id": 2, "first_name": "Budi", "last_name": "B"}},
    {"status": "Past Due", "module_name": "Phishing 101", "content_type": "Store Purchase", "store_purchase_id": 1,
     "enrollment_date": T, "user": {"id": 3, "first_name": "Citra", "last_name": "C"}},
    {"status": "Past Due", "module_name": "Password Basics", "content_type": "Store Purchase", "store_purchase_id": 2,
     "enrollment_date": T, "user": {"id": 1, "first_name": "Ana", "last_name": "A"}},
    {"status": "Not Started", "module_name": "Password Basics", "content_type": "Store Purchase", "store_purchase_id": 2,
     "enrollment_date": "2024-01-05T08:00:00.000Z", "user": {"id": 2, "first_name": "Budi", "last_name": "B"}},
]
PURCHASES = [
    {"store_purchase_id": 1, "name": "Phishing 101", "type": "Training Module", "duration": 10, "retired": False},
    {"store_purchase_id": 2, "name": "Password Basics", "type": "Video Module", "duration": 5, "retired": False},
    {"store_purchase_id": 3, "name": "Unused Game", "type": "Game", "duration": 8, "retired": False},
    {"store_purchase_id": 4, "name": "Old Poster", "type": "Poster / Artwork", "duration": None, "retired": True},
]
USERS = [
    {"id": 1, "first_name": "Ana", "last_name": "A", "status": "active", "current_risk_score": 50.0, "phish_prone_percentage": 20.0,
     "joined_on": ago(30), "last_sign_in": ago(5)},
    {"id": 2, "first_name": "Budi", "last_name": "B", "status": "active", "current_risk_score": 30.0, "phish_prone_percentage": 0.0,
     "joined_on": ago(400), "last_sign_in": ago(200)},
    {"id": 3, "first_name": "Citra", "last_name": "C", "status": "active", "current_risk_score": 44.0, "phish_prone_percentage": 0.0,
     "joined_on": ago(10), "last_sign_in": None},
]
GROUPS = [
    {"id": 10, "name": "Finance Team", "current_risk_score": 48.0, "member_count": 4},
    {"id": 20, "name": "IT", "current_risk_score": 30.0, "member_count": 3},
    {"id": 30, "name": "Finance Board", "current_risk_score": 41.0, "member_count": 2},
    {"id": 40, "name": "Empty", "current_risk_score": 90.0, "member_count": 0},
]


def history(start, end):
    """weekly points from 120 days ago to today, moving linearly from start to end"""
    points = []
    for weeks in range(18, -1, -1):
        days = weeks * 7
        points.append({"date": ago(days), "risk_score": start + (end - start) * (1 - days / 126)})
    return points


GROUP_HISTORY = {10: history(40.0, 48.0), 20: history(35.0, 30.0), 30: history(41.0, 41.0)}


class FakeKB:
    def __init__(self, enrolments=ENROLMENTS, users=USERS, tests=None):
        self.enrolments, self.users, self.tests = enrolments, users, tests or []
        self.calls = []

    async def list_training_enrollments(self, console, **kwargs):
        self.calls.append(("enrollments", kwargs))
        return [dict(e) for e in self.enrolments]

    async def list_store_purchases(self, console, max_records=None):
        return [dict(p) for p in PURCHASES]

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in self.users]

    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def get_group(self, console, group_id):
        return next(dict(g) for g in GROUPS if g["id"] == group_id)

    async def get_group_risk_history(self, console, group_id, full=False):
        self.calls.append(("group_history", group_id, full))
        return [dict(p) for p in GROUP_HISTORY.get(group_id, [])]

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        self.calls.append(("tests", campaign_type))
        return [dict(t) for t in self.tests]


async def test_modules_ranked_by_completion_with_typical_minutes():
    r = await summaries.training_by_module(FakeKB(), "main")
    assert [m["module"] for m in r["modules"]] == ["Password Basics", "Phishing 101"]
    phishing = r["modules"][1]
    assert (phishing["enrolled"], phishing["passed"], phishing["past_due"], phishing["completion_percent"]) == (3, 2, 1, 66.67)
    # time_spent 600 and 300 seconds: median 7.5 minutes
    assert phishing["typical_minutes"] == 7.5
    assert r["headline"] == ('2 training modules with 5 enrolments; 2 passed (40.0%). Lowest completion: '
                             '"Password Basics" (0.0%, 0 of 2 passed); highest: "Phishing 101" (66.67%, 2 of 3 passed).')


@pytest.mark.parametrize("sort,lead", [
    ("most_completed", 'Highest completion: "Phishing 101" (66.67%, 2 of 3 passed); lowest: "Password Basics" (0.0%, 0 of 2 passed).'),
    ("most_overdue", 'Most Past Due: "Phishing 101" (1 of 3).'),
    ("most_enrolled", 'Most enrolments: "Phishing 101" (3, 66.67% passed).'),
])
async def test_module_headline_leads_with_what_was_asked(sort, lead):
    # a "best module" answer once opened with the lowest, and the model made up a wrong lowest of its own
    r = await summaries.training_by_module(FakeKB(), "main", sort=sort)
    assert r["headline"].endswith(lead)


async def test_one_module_by_name_lists_who_is_overdue():
    r = await summaries.training_by_module(FakeKB(), "main", module="phishing")
    assert r["headline"].startswith('Module "Phishing 101": 3 enrolments, 2 passed (66.67%), 1 Past Due')
    assert r["past_due_people"] == ["Citra C"] and r["past_due_people_total"] == 1


async def test_unknown_module_says_so_with_names_to_offer():
    r = await summaries.training_by_module(FakeKB(), "main", module="cloud security")
    assert r["modules"] == [] and "No training module matches 'cloud security'" in r["headline"]
    assert r["some_module_names"] == ["Password Basics", "Phishing 101"]


# most_overdue: both have 1 Past Due, the tie goes to the module with more enrolments (as in the headline)
@pytest.mark.parametrize("sort,first", [("most_overdue", "Phishing 101"), ("most_enrolled", "Phishing 101"),
                                        ("most_completed", "Phishing 101"), ("longest", "Phishing 101"), ("nonsense", "Password Basics")])
async def test_module_sorts(sort, first):
    r = await summaries.training_by_module(FakeKB(), "main", sort=sort)
    assert r["modules"][0]["module"] == first


async def test_module_period_uses_enrolment_date():
    r = await summaries.training_by_module(FakeKB(), "main", start_date="2025-01-01")
    assert r["enrolments"] == 4 and r["period"].startswith("enrolled 2025-01-01")
    bad = await summaries.training_by_module(FakeKB(), "main", start_date="Jan 2025")
    assert bad["error"] is True


async def test_modules_with_no_enrolments():
    r = await summaries.training_by_module(FakeKB(enrolments=[]), "main")
    assert r["modules"] == [] and r["headline"] == "No training enrolments."


async def test_library_counts_types_retired_and_never_assigned():
    r = await summaries.training_library(FakeKB(), "main")
    assert r["by_type"] == {"Training Module": 1, "Video Module": 1, "Game": 1, "Poster / Artwork": 1}
    assert r["never_assigned"] == ["Unused Game"]
    item = r["items"][0]
    assert {k: item[k] for k in ("name", "type", "length", "enrolments", "retired")} == {"name": "Phishing 101", "type": "Training Module", "length": 10, "enrolments": 3, "retired": False}
    assert "1 are retired and 1 current ones have never been assigned" in r["headline"]
    video = await summaries.training_library(FakeKB(), "main", content_type="video")
    assert [i["name"] for i in video["items"]] == ["Password Basics"]


async def test_one_group_trend_uses_the_group_history():
    kb = FakeKB()
    r = await summaries.group_risk_trend(kb, "main", group="it")
    assert r["group_id"] == 20 and r["headline"].startswith("Group IT: risk score now 30.0 (Low).")
    assert ("group_history", 20, False) in kb.calls


async def test_group_name_matching_several_asks_which():
    r = await summaries.group_risk_trend(FakeKB(), "main", group="finance")
    assert r["ask_user"] is True and [m["name"] for m in r["matches"]] == ["Finance Team", "Finance Board"]


async def test_unknown_group_is_a_readable_error():
    r = await summaries.group_risk_trend(FakeKB(), "main", group="marketing")
    assert r["error"] is True and "No active group matches 'marketing'" in r["message"]


async def test_riskiest_groups_trend_counts_risers_and_fallers():
    kb = FakeKB()
    r = await summaries.group_risk_trend(kb, "main", limit=3)
    # the empty group is left out; the others ranked by today's score
    assert [g["group"] for g in r["groups"]] == ["Finance Team", "Finance Board", "IT"]
    assert r["headline"].startswith("Of the 3 riskiest groups, 3 can be compared with 90 days ago: 1 rose and 1 fell")


async def test_riskiest_groups_trend_says_how_many_have_no_old_snapshot():
    kb = FakeKB()
    GROUP_HISTORY[30], saved = [], GROUP_HISTORY[30]
    try:
        r = await summaries.group_risk_trend(kb, "main", limit=3)
    finally:
        GROUP_HISTORY[30] = saved
    assert "2 can be compared with 90 days ago" in r["headline"]
    assert "The other 1 have no snapshot from 90 days ago." in r["headline"]
    assert sum(1 for c in kb.calls if c[0] == "group_history") == 3


async def test_sign_in_buckets():
    r = await summaries.sign_in_activity(FakeKB(), "main")
    assert r["headline"] == ("Of 3 active users, 1 have never signed in to KnowBe4, 1 last signed in more than 90 days ago, "
                             "0 between 31 and 90 days ago and 1 in the last 30 days.")
    assert [p["name"] for p in r["never_signed_in_people"]] == ["Citra C"]
    assert r["longest_since_sign_in"][0]["days_ago"] == 200


async def test_new_joiners_against_everyone_else():
    r = await summaries.new_joiners(FakeKB(), "main", start_date=ago(90)[:10])
    assert r["date_used"].startswith("joined_on")
    assert r["joiners"]["people"] == 2 and r["everyone_else"]["people"] == 1
    assert r["joiners"]["average_risk_score"] == 47.0 and r["joiners"]["with_past_due_training"] == 2
    assert [p["name"] for p in r["people"]] == ["Ana A", "Citra C"]
    none = await summaries.new_joiners(FakeKB(users=[]), "main")
    assert none["headline"].startswith("No active users joined from")


async def test_callback_phishing_with_and_without_calls():
    quiet = FakeKB(tests=[{"pst_id": 1, "name": "A", "started_at": T, "called_count": 0, "callback_data_entered_count": 0}])
    r = await summaries.callback_phishing_summary(quiet, "main")
    assert ("tests", "callback") in quiet.calls
    assert r["headline"].startswith("No callback (phone) phishing results: nobody called the number in any of the 1")
    busy = FakeKB(tests=[{"pst_id": 2, "name": "Call me", "started_at": T, "delivered_count": 9, "called_count": 3,
                          "callback_data_entered_count": 1}])
    r = await summaries.callback_phishing_summary(busy, "main")
    assert r["called"] == 3 and r["data_entered_on_call"] == 1 and r["tests"][0]["name"] == "Call me"


async def test_speed_of_failure_in_test_detail():
    def rec(uid, delivered, **events):
        return {"recipient_id": uid, "user": {"id": uid, "first_name": str(uid)}, "delivered_at": delivered, **events}

    class KB:
        async def get_phishing_security_test(self, console, pst_id, campaign_type=None):
            return {"pst_id": 5, "name": "Speed", "started_at": T, "phish_prone_percentage": 0.5}

        async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
            return [
                rec(1, "2026-10-01T08:00:00.000Z", clicked_at="2026-10-01T08:04:00.000Z"),
                rec(2, "2026-10-01T08:00:00.000Z", data_entered_at="2026-10-01T10:00:00.000Z", clicked_at="2026-10-01T09:00:00.000Z"),
                rec(3, "2026-10-01T08:00:00.000Z", opened_at="2026-10-01T08:30:00.000Z"),
                rec(4, None, bounced_at="2026-10-01T08:00:00.000Z"),
            ]

    r = await summaries.phishing_test_detail(KB(), "main", pst_id=5)
    speed = r["speed_of_failure"]
    assert (speed["fastest_minutes"], speed["median_minutes"], speed["within_10_minutes"], speed["within_1_hour"]) == (4.0, 32.0, 1, 2)
    assert r["opened_but_did_nothing"] == 1 and r["bounced"] == 1


async def test_group_trend_chart_needs_a_group():
    r = await outputs.make_chart(FakeKB(), "main", "group_trend", "id")
    assert r["error"] is True and "group_id" in r["message"]



def episode(n, status, season=1):
    return {"status": status, "module_name": f"The Inside Man: Season {season} Ep {n:02d} - Title {chr(64 + n)}", "content_type": "Store Purchase",
            "enrollment_date": T, "user": {"id": n, "first_name": "P", "last_name": str(n)}}


async def test_series_episodes_become_one_row_and_named_ones_stay_apart():
    # twelve near-identical episodes filled the whole top 10 of the chart
    enrolments = [episode(n, "Past Due") for n in range(1, 13)] + [episode(1, "Passed", 2), episode(2, "Past Due", 2)] + ENROLMENTS
    r = await summaries.training_by_module(FakeKB(enrolments=enrolments), "main", sort="most_enrolled")
    names = [m["module"] for m in r["modules"]]
    assert names[0] == "The Inside Man: Season 1 (12 episodes)" and "The Inside Man: Season 2 (2 episodes)" in names
    season1 = r["modules"][0]
    assert season1["episodes"] == 12 and season1["enrolled"] == 12 and "every enrolment is Past Due" in season1["facts"]
    named = await summaries.training_by_module(FakeKB(enrolments=enrolments), "main", module="inside man season 1")
    assert named["modules_total"] == 12


async def test_module_facts_explain_small_and_late_modules():
    r = await summaries.training_by_module(FakeKB(), "main")
    facts = {m["module"]: m["facts"] for m in r["modules"]}
    assert "only 2 enrolled, so one person changes the completion by about 50 points" in facts["Password Basics"]
    assert "length as KnowBe4 lists it: 10" in facts["Phishing 101"]
    assert "do not" not in r["note"] or "never give other reasons" in r["note"]


async def test_library_newest_and_period():
    dated = [dict(p, publish_date=d1, purchase_date=d2) for p, (d1, d2) in zip(PURCHASES, [
        ("2024-01-01T00:00:00Z", "2024-02-01T00:00:00Z"), ("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z"),
        ("2020-01-01T00:00:00Z", "2026-05-01T00:00:00Z"), ("2019-01-01T00:00:00Z", "2024-01-01T00:00:00Z")], strict=True)]

    class KB(FakeKB):
        async def list_store_purchases(self, console, max_records=None):
            return [dict(p) for p in dated]

    newest = await summaries.training_library(KB(), "main", sort="newest")
    assert [i["name"] for i in newest["items"]][:2] == ["Password Basics", "Phishing 101"]
    assert newest["items"][0]["published"] == "2026-03-01" and newest["items"][0]["added_to_account"] == "2026-04-01"
    in_2026 = await summaries.training_library(KB(), "main", start_date="2026-01-01")
    assert [i["name"] for i in in_2026["items"]] == ["Password Basics", "Unused Game"]
    assert in_2026["headline"].startswith("From 2026-01-01 to today: 2 training content items are new (1 published by KnowBe4, 2 added")
    assert (await summaries.training_library(KB(), "main", start_date="2026/01/01"))["error"] is True



@pytest.mark.parametrize("query,name,hit", [
    ("inside man season 1", "The Inside Man: Season 1 Ep 03 - On Our Side", True),
    ("inside man season 1", "The Inside Man: Season 2 Ep 01 - Mobile", False),   # "1" is not "01"
    ("ep 1", "The Inside Man: Season 2 Ep 10 - Keep", False),                    # nor "10"
    ("phish", "Basics of Phishing", True),                                         # words match from their start
    ("hing", "Basics of Phishing", False),
    ("video", "Video Module", True),
])
def test_name_matching_uses_word_starts_and_whole_numbers(query, name, hit):
    assert summaries._words_match(name, query) is hit


async def test_library_says_it_is_not_the_whole_modstore():
    r = await summaries.training_library(FakeKB(), "main")
    assert r["headline"].endswith(summaries.LIBRARY_SCOPE) and "not the whole ModStore catalogue" in r["note"]


async def test_library_counts_for_the_first_line():
    r = await summaries.training_library(FakeKB(), "main")
    assert r["counts"] == {"total": 4, "retired": 1, "never_assigned": 1, "published": None, "added": None,
                           "start_date": None, "end_date": None, "content_type": None}
