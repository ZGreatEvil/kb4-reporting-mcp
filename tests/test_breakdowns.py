from datetime import date, timedelta

import pytest

from kb4_mcp import breakdowns

GROUPS = [{"id": 1, "name": "IT"}, {"id": 2, "name": "HR"}, {"id": 3, "name": "Finance", "current_risk_score": 41.0}]
USERS = [
    {"id": 10, "first_name": "Ana", "last_name": "A", "email": "ana@example.com", "status": "active", "groups": [1],
     "current_risk_score": 50.0, "phish_prone_percentage": 25.0, "joined_on": "2025-01-01"},
    {"id": 11, "first_name": "Budi", "last_name": "B", "email": "budi@example.com", "status": "active", "groups": [1, 2],
     "current_risk_score": 30.0, "phish_prone_percentage": 0.0, "joined_on": "2025-02-01"},
    {"id": 12, "first_name": "Citra", "last_name": "C", "email": "citra@example.com", "status": "active", "groups": [2, 99],
     "current_risk_score": 45.0, "phish_prone_percentage": 0.0, "joined_on": "2026-03-01"},
    {"id": 13, "first_name": "Dodi", "last_name": "D", "email": "dodi@example.com", "status": "archived", "groups": [1]},
    {"id": 14, "first_name": "Eka", "last_name": "E", "email": "eka@example.com", "status": "active", "groups": [3],
     "current_risk_score": 20.0, "joined_on": "2026-06-01"},
]
TESTS = [
    {"pst_id": 100, "name": "Invoice test", "started_at": "2026-10-01T00:00:00Z", "delivered_count": 4, "reported_count": 1,
     "phish_prone_percentage": 0.25},
    {"pst_id": 101, "name": "Old test", "started_at": "2026-04-01T00:00:00Z", "delivered_count": 2, "reported_count": 0,
     "phish_prone_percentage": 0.0},
]


def rec(uid, clicked=False, reported=False, delivered=True):
    return {"user": {"id": uid}, "delivered_at": "2026-10-01T01:00:00Z" if delivered else None,
            "clicked_at": "2026-10-01T01:05:00Z" if clicked else None, "reported_at": "2026-10-01T02:00:00Z" if reported else None}


RECIPIENTS = {100: [rec(10, clicked=True), rec(11, reported=True), rec(12), rec(13, clicked=True), rec(14, delivered=False)],
              101: [rec(10), rec(12)]}
CAMPAIGNS = [{"campaign_id": 7, "name": "Onboarding", "start_date": "2026-09-01T00:00:00Z", "status": "In Progress",
              "groups": [{"group_id": 1, "name": "IT"}, {"group_id": 2, "name": "HR"}]}]


def enrol(uid, status, module="M1", campaign=7, when="2026-09-02T00:00:00Z", seconds=None):
    return {"campaign_id": campaign, "campaign_name": "Onboarding", "module_name": module, "status": status, "user": {"id": uid},
            "enrollment_date": when, "completion_date": "2026-09-10T00:00:00Z" if status == "Passed" else None, "time_spent": seconds}


ENROLMENTS = [enrol(10, "Passed", seconds=600), enrol(10, "Past Due", "M2"), enrol(11, "Passed"), enrol(12, "Not Started"),
              enrol(13, "Past Due"), enrol(14, "Passed", campaign=8, when="2025-01-01T00:00:00Z")]


class FakeKB:
    async def list_groups(self, console, status=None, max_records=None):
        return [dict(g) for g in GROUPS]

    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS if status is None or u.get("status") == status]

    async def get_user(self, console, user_id):
        return dict(next(u for u in USERS if u["id"] == user_id))

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [dict(t) for t in TESTS]

    async def list_pst_recipients(self, console, pst_id, campaign_type=None, max_records=None):
        return [dict(r) for r in RECIPIENTS[pst_id]]

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [dict(c) for c in CAMPAIGNS]

    async def list_training_enrollments(self, console, *args, user_id=None, exclude_archived_users=False, **kwargs):
        rows = [dict(e) for e in ENROLMENTS if user_id is None or e["user"]["id"] == user_id]
        if exclude_archived_users:
            rows = [e for e in rows if next(u for u in USERS if u["id"] == e["user"]["id"])["status"] != "archived"]
        return rows

    async def list_group_members(self, console, group_id, max_records=None):
        return [{"id": u["id"]} for u in USERS if group_id in (u.get("groups") or [])]


# ---------------------------------------------------------------- phishing per group

async def test_phishing_per_group_for_the_latest_test():
    r = await breakdowns.phishing_by_group(FakeKB(), "main")
    assert [t["pst_id"] for t in r["tests"]] == [100]
    rows = {g["group"]: g for g in r["groups"]}
    # Dodi is archived and Eka never got it delivered; group 99 is a system group with no row
    assert rows["IT"] == {"group": "IT", "delivered": 2, "failed": 1, "clicked": 1, "entered_data": 0, "opened_attachment": 0,
                          "reported": 1, "failure_percent": 50.0, "report_percent": 50.0}
    assert rows["HR"]["delivered"] == 2 and rows["HR"]["failed"] == 0
    assert r["totals"]["delivered"] == 3 and r["archived_not_counted"] == 1
    assert r["emails_to_people_in_unlisted_system_groups"] == 1
    assert r["headline"].startswith('Phishing test "Invoice test" (2026-10-01): 3 emails delivered in 2 groups; 1 failed (33.33%)')


async def test_phishing_per_group_named_groups_period_and_archived():
    r = await breakdowns.phishing_by_group(FakeKB(), "main", start_date="2026-01-01", text="phishing per grup hr dan marketing")
    assert [g["group"] for g in r["groups"]] == ["HR"] and len(r["tests"]) == 2
    assert r["groups"][0]["delivered"] == 3  # Budi and Citra in the October test, Citra in April
    with_archived = await breakdowns.phishing_by_group(FakeKB(), "main", groups="IT", include_archived=True)
    assert with_archived["groups"][0]["delivered"] == 3 and with_archived["archived_not_counted"] == 0


@pytest.mark.parametrize("args,message", [({"test": "nothing like it"}, "No phishing test matches"),
                                          ({"start_date": "2026-13-01"}, "must be a date")])
async def test_phishing_per_group_bad_input(args, message):
    r = await breakdowns.phishing_by_group(FakeKB(), "main", **args)
    assert r["error"] is True and message in r["message"]


# ---------------------------------------------------------------- campaign people

async def test_campaign_people_by_status():
    late = await breakdowns.campaign_people(FakeKB(), "main", campaign="onboarding")
    assert [p["name"] for p in late["people"]] == ["Ana A"] and late["people"][0]["status"] == "Past Due"
    assert late["headline"] == "Onboarding (2026-09-01): 1 people are Past Due."
    assert {m["module"]: m["status"] for m in late["people"][0]["modules"]} == {"M1": "Passed", "M2": "Past Due"}
    assert (await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="completed"))["total"] == 1   # Budi
    every = await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="all", include_archived=True)
    assert every["total"] == 4 and every["headline"].endswith("4 people are enrolled.")


async def test_campaign_people_narrowed_to_a_group_and_bad_status():
    hr = await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="not_started", text="siapa yang belum mulai di grup hr")
    assert [p["name"] for p in hr["people"]] == ["Citra C"] and "in HR" in hr["headline"]
    bad = await breakdowns.campaign_people(FakeKB(), "main", status="lost")
    assert bad["error"] is True and "status must be one of" in bad["message"]


async def test_campaign_people_rows_carry_groups_and_module_counts():
    every = await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="all")
    rows = {p["name"]: p for p in every["people"]}
    # no group named: every group the person is in; Budi is in IT and HR
    assert rows["Budi B"]["groups"] == ["IT", "HR"] and rows["Budi B"]["completed_on"] == "2026-09-10"
    assert rows["Ana A"]["modules_completed"] == 1 and rows["Ana A"]["modules_enrolled"] == 2 and rows["Ana A"]["completed_on"] is None
    # group 99 has no name in the group list: left out rather than shown as a number
    assert rows["Citra C"]["groups"] == ["HR"] and "archived" not in rows["Citra C"]
    hr = await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="all", text="grup HR")
    assert [p["groups"] for p in hr["people"]] == [["HR"], ["HR"]]  # Budi and Citra, only the named group


async def test_campaign_people_unfinished_is_everyone_not_done():
    r = await breakdowns.campaign_people(FakeKB(), "main", campaign="7", status="unfinished")
    assert sorted(p["name"] for p in r["people"]) == ["Ana A", "Citra C"] and r["headline"].endswith("2 people are not finished.")


async def test_people_csv_has_every_person_with_groups(tmp_path, monkeypatch):
    import csv

    from kb4_mcp import outputs
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)
    monkeypatch.setattr(breakdowns, "PEOPLE_LIMIT", 1)   # the chat cap does not apply to the file
    r = await outputs.export_csv(FakeKB(), "main", "campaign_people", campaign="7")
    assert r["status_filter"] == "all" and r["rows"] == 3 and r["campaign"] == "Onboarding"
    # the default past-year period does not filter a campaign's people, so it is not reported as if it did
    assert r["period"] == "the campaign's own people (no period filter)"
    path = tmp_path / r["download_url"].split("/")[-1].split("?")[0]
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0] == ["name", "email", "groups", "status", "modules_completed", "modules_enrolled", "completed_on", "campaign", "modules"]
    by_name = {row[0]: row for row in rows[1:]}
    assert by_name["Budi B"][2] == "IT; HR" and by_name["Budi B"][3] == "Passed" and by_name["Budi B"][6] == "2026-09-10"
    assert by_name["Ana A"][4:6] == ["1", "2"] and by_name["Ana A"][8] == "M1 (Passed); M2 (Past Due)"
    # archived people only when asked, and marked
    archived = await outputs.export_csv(FakeKB(), "main", "campaign_people", campaign="7", include_archived=True)
    path = tmp_path / archived["download_url"].split("/")[-1].split("?")[0]
    assert "Past Due (archived)" in path.read_text(encoding="utf-8-sig") and archived["rows"] == 4
    only_late = await outputs.export_csv(FakeKB(), "main", "campaign_people", campaign="7", status="past_due")
    assert only_late["rows"] == 1 and only_late["status_filter"] == "past_due"


@pytest.mark.parametrize("args,key", [({"campaign": "no such campaign"}, "error"), ({"campaign": "7", "status": "lost"}, "error")])
async def test_people_csv_bad_input_makes_no_file(tmp_path, monkeypatch, args, key):
    from kb4_mcp import outputs
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path)
    r = await outputs.export_csv(FakeKB(), "main", "campaign_people", **args)
    assert r.get(key) is True and "download_url" not in r and not list(tmp_path.iterdir())


# ---------------------------------------------------------------- group members

async def test_group_members_sorted_by_risk_with_late_training():
    r = await breakdowns.group_members(FakeKB(), "main", "it")
    assert [m["name"] for m in r["members"]] == ["Ana A", "Budi B"]  # Dodi is archived
    assert r["members"][0] == {"name": "Ana A", "email": "ana@example.com", "risk_score": 50.0, "risk_level": "High",
                               "phish_prone_percent": 25.0, "past_due_training": 1}
    assert r["headline"] == ("Group IT: 2 active members, average risk score 40.0 (Low); 1 have Past Due training and "
                             "1 have a phish-prone % above 0.")
    by_name = await breakdowns.group_members(FakeKB(), "main", text="siapa saja anggota grup finance?", sort="name")
    assert by_name["group"] == "Finance" and by_name["group_risk_score"] == 41.0


async def test_unknown_group_member_question():
    r = await breakdowns.group_members(FakeKB(), "main", "marketing")
    assert r["error"] is True and "No group matches 'marketing'" in r["message"]


# ---------------------------------------------------------------- one person's training

async def test_person_training_by_id_and_by_name():
    r = await breakdowns.person_training(FakeKB(), "main", user_id=10)
    assert r["by_status"] == {"Passed": 1, "Past Due": 1} and r["headline"] == "Ana A has 2 training enrolments: 1 Passed, 1 Past Due."
    assert r["enrolments"][0]["minutes"] == 10.0 or r["enrolments"][1]["minutes"] == 10.0
    by_name = await breakdowns.person_training(FakeKB(), "main", name="citra")
    assert by_name["user_id"] == 12 and by_name["by_status"] == {"Not Started": 1}


@pytest.mark.parametrize("args,key,text", [({"name": "a"}, "ask_user", None), ({"name": "zz"}, "message", "No active user matches"),
                                           ({}, "message", "Give user_id")])
async def test_person_training_unhappy(args, key, text):
    r = await breakdowns.person_training(FakeKB(), "main", **args)
    assert key in r and (text is None or text in r[key])


# ---------------------------------------------------------------- never phished or trained

async def test_coverage_gaps():
    r = await breakdowns.coverage_gaps(FakeKB(), "main", start_date="2026-01-01")
    # Eka: no delivered test and no 2026 enrolment; Citra was phished and enrolled
    assert (r["active_users"], r["no_phishing_test"], r["no_training"], r["neither"]) == (4, 1, 1, 1)
    assert [p["name"] for p in r["people_with_neither"]] == ["Eka E"]
    assert r["headline"].startswith("From 2026-01-01 to today, of 4 active users: 1 got no phishing test")


# ---------------------------------------------------------------- two periods

async def test_compare_periods_phishing_and_training():
    p = await breakdowns.compare_periods(FakeKB(), "main", "phishing", start_date="2026-07-01", end_date="2026-12-31")
    assert p["current"]["tests"] == 1 and p["current"]["phish_prone_percent"] == 25.0
    assert p["earlier"]["period"] == "2025-12-29 to 2026-06-30" and p["earlier"]["phish_prone_percent"] == 0.0
    assert p["change_points"] == 25.0 and p["better"] is False and "worse" in p["headline"]
    t = await breakdowns.compare_periods(FakeKB(), "main", "training", start_date="2026-01-01", end_date="2026-12-31",
                                         compare_start="2025-01-01", compare_end="2025-12-31")
    assert t["current"]["enrolments"] == 4 and t["current"]["completion_percent"] == 50.0 and t["earlier"]["completion_percent"] == 100.0
    assert t["better"] is False


async def test_compare_periods_defaults_and_bad_metric():
    r = await breakdowns.compare_periods(FakeKB(), "main")
    today = date.today()
    assert r["current"]["period"] == f"{(today - timedelta(days=89)).isoformat()} to {today.isoformat()}"
    assert (await breakdowns.compare_periods(FakeKB(), "main", "risk"))["error"] is True


@pytest.mark.parametrize("start,end,expected", [
    ("2026-10-01", "2026-11-12", ("2026-07-01", "2026-09-30")),   # this quarter so far: all of last quarter
    ("2026-01-01", "2026-11-12", ("2025-01-01", "2025-12-31")),   # this year so far: last year
    ("2026-11-01", "2026-11-12", ("2026-10-01", "2026-10-31")),   # this month: last month
    ("2026-01-01", "2026-03-31", ("2025-10-01", "2025-12-31")),   # Q1: Q4, not the whole year
    ("2026-03-15", "2026-04-14", ("2026-02-12", "2026-03-14")),   # any other range: the same number of days
])
def test_the_period_before(start, end, expected):
    a, b = breakdowns._previous(date.fromisoformat(start), date.fromisoformat(end))
    assert (a.isoformat(), b.isoformat()) == expected
