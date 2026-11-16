"""Lookups and definitions: find a group or a campaign by name, list the values a user field takes, and explain a metric.

They turn the words people use ("grup Finance", "kampanye Oktober", "departemen apa saja") into what the other tools need,
and give definitions from KnowBe4's own material so the model does not make them up.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from kb4_mcp.summaries import (
    _bad_period,
    _date,
    _limit,
    _period_label,
    _r,
    _test_percent,
    _within,
    _words_match,
    risk_level,
)

GROUP_LIMIT = 30


def _matches(name: Any, query: str) -> bool:
    """word starts ("fin" finds Finance) or the text anywhere ("security" finds "Team-Security")"""
    return _words_match(name, query) or query.casefold() in str(name or "").casefold()


async def find_group(kb: Any, console: str, query: str = "", status: str = "active", limit: int = GROUP_LIMIT) -> dict[str, Any]:
    """groups by name; an empty query lists them all, largest first"""
    status = (status or "active").strip().lower()
    if status not in ("active", "archived", "all"):
        return {"console": console, "error": True, "message": "status must be active, archived or all."}
    groups = await kb.list_groups(console, None if status == "all" else status)
    query = (query or "").strip()
    found = [g for g in groups if _matches(g.get("name"), query)] if query else list(groups)
    exact = [g for g in found if str(g.get("name") or "").casefold() == query.casefold()] if query else []
    found.sort(key=lambda g: (g not in exact, -(g.get("member_count") or 0), str(g.get("name") or "").casefold()))
    rows = [{"id": g.get("id"), "name": g.get("name"), "type": g.get("group_type"), "members": g.get("member_count"),
             "risk_score": _r(g.get("current_risk_score")), "risk_level": risk_level(g.get("current_risk_score")),
             "status": g.get("status")} for g in found]
    shown = rows[: _limit(limit, GROUP_LIMIT)]
    ask = bool(query) and len(found) > 1 and len(exact) != 1
    if not groups:
        headline = "This console has no groups."
    elif not query:
        headline = f"{len(groups)} groups ({status})."
    elif not found:
        headline = f"No group name matches '{query}' among {len(groups)} groups."
    else:
        headline = f"{len(found)} group(s) match '{query}'."
    return {
        "console": console,
        "headline": headline,
        "query": query,
        "total": len(found),
        "shown": len(shown),
        "truncated": len(found) > len(shown),
        "groups": shown,
        **({"chosen": exact[0].get("id")} if query and len(exact) == 1 else {}),
        "ask_user": ask,
        "note": ("Several groups match: list them and ask which one is meant." if ask else
                 "Start from the headline; list the groups as given. Do not add advice."),
    }


async def find_campaign(kb: Any, console: str, query: str = "", kind: str = "phishing", start_date: str | None = None,
                        end_date: str | None = None, limit: int = 10) -> dict[str, Any]:
    """phishing or training campaigns by name and date, newest first"""
    if problem := _bad_period(start_date, end_date):
        return {"console": console, "error": True, "message": problem}
    kind = (kind or "phishing").strip().lower()
    if kind not in ("phishing", "training"):
        return {"console": console, "error": True, "message": "kind must be phishing or training."}
    query = (query or "").strip()
    if kind == "phishing":
        items = await kb.list_phishing_campaigns(console)
        # a campaign that never ran is dated by its creation
        when = lambda c: c.get("last_run") or c.get("create_date")  # noqa: E731
    else:
        items = await kb.list_training_campaigns(console)
        when = lambda c: c.get("start_date")  # noqa: E731
    found = [c for c in items if (not query or _matches(c.get("name"), query)) and _within(when(c), start_date, end_date)]
    found.sort(key=lambda c: str(when(c) or ""), reverse=True)
    if kind == "phishing":
        rows = [{"campaign_id": c.get("campaign_id"), "name": c.get("name"), "status": c.get("status"),
                 "frequency": c.get("frequency"), "last_run": _date(c.get("last_run")) or None, "created": _date(c.get("create_date")) or None,
                 "tests_run": c.get("psts_count"),
                 # a fraction on campaigns, like on tests (0.25 = 25%)
                 "last_phish_prone_percent": _test_percent(c.get("last_phish_prone_percentage")),
                 "groups": [g.get("name") for g in c.get("groups") or []]} for c in found]
    else:
        rows = [{"campaign_id": c.get("campaign_id"), "name": c.get("name"), "status": c.get("status"),
                 "start_date": _date(c.get("start_date")) or None, "end_date": _date(c.get("end_date")) or None,
                 "completion_percent": c.get("completion_percentage"),
                 "groups": [g.get("name") for g in c.get("groups") or []]} for c in found]
    shown = rows[: _limit(limit)]
    period = _period_label(start_date, end_date)
    what = f"{kind} campaign(s)" + (f" matching '{query}'" if query else "") + (f" in {period}" if period else "")
    return {
        "console": console,
        "kind": kind,
        "headline": f"{len(found)} {what}." if found else f"No {what}.",
        "period": period or "all data",
        "total": len(found),
        "shown": len(shown),
        "truncated": len(found) > len(shown),
        "campaigns": shown,
        "note": "Newest first. Start from the headline; list the campaigns as given. Do not add advice.",
    }


# user fields people break reports down by; the api's own names
ATTRIBUTES = ("department", "division", "location", "manager_name", "job_title", "organization", "employee_number",
              "custom_field_1", "custom_field_2", "custom_field_3", "custom_field_4")
EMPTY = "(kosong)"
VALUE_LIMIT = 30


ATTRIBUTE_NAMES = {"manager": "manager_name", "atasan": "manager_name", "title": "job_title", "jabatan": "job_title",
                   "departemen": "department", "departments": "department", "divisi": "division", "lokasi": "location",
                   "organisation": "organization", "organisasi": "organization"}


def normalise_attribute(name: Any) -> str:
    """the api's field name for what people call it ("jabatan" is job_title)"""
    attribute = str(name or "").strip().lower().replace(" ", "_")
    return ATTRIBUTE_NAMES.get(attribute, attribute)


async def list_dimension_values(kb: Any, console: str, attribute: str = "department", limit: int = VALUE_LIMIT) -> dict[str, Any]:
    """the values a user field takes among active users, with how many people have each, most first"""
    attribute = normalise_attribute(attribute)
    if attribute not in ATTRIBUTES:
        return {"console": console, "error": True, "message": f"attribute must be one of: {', '.join(ATTRIBUTES)}."}
    users = await kb.list_users(console, "active")
    counts = Counter(str(u.get(attribute)).strip() if str(u.get(attribute) or "").strip() else EMPTY for u in users)
    empty = counts.pop(EMPTY, 0)
    values = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    shown = values[: _limit(limit, VALUE_LIMIT)]
    if not values:
        headline = f"No active user has a {attribute} filled in ({len(users)} active users)."
    else:
        headline = (f"{len(values)} different {attribute} values among {len(users)} active users; "
                    f"{len(users) - empty} have one, {empty} have it empty.")
    return {
        "console": console,
        "attribute": attribute,
        "headline": headline,
        "active_users": len(users),
        "with_value": len(users) - empty,
        "empty": empty,
        "distinct": len(values),
        "truncated": len(values) > len(shown),
        "values": [{"value": v, "users": n} for v, n in shown],
        "note": "Start from the headline; list the values as given. Do not add advice.",
    }


# definitions from KnowBe4's own material (support articles 115010178267, 360018819194, 360001358728 and the training
# status article, read through search excerpts on 2026-11-12: the support site refuses automated reading) and the api
METRICS: dict[str, dict[str, str]] = {
    "risk_score": {
        "id": ("Risk score KnowBe4 (0–100; makin rendah makin baik) dihitung KnowBe4 untuk tiap pengguna, grup dan organisasi. "
               "Faktornya antara lain seberapa sering seseorang menjadi sasaran phishing, bagaimana ia bereaksi (klik atau "
               "melaporkan), kepatuhan pada kebijakan keamanan, dan faktor organisasi seperti produk keamanan yang belum dipakai. Skor diperbarui otomatis dan tidak bisa diubah manual. "
               "Tingkatan: Low 10–40, Medium 41–47, High 48–53, Critical 54–90."),
        "en": ("KnowBe4's risk score (0–100; lower is better) is calculated by KnowBe4 for each user, group and the organisation. "
               "Its factors include how often someone is targeted by phishing, how they react (clicking or reporting), security "
               "policy compliance, and organisational factors such as security products not in use. It updates automatically and cannot be changed by hand. "
               "Levels: Low 10–40, Medium 41–47, High 48–53, Critical 54–90."),
    },
    "phish_prone": {
        "id": ("Phish-prone % = jumlah kegagalan ÷ jumlah email phishing simulasi yang terkirim. Setiap tindakan tidak aman "
               "dihitung: klik tautan, membuka lampiran, mengaktifkan macro, mengisi data, membalas email, memindai QR code. "
               "Satu orang bisa gagal lebih dari sekali pada satu email, jadi angkanya bisa melebihi persentase orang yang gagal."),
        "en": ("Phish-prone % = failures ÷ simulated phishing emails delivered. Every unsafe action counts: clicking a link, "
               "opening an attachment, enabling macros, entering data, replying, scanning a QR code. One person can fail more "
               "than once on one email, so it can be higher than the share of people who failed."),
    },
    "users_failed": {
        "id": ("Persentase pengguna gagal (KnowBe4: Phish-failure Percentage) = jumlah orang yang gagal setidaknya sekali ÷ "
               "jumlah orang yang menerima tes. Setiap orang dihitung sekali, berapa pun tindakan tidak amannya."),
        "en": ("Users failed % (KnowBe4: Phish-failure Percentage) = people who failed at least once ÷ people who received the "
               "test. Each person counts once, however many unsafe actions they took."),
    },
    "report_rate": {
        "id": "Report rate = jumlah email simulasi yang dilaporkan (tombol Phish Alert) ÷ jumlah email yang terkirim.",
        "en": "Report rate = simulated emails reported (Phish Alert button) ÷ emails delivered.",
    },
    "failure_types": {
        "id": ("Jenis kegagalan di data KnowBe4: klik tautan, membuka lampiran, mengaktifkan macro, mengisi data di halaman "
               "palsu, membalas email, memindai QR code, dan menelepon nomor di email callback phishing. Membuka email saja tidak "
               "dihitung gagal."),
        "en": ("Failure types in KnowBe4's data: clicking a link, opening an attachment, enabling macros, entering data on the "
               "landing page, replying to the email, scanning a QR code, and calling the number in a callback phishing email. Only "
               "opening the email is not a failure."),
    },
    "training_status": {
        "id": ("Status training: Not Started (belum mulai), In Progress (sedang dikerjakan), Passed (selesai/lulus) dan "
               "Past Due (melewati batas waktu). Past Due adalah tanda tenggat; training yang Past Due tetap bisa diselesaikan."),
        "en": ("Training statuses: Not Started, In Progress, Passed (completed) and Past Due (past the deadline). Past Due is a "
               "deadline flag; Past Due training can still be completed."),
    },
    "campaign_vs_test": {
        "id": ("Kampanye phishing adalah pengaturan (grup sasaran, jadwal, template); setiap kali kampanye dijalankan, KnowBe4 "
               "membuat satu tes phishing (phishing security test). Satu kampanye bisa punya banyak tes."),
        "en": ("A phishing campaign is the set-up (target groups, schedule, templates); every time it runs, KnowBe4 creates one "
               "phishing security test. One campaign can have many tests."),
    },
    "completion": {
        "id": ("Persentase penyelesaian sebuah kampanye training diambil langsung dari KnowBe4. Hitungan per grup atau per "
               "orang di chatbot ini: yang selesai (Passed) ÷ semua yang terdaftar."),
        "en": ("A training campaign's completion % comes straight from KnowBe4. This chatbot's per-group or per-person "
               "figures are: completed (Passed) ÷ everyone enrolled."),
    },
}
METRIC_NAMES = {
    "risk": "risk_score", "risk score": "risk_score", "skor risiko": "risk_score", "risk level": "risk_score",
    "phish-prone": "phish_prone", "phish prone": "phish_prone", "ppp": "phish_prone", "phish_prone_percentage": "phish_prone",
    "users failed": "users_failed", "phish-failure": "users_failed", "phish failure": "users_failed",
    "report": "report_rate", "reporting": "report_rate", "report rate": "report_rate",
    "failure": "failure_types", "failures": "failure_types", "kegagalan": "failure_types",
    "status": "training_status", "past due": "training_status", "training status": "training_status",
    "campaign": "campaign_vs_test", "pst": "campaign_vs_test", "test": "campaign_vs_test",
    "completion": "completion", "penyelesaian": "completion",
}


def explain_metric(name: str = "", language: str = "id") -> dict[str, Any]:
    """fixed definitions, no api call; several names give several definitions"""
    language = language if language in ("id", "en") else "id"
    wanted = []
    text = (name or "").strip().lower().replace("_", " ")
    for part in [p.strip() for p in text.replace(" dan ", ",").replace(" and ", ",").replace(" vs ", ",").split(",") if p.strip()]:
        key = part.replace(" ", "_") if part.replace(" ", "_") in METRICS else METRIC_NAMES.get(part)
        if key is None:
            key = next((v for k, v in sorted(METRIC_NAMES.items(), key=lambda kv: -len(kv[0])) if k in part), None)
        if key and key not in wanted:
            wanted.append(key)
    if not wanted:
        return {"error": True, "message": f"Unknown metric. Use one of: {', '.join(METRICS)}.", "known": list(METRICS)}
    return {
        "definitions": [{"metric": key, "text": METRICS[key][language]} for key in wanted],
        "note": "Give these definitions in your own words without changing their meaning; add nothing from general knowledge.",
    }
