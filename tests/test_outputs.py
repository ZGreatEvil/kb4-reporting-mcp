import csv
import json
import os
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from kb4_mcp import outputs
from kb4_mcp.knowledge import NistSearch, _passages

USERS = [
    {"id": 1, "first_name": "Ana", "last_name": "Low", "email": "ana@example.com", "status": "active", "current_risk_score": 30.0, "phish_prone_percentage": 0.0},
    {"id": 2, "first_name": "=cmd", "last_name": "Evil", "email": "x@example.com", "status": "active", "current_risk_score": 55.0, "phish_prone_percentage": 100.0},
    {"id": 3, "first_name": "Citra", "last_name": "Mid", "email": "c@example.com", "status": "active", "current_risk_score": 44.0, "phish_prone_percentage": 25.0, "groups": [70]},
]
HISTORY = [{"date": "2026-05-04T00:00:00.000Z", "risk_score": 46.0}, {"date": "2026-06-15T00:00:00.000Z", "risk_score": 45.25}]


class FakeKB:
    async def list_users(self, console, status=None, group_id=None, max_records=None):
        return [dict(u) for u in USERS]

    async def get_user(self, console, user_id):
        return USERS[0]

    async def get_user_risk_history(self, console, user_id, full=False):
        return list(HISTORY)

    async def get_account_risk_history(self, console, full=False):
        return list(HISTORY)

    async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
        return [{"pst_id": 9, "name": "Test A", "started_at": "2026-10-01T00:00:00.000Z", "phish_prone_percentage": 0.25, "delivered_count": 4}]

    async def list_training_campaigns(self, console, exclude_percentages=False, max_records=None):
        return [{"campaign_id": 5, "name": "Q3", "start_date": "2026-07-01T00:00:00.000Z", "completion_percentage": 60.0}]

    async def list_groups(self, console, status=None, max_records=None):
        return [{"id": 70, "name": "Finance", "current_risk_score": 44.0, "member_count": 1}]

    async def get_group(self, console, group_id):
        return {"id": 70, "name": "Finance", "current_risk_score": 44.0, "member_count": 1}

    async def get_group_risk_history(self, console, group_id, full=False):
        return list(HISTORY)

    async def graph(self, console, product, document, variables=None):
        # reported emails per month for the PhishER chart
        return {"phisherMessages": {"pagination": {"totalCount": 3, "pages": 1}, "nodes": [
            {"reportedAt": "2026-09-02T08:00:00Z", "category": "THREAT", "actionStatus": "RESOLVED"},
            {"reportedAt": "2026-10-05T08:00:00Z", "category": "SPAM", "actionStatus": "RECEIVED"},
            {"reportedAt": "2026-10-06T08:00:00Z", "category": "UNKNOWN", "actionStatus": "IN_REVIEW"},
        ]}}

    async def list_training_enrollments(self, console, **kwargs):
        return [
            {"module_name": "Phishing 101", "status": "Passed", "time_spent": 600, "user": {"id": 1}},
            {"module_name": "Phishing 101", "status": "Past Due", "user": {"id": 2}},
            {"module_name": "Passwords", "status": "Not Started", "user": {"id": 3}},
        ]


# charts that need an argument to draw anything
CHART_ARGS = {"group_trend": {"group_id": 70}}


@pytest.fixture(autouse=True)
def tmp_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(outputs, "CHART_DIR", tmp_path / "charts")
    monkeypatch.setattr(outputs, "EXPORT_DIR", tmp_path / "exports")
    return tmp_path


@pytest.mark.parametrize("chart", outputs.CHARTS)
async def test_every_chart_writes_a_png(tmp_dirs, chart):
    result = await outputs.make_chart(FakeKB(), "main", chart, "en", **CHART_ARGS.get(chart, {}))
    name = result["image_url"].rsplit("/", 1)[-1]
    assert result["image_url"] == f"/static/charts/{name}"
    data = (tmp_dirs / "charts" / name).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 5000
    assert result["summary"]


async def test_chart_titles_follow_language():
    assert (await outputs.make_chart(FakeKB(), "main", "users_by_level", "id"))["title"] == "Pengguna aktif per level risiko"
    assert (await outputs.make_chart(FakeKB(), "main", "users_by_level", "en"))["title"] == "Active users per risk level"
    person = await outputs.make_chart(FakeKB(), "main", "risk_trend", "en", user_id=1)
    assert person["title"] == "Ana Low's risk score over time" and person["summary"]["to"] == "2026-06-15"


async def test_users_by_level_counts():
    result = await outputs.make_chart(FakeKB(), "main", "users_by_level", "en")
    assert result["summary"]["users_per_level"] == {"Low": 1, "Medium": 1, "Critical": 1}


async def test_unknown_chart_is_rejected():
    result = await outputs.make_chart(FakeKB(), "main", "radar", "en")
    assert result["error"] is True and "risk_trend" in result["message"]


@pytest.mark.parametrize("dataset,rows", [("users", 3), ("phishing_tests", 1), ("training_campaigns", 1), ("risk_history", 2)])
async def test_every_export_writes_a_csv(tmp_dirs, dataset, rows):
    result = await outputs.export_csv(FakeKB(), "main", dataset)
    file_id = result["download_url"].split("/exports/")[1].split(".csv")[0]
    assert len(file_id) == 32 and result["download_url"].endswith(f"?name={result['file_name']}")
    path = tmp_dirs / "exports" / f"{file_id}.csv"
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # excel reads utf-8 correctly with the bom
    table = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    assert table[0] == result["columns"] and len(table) - 1 == rows == result["rows"]


async def test_csv_formula_cells_are_neutralised(tmp_dirs):
    result = await outputs.export_csv(FakeKB(), "main", "users")
    file_id = result["download_url"].split("/exports/")[1].split(".csv")[0]
    names = [r[1] for r in csv.reader((tmp_dirs / "exports" / f"{file_id}.csv").read_text(encoding="utf-8-sig").splitlines())]
    assert "'=cmd Evil" in names


async def test_phishing_export_uses_percent(tmp_dirs):
    result = await outputs.export_csv(FakeKB(), "main", "phishing_tests")
    file_id = result["download_url"].split("/exports/")[1].split(".csv")[0]
    rows = list(csv.reader((tmp_dirs / "exports" / f"{file_id}.csv").read_text(encoding="utf-8-sig").splitlines()))
    assert rows[1][-1] == "25.0"


async def test_old_files_are_cleaned_up(tmp_dirs):
    folder = tmp_dirs / "charts"
    folder.mkdir()
    old = folder / "old.png"
    old.write_bytes(b"x")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    await outputs.make_chart(FakeKB(), "main", "top_users", "en")
    assert not old.exists()


# nist search


def test_passages_keep_page_numbers():
    pages = ["word " * 300, "", "other " * 50]
    passages = _passages(pages)
    assert {p["page"] for p in passages} == {1, 3}


def test_nist_search_ranks_and_cites(tmp_path):
    index = {
        "sources": [{"id": "SP 800-50r1", "title": "Learning programs", "url": "u"}],
        "passages": [
            {"source": "SP 800-50r1", "page": 12, "text": "Phishing simulation exercises help measure the effectiveness of awareness training."},
            {"source": "SP 800-50r1", "page": 40, "text": "Budget planning and procurement for the learning program."},
        ],
    }
    f = tmp_path / "idx.json"
    f.write_text(json.dumps(index), encoding="utf-8")
    result = NistSearch(f).search("phishing simulation effectiveness")
    assert result["results"][0]["pdf_page"] == 12 and result["results"][0]["source"] == "SP 800-50r1"
    assert "cite" in result["note"]
    assert NistSearch(f).search("the and of")["results"] == []


def test_missing_nist_library_says_how_to_build(tmp_path):
    result = NistSearch(tmp_path / "missing.json").search("anything")
    assert result["error"] is True and "python -m kb4_mcp.knowledge" in result["message"]


# agent attaches charts and files from tool results


async def test_agent_attaches_chart_and_csv_and_drops_model_links(monkeypatch):
    from agent.agent import Agent
    from config.settings import AppConfig, ConsoleConfig

    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")})
    results = {
        "make_chart": {"chart": "top_users", "title": "Top 3", "image_url": "/static/charts/abc.png", "summary": {}},
        "export_csv": {"dataset": "users", "rows": 3, "download_url": "/exports/" + "a" * 32 + ".csv?name=x.csv", "file_name": "x.csv"},
    }
    calls = []

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=n, description="d", input_schema={"type": "object"}) for n in results])

        async def call_tool(self, name, arguments):
            calls.append((name, dict(arguments)))
            return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(text=json.dumps(results[name]))])

    replies = [
        SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(id="a", function=SimpleNamespace(name="make_chart", arguments='{"console": "main", "chart": "top_users", "language": "en"}')),
            SimpleNamespace(id="b", function=SimpleNamespace(name="export_csv", arguments='{"console": "main", "dataset": "users"}')),
        ]), finish_reason="tool_calls"),
        SimpleNamespace(message=SimpleNamespace(content="**Ini grafiknya.** ![x](/static/charts/wrong.png) [file](/exports/wrong.csv)", tool_calls=None), finish_reason="stop"),
    ]

    class LLM:
        async def chat(self, messages, tools):
            return replies.pop(0)

    @asynccontextmanager
    async def factory():
        yield Session()

    answer = await Agent(cfg, llm=LLM(), session_factory=factory).ask("grafik dan csv", "id")
    assert calls[0][1]["language"] == "id"  # the chat language wins over what the model passed
    assert "wrong" not in answer
    assert "![Top 3](/static/charts/abc.png)" in answer
    assert "[⬇ Unduh CSV: x.csv (3 baris)](/exports/" + "a" * 32 + ".csv?name=x.csv)" in answer


# download endpoint


def test_export_download_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import web.main as web_main

    monkeypatch.setattr(web_main, "EXPORT_DIR", tmp_path)
    file_id = "b" * 32
    (tmp_path / f"{file_id}.csv").write_bytes(b"a,b\n1,2\n")
    client = TestClient(web_main.app)
    ok = client.get(f"/exports/{file_id}.csv?name=contoh_users.csv")
    assert ok.status_code == 200 and ok.text == "a,b\n1,2\n"
    assert 'filename="contoh_users.csv"' in ok.headers["content-disposition"]
    assert client.get("/exports/..%2F..%2F.env.csv").status_code == 404
    assert client.get("/exports/" + "c" * 32 + ".csv").status_code == 404
    weird = client.get(f"/exports/{file_id}.csv?name=../../evil name")
    assert 'filename=".._.._evil_name.csv"' in weird.headers["content-disposition"]


async def test_phishing_summary_gives_weighted_average():
    from kb4_mcp import summaries

    class KB:
        async def list_phishing_security_tests(self, console, campaign_type=None, max_records=None):
            # 1 failure in 4 emails, 3 in 4: weighted = 4 / 8 = 50%
            return [{"name": "a", "phish_prone_percentage": 0.25, "delivered_count": 4, "started_at": "2026-01-01"},
                    {"name": "b", "phish_prone_percentage": 0.75, "delivered_count": 4, "started_at": "2026-02-01"},
                    {"name": "c", "phish_prone_percentage": 0.9, "delivered_count": 0, "started_at": "2026-03-01"}]

    result = await summaries.phishing_campaign_summary(KB(), "main")
    assert result["all_tests_phish_prone_percent"] == 50.0
    assert result["all_tests_vs_benchmark"]["comparison"].startswith("higher than every")


async def test_nist_sources_are_added_by_code(monkeypatch):
    from agent.agent import Agent
    from config.settings import AppConfig, ConsoleConfig

    monkeypatch.setenv("KB4_T_MAIN", "real-token")
    cfg = AppConfig(consoles={"main": ConsoleConfig(display_name="Main", api_key_env="KB4_T_MAIN")})
    found = {"results": [{"source": "SP 800-50r1", "pdf_page": 80, "text": "x"}, {"source": "SP 800-50r1", "pdf_page": 69, "text": "y"},
                         {"source": "TN 2276", "pdf_page": 22, "text": "z"}]}

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="search_nist", description="d", input_schema={"type": "object"})])

        async def call_tool(self, name, arguments):
            return SimpleNamespace(is_error=False, structured_content=None, content=[SimpleNamespace(text=json.dumps(found))])

    replies = [
        SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[
            SimpleNamespace(id="a", function=SimpleNamespace(name="search_nist", arguments='{"query": "measure training effectiveness"}'))]), finish_reason="tool_calls"),
        SimpleNamespace(message=SimpleNamespace(content="**Ukur dengan metrik.**", tool_calls=None), finish_reason="stop"),
    ]

    class LLM:
        async def chat(self, messages, tools):
            return replies.pop(0)

    @asynccontextmanager
    async def factory():
        yield Session()

    answer = await Agent(cfg, llm=LLM(), session_factory=factory).ask("menurut NIST?", "id")
    assert answer.endswith("**Sumber:** NIST SP 800-50r1 (hlm. PDF 69, 80); NIST TN 2276 (hlm. PDF 22)")


@pytest.mark.parametrize("prompt,expected", [
    ("Tampilkan semua pengguna", True),
    ("Export semua pengguna ke CSV.", False),
    ("Tampilkan grafik semua pengguna per level", False),
    ("list all users", True),
])
def test_exports_and_charts_are_not_list_requests(prompt, expected):
    from agent.agent import LIST_ALL, NOT_A_LIST
    assert (bool(LIST_ALL.search(prompt)) and not NOT_A_LIST.search(prompt)) is expected


def test_nist_build_without_pdfs_and_no_download_explains(monkeypatch, tmp_path):
    from kb4_mcp import knowledge

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path)
    with pytest.raises(knowledge.BuildError, match="run without --no-download"):
        knowledge.build_index(download=False)


def test_nist_build_with_a_damaged_pdf_explains(monkeypatch, tmp_path):
    from kb4_mcp import knowledge

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path)
    (tmp_path / "pdfs").mkdir()
    (tmp_path / "pdfs" / knowledge.SOURCES[0]["url"].rsplit("/", 1)[-1]).write_bytes(b"not a pdf")
    with pytest.raises(knowledge.BuildError, match="could not be read"):
        knowledge.build_index(download=False)


def test_damaged_nist_index_asks_for_a_rebuild(tmp_path):
    index = tmp_path / "nist_index.json"
    index.write_text("{", encoding="utf-8")
    result = NistSearch(index).search("phishing")
    assert result["error"] is True and "Rebuild" in result["message"]


async def test_users_export_is_active_only_unless_asked():
    class StatusKB(FakeKB):
        async def list_users(self, console, status=None, group_id=None, max_records=None):
            rows = [dict(u) for u in USERS] + [{"id": 9, "first_name": "Old", "last_name": "Leaver", "status": "archived"}]
            return [u for u in rows if status is None or u["status"] == status]

    active = await outputs.export_csv(StatusKB(), "main", "users")
    everyone = await outputs.export_csv(StatusKB(), "main", "users", status="all")
    assert (active["rows"], active["status_filter"]) == (3, "active")
    assert (everyone["rows"], everyone["status_filter"]) == (4, "all")
