"""Charts (PNG) and CSV files the chat can hand out.

Everything is drawn or written in code from KnowBe4 data; the model only picks which one.
Charts land in web/static/charts (served under /static/charts), CSV files in exports/
(served only by /exports/<id>.csv), and both are deleted after an hour.
"""
from __future__ import annotations

import csv
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no window, safe in a server process
import matplotlib.pyplot as plt  # noqa: E402

from kb4_mcp.products import _all_messages, reported_emails  # noqa: E402
from kb4_mcp.summaries import (  # noqa: E402
    _bad_period,
    _date,
    _name,
    _period_label,
    _r,
    _test_percent,
    _within,
    risk_by_group,
    risk_level,
    training_by_module,
)

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
CHART_DIR = STATIC / "charts"
# csv files hold names and emails, so they stay out of /static and are served only by /exports/<id>.csv
EXPORT_DIR = Path(__file__).resolve().parents[1] / "exports"
KEEP_SECONDS = 3600

CHARTS = ("risk_trend", "users_by_level", "top_users", "phishing_tests", "training_completion", "groups", "modules", "group_trend",
          "reported_emails")
# charts of data over time; the others show today's state, which has no period
PERIOD_CHARTS = {"risk_trend", "phishing_tests", "training_completion", "group_trend", "reported_emails"}
DATASETS = ("users", "phishing_tests", "training_campaigns", "risk_history", "modules", "reported_emails")

LEVEL_ORDER = ["Low", "Medium", "High", "Critical"]
LEVEL_COLOURS = {"Low": "#16a34a", "Medium": "#f59e0b", "High": "#ea580c", "Critical": "#dc2626"}
ACCENT = "#0071E3"
STATUS_COLOURS = {"passed": "#16a34a", "in_progress": ACCENT, "not_started": "#94a3b8", "past_due": "#dc2626"}

LABELS = {
    "id": {
        "risk_trend": "Risk score dari waktu ke waktu",
        "risk_trend_user": "Risk score {name} dari waktu ke waktu",
        "users_by_level": "Pengguna aktif per level risiko",
        "top_users": "{n} pengguna dengan risk score tertinggi",
        "phishing_tests": "Phish-prone % per tes phishing (terbaru)",
        "training_completion": "Penyelesaian training per kampanye (terbaru)",
        "groups": "{n} grup dengan risk score tertinggi",
        # short: long module names push the plot (and a left-aligned title) to the right
        "modules": "Status per modul ({n} terbanyak peserta)",
        "reported_emails": "Email yang dilaporkan ke PhishER per bulan",
        "reports": "Laporan",
        "enrolments": "Pendaftaran",
        "enrolments_share": "% pendaftaran (angka di kanan: % lulus · jumlah pendaftaran)",
        "statuses": {"passed": "Lulus", "in_progress": "Sedang dikerjakan", "not_started": "Belum mulai", "past_due": "Lewat tenggat"},
        "group_trend": "Risk score grup {name} dari waktu ke waktu",
        "no_group": "Pilih satu grup untuk grafik ini (group_id dari group_risk_trend).",
        "no_history": "Belum ada riwayat risk score untuk grafik ini.",
        "no_data": "Belum ada data KnowBe4 untuk grafik ini.",
        "today": "hari ini",
        "date": "Tanggal",
        "score": "Risk score",
        "percent": "%",
        "levels": {"Low": "Rendah", "Medium": "Sedang", "High": "Tinggi", "Critical": "Kritis"},
    },
    "en": {
        "risk_trend": "Risk score over time",
        "risk_trend_user": "{name}'s risk score over time",
        "users_by_level": "Active users per risk level",
        "top_users": "Top {n} users by risk score",
        "phishing_tests": "Phish-prone % per phishing test (latest)",
        "training_completion": "Training completion per campaign (latest)",
        "groups": "Top {n} groups by risk score",
        "modules": "Status per module (top {n} by enrolments)",
        "reported_emails": "Emails reported to PhishER per month",
        "reports": "Reports",
        "enrolments": "Enrolments",
        "enrolments_share": "% of enrolments (right: % passed · enrolments)",
        "statuses": {"passed": "Passed", "in_progress": "In progress", "not_started": "Not started", "past_due": "Past Due"},
        "group_trend": "Group {name}'s risk score over time",
        "no_group": "Pick one group for this chart (group_id from group_risk_trend).",
        "no_history": "There is no risk score history to chart yet.",
        "no_data": "There is no KnowBe4 data for this chart yet.",
        "today": "today",
        "date": "Date",
        "score": "Risk score",
        "percent": "%",
        "levels": {"Low": "Low", "Medium": "Medium", "High": "High", "Critical": "Critical"},
    },
}


def _cleanup(folder: Path) -> None:
    cutoff = time.time() - KEEP_SECONDS
    for f in folder.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _new_file(folder: Path, suffix: str) -> tuple[Path, str]:
    folder.mkdir(parents=True, exist_ok=True)
    _cleanup(folder)
    name = f"{uuid.uuid4().hex}{suffix}"
    return folder / name, f"/static/{folder.name}/{name}"


def _short(text: Any, width: int = 28) -> str:
    text = str(text or "-")
    return text if len(text) <= width else text[: width - 1] + "…"


def _bar_label(name: Any, when: Any) -> str:
    return f"{_short(name, 34)}  ·  {_date(when)}" if _date(when) else _short(name, 34)


def _hbars(fig: Any, ax: Any, labels: list[str], values: list[float], fmt: str, xlabel: str, top: float | None = None) -> None:
    """long test and campaign names overlapped under vertical bars; horizontal bars give every name its own line"""
    fig.set_size_inches(8, max(3.2, 0.42 * len(labels) + 1.6))
    ax.barh(range(len(labels)), values, color=ACCENT)
    ax.set_yticks(range(len(labels)), labels, fontsize=8)
    limit = max([top or 0, *values, 1])
    ax.set_xlim(0, limit * 1.15)
    for i, v in enumerate(values):
        ax.text(v + limit * 0.01, i, fmt.format(v), va="center", fontsize=8)
    ax.set_xlabel(xlabel)


def _save(fig: Any) -> str:
    path, url = _new_file(CHART_DIR, ".png")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return url


async def make_chart(
    kb: Any, console: str, chart: str, language: str = "id", user_id: int | None = None, limit: int = 10,
    start_date: str | None = None, end_date: str | None = None, group_id: int | None = None,
) -> dict[str, Any]:
    if problem := _bad_period(start_date, end_date):
        return {"error": True, "message": problem}
    if chart not in CHARTS:
        return {"error": True, "message": f"Unknown chart '{chart}'. Use one of: {', '.join(CHARTS)}."}
    t = LABELS.get(language, LABELS["id"])
    limit = max(1, min(int(limit or 10), 20))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    try:
        summary: dict[str, Any] = {}

        if chart in ("risk_trend", "group_trend"):
            if chart == "group_trend":
                if not group_id:
                    return {"error": True, "message": t["no_group"]}
                group = await kb.get_group(console, group_id)
                history = await kb.get_group_risk_history(console, group_id, bool(start_date or end_date))
                title = t["group_trend"].format(name=group.get("name") if isinstance(group, dict) else group_id)
            elif user_id:
                user = await kb.get_user(console, user_id)
                history = await kb.get_user_risk_history(console, user_id, bool(start_date or end_date))
                title = t["risk_trend_user"].format(name=_name(user) if isinstance(user, dict) else user_id)
            else:
                history = await kb.get_account_risk_history(console, bool(start_date or end_date))
                title = t["risk_trend"]
            points = sorted((_date(h.get("date")), h.get("risk_score")) for h in history or []
                            if isinstance(h.get("risk_score"), (int, float)) and _within(h.get("date"), start_date, end_date))
            if not points:
                return {"error": True, "message": t["no_history"]}
            xs = [date.fromisoformat(d) for d, _ in points]
            ys = [s for _, s in points]
            ax.plot(xs, ys, color=ACCENT, linewidth=2, marker="o", markersize=3)
            for upper, name in [(40, "Low"), (47, "Medium"), (53, "High")]:
                ax.axhline(upper, color=LEVEL_COLOURS[name], linewidth=0.8, linestyle="--", alpha=0.6)
            ax.set_ylabel(t["score"])
            ax.set_xlabel(t["date"])
            fig.autofmt_xdate()
            summary = {
                "points": len(points),
                "from": points[0][0] if points else None,
                "to": points[-1][0] if points else None,
                "first_score": _r(ys[0]) if ys else None,
                "last_score": _r(ys[-1]) if ys else None,
                "dashed_lines": "level borders at 40 (Low/Medium), 47 (Medium/High), 53 (High/Critical)",
            }

        elif chart == "users_by_level":
            users = await kb.list_users(console, "active")
            counts = {lvl: 0 for lvl in LEVEL_ORDER}
            for u in users:
                lvl = risk_level(u.get("current_risk_score"))
                if lvl:
                    counts[lvl] += 1
            shown = [lvl for lvl in LEVEL_ORDER if counts[lvl]]
            ax.pie(
                [counts[lvl] for lvl in shown],
                labels=[f"{t['levels'][lvl]} ({counts[lvl]})" for lvl in shown],
                colors=[LEVEL_COLOURS[lvl] for lvl in shown],
                autopct="%1.0f%%",
                startangle=90,
                wedgeprops={"edgecolor": "white"},
            )
            ax.axis("equal")
            title = t["users_by_level"]
            summary = {"active_users": len(users), "users_per_level": {lvl: counts[lvl] for lvl in shown}}

        elif chart == "top_users":
            users = await kb.list_users(console, "active")
            scored = sorted((u for u in users if isinstance(u.get("current_risk_score"), (int, float))), key=lambda u: u["current_risk_score"], reverse=True)[:limit]
            names = [_short(_name(u), 24) for u in scored][::-1]
            scores = [u["current_risk_score"] for u in scored][::-1]
            ax.barh(names, scores, color=[LEVEL_COLOURS[risk_level(s)] for s in scores])
            for i, s in enumerate(scores):
                ax.text(s + 0.3, i, f"{s:.1f}", va="center", fontsize=8)
            ax.set_xlabel(t["score"])
            title = t["top_users"].format(n=len(scored))
            summary = {"users": [{"name": _name(u), "risk_score": _r(u["current_risk_score"]), "risk_level": risk_level(u["current_risk_score"])} for u in scored]}

        elif chart == "phishing_tests":
            tests = sorted((x for x in await kb.list_phishing_security_tests(console) if _within(x.get("started_at"), start_date, end_date)),
                           key=lambda x: str(x.get("started_at") or ""), reverse=True)[:limit]
            tests = tests[::-1]
            values = [_test_percent(x.get("phish_prone_percentage")) or 0 for x in tests]
            _hbars(fig, ax, [_bar_label(x.get("name"), x.get("started_at")) for x in tests], values, "{:.1f}%", t["percent"])
            title = t["phishing_tests"]
            summary = {"tests": [{"name": x.get("name"), "started_at": _date(x.get("started_at")), "phish_prone_percent": v} for x, v in zip(tests, values, strict=True)]}

        elif chart == "groups":
            data = await risk_by_group(kb, console, "group", limit)
            rows = [g for g in data["groups"] if isinstance(g.get("risk_score"), (int, float))][::-1]
            names = [_short(g["name"], 24) for g in rows]
            scores = [g["risk_score"] for g in rows]
            ax.barh(names, scores, color=[LEVEL_COLOURS[risk_level(s)] for s in scores])
            for i, s in enumerate(scores):
                ax.text(s + 0.3, i, f"{s:.1f}", va="center", fontsize=8)
            ax.set_xlabel(t["score"])
            title = t["groups"].format(n=len(rows))
            summary = {"groups": [{"name": g["name"], "risk_score": g["risk_score"], "risk_level": g["risk_level"], "active_users": g["active_users"]} for g in rows[::-1]]}

        elif chart == "reported_emails":
            data = await reported_emails(kb, console, start_date=start_date, end_date=end_date)
            months = data.get("per_month") or {}
            ax.bar(list(months), list(months.values()), color=ACCENT)
            for i, n in enumerate(months.values()):
                ax.text(i, n, str(n), ha="center", va="bottom", fontsize=8)
            ax.set_ylabel(t["reports"])
            ax.tick_params(axis="x", labelsize=8, rotation=45)
            title = t["reported_emails"]
            summary = {"per_month": months, "by_category": data.get("by_category"), "still_open": data.get("still_open")}

        elif chart == "modules":
            # stacked statuses: bars of completion % alone were all empty when the lowest modules sat at 0%
            data = await training_by_module(kb, console, None, "most_enrolled", limit)
            rows = data.get("modules", [])[::-1]
            fig.set_size_inches(8, max(3.2, 0.42 * len(rows) + 1.9))
            # shares, not counts: one series with 1,548 enrolments squashed the other rows to slivers
            left = [0.0] * len(rows)
            for key in ("passed", "in_progress", "not_started", "past_due"):
                values = [m[key] * 100 / m["enrolled"] if m["enrolled"] else 0 for m in rows]
                ax.barh(range(len(rows)), values, left=left, color=STATUS_COLOURS[key], label=t["statuses"][key])
                left = [a + b for a, b in zip(left, values, strict=True)]
            ax.set_yticks(range(len(rows)), [_short(m["module"], 40) for m in rows], fontsize=8)
            for i, m in enumerate(rows):
                ax.text(101.5, i, f"{m['completion_percent'] or 0:.0f}% · {m['enrolled']}", va="center", fontsize=8)
            ax.set_xlim(0, 118)
            ax.set_xticks([0, 25, 50, 75, 100])
            ax.set_xlabel(t["enrolments_share"])
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.32 if len(rows) < 6 else -0.18), ncol=4, fontsize=8, frameon=False)
            title = t["modules"].format(n=len(rows))
            summary = {"modules": [{k: m[k] for k in ("module", "enrolled", "passed", "past_due", "not_started", "in_progress",
                                                       "completion_percent")} for m in rows[::-1]],
                       "bars": "stacked per module: passed, in progress, not started, Past Due; the % is completion"}

        else:  # training_completion
            campaigns = sorted((c for c in await kb.list_training_campaigns(console) if _within(c.get("start_date"), start_date, end_date)),
                               key=lambda c: str(c.get("start_date") or ""), reverse=True)[:limit]
            campaigns = campaigns[::-1]
            values = [c.get("completion_percentage") if isinstance(c.get("completion_percentage"), (int, float)) else 0 for c in campaigns]
            _hbars(fig, ax, [_bar_label(c.get("name"), c.get("start_date")) for c in campaigns], values, "{:.0f}%", t["percent"], top=100)
            title = t["training_completion"]
            summary = {"campaigns": [{"name": c.get("name"), "start_date": _date(c.get("start_date")), "completion_percentage": v} for c, v in zip(campaigns, values, strict=True)]}

        if not ax.has_data():
            return {"error": True, "message": t["no_data"]}
        period = _period_label(start_date, end_date) if chart in PERIOD_CHARTS else None
        # room above the plot for the period line under the title
        ax.set_title(title, fontsize=11, fontweight="bold", loc="left", pad=20 if period else 6)
        if period:
            # its own line, in the chart's language: one long title line was cut off on the right
            ax.text(0, 1.01, f"{(start_date or '…')[:10]} – {(end_date or '')[:10] or t['today']}",
                    transform=ax.transAxes, fontsize=9, color="#555555", va="bottom")
            title = f"{title} ({(start_date or '…')[:10]} – {(end_date or '')[:10] or t['today']})"
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        url = _save(fig)
        return {"chart": chart, "title": title, "image_url": url, "summary": summary, "period": period or "all data",
                "note": "The image is attached to your answer automatically. Explain what it shows; do not write the link."}
    finally:
        # _save closes it too; this covers a fetch that fails half-way
        plt.close(fig)


def _cell(value: Any) -> Any:
    # spreadsheet apps run cells starting with these as formulas (csv injection)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


async def export_csv(
    kb: Any, console: str, dataset: str, user_id: int | None = None, status: str = "active",
    start_date: str | None = None, end_date: str | None = None,
) -> dict[str, Any]:
    if problem := _bad_period(start_date, end_date):
        return {"error": True, "message": problem}
    if dataset not in DATASETS:
        return {"error": True, "message": f"Unknown dataset '{dataset}'. Use one of: {', '.join(DATASETS)}."}

    if dataset == "users":
        header = ["id", "name", "email", "department", "job_title", "status", "risk_score", "risk_level", "phish_prone_percent"]
        rows = [
            [u.get("id"), _name(u), u.get("email"), u.get("department"), u.get("job_title"), u.get("status"),
             _r(u.get("current_risk_score")), risk_level(u.get("current_risk_score")), _r(u.get("phish_prone_percentage"))]
            # active by default, like every other users answer, so the totals match what the chat says
            for u in await kb.list_users(console, None if status in ("", "all") else status)
        ]
    elif dataset == "phishing_tests":
        header = ["pst_id", "campaign_id", "name", "started_at", "status", "delivered", "clicked", "data_entered", "reported", "phish_prone_percent"]
        rows = [
            [x.get("pst_id"), x.get("campaign_id"), x.get("name"), _date(x.get("started_at")), x.get("status"), x.get("delivered_count"),
             x.get("clicked_count"), x.get("data_entered_count"), x.get("reported_count"), _test_percent(x.get("phish_prone_percentage"))]
            for x in await kb.list_phishing_security_tests(console) if _within(x.get("started_at"), start_date, end_date)
        ]
    elif dataset == "training_campaigns":
        header = ["campaign_id", "name", "status", "start_date", "end_date", "completion_percentage"]
        rows = [
            [c.get("campaign_id"), c.get("name"), c.get("status"), _date(c.get("start_date")), _date(c.get("end_date")), c.get("completion_percentage")]
            for c in await kb.list_training_campaigns(console) if _within(c.get("start_date"), start_date, end_date)
        ]
    elif dataset == "modules":
        # every module on its own row in the file, episodes included
        data = await training_by_module(kb, console, None, "most_enrolled", 0, start_date, end_date, group_series=False)
        header = ["module", "type", "enrolled", "passed", "past_due", "in_progress", "not_started", "completion_percent", "typical_minutes"]
        rows = [[m["module"], m["type"], m["enrolled"], m["passed"], m["past_due"], m["in_progress"], m["not_started"],
                 m["completion_percent"], m["typical_minutes"]] for m in data.get("modules", [])]
    elif dataset == "reported_emails":
        messages, _ = await _all_messages(kb, console)
        header = ["reported_at", "subject", "from", "reported_by", "category", "severity", "status"]
        rows = [[_date(m.get("reportedAt")), m.get("subject"), m.get("from"), m.get("reportedBy"), m.get("category"), m.get("severity"),
                 m.get("actionStatus")] for m in messages if _within(m.get("reportedAt"), start_date, end_date)]
    else:  # risk_history
        history = [h for h in await (kb.get_user_risk_history(console, user_id, True) if user_id else kb.get_account_risk_history(console, True)) or []
                   if _within(h.get("date"), start_date, end_date)]
        header = ["date", "risk_score", "risk_level"]
        rows = [[_date(h.get("date")), _r(h.get("risk_score")), risk_level(h.get("risk_score"))] for h in history or []]

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup(EXPORT_DIR)
    file_id = uuid.uuid4().hex
    path = EXPORT_DIR / f"{file_id}.csv"
    # utf-8 with bom so excel shows indonesian names correctly
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows([[_cell(v) for v in row] for row in rows])
    suffix = f"_user{user_id}" if dataset == "risk_history" and user_id else ""
    file_name = f"{console}_{dataset}{suffix}_{date.today().isoformat()}.csv"
    url = f"/exports/{file_id}.csv?name={file_name}"
    return {
        "dataset": dataset,
        **({"status_filter": status or "all"} if dataset == "users" else {}),
        "period": (_period_label(start_date, end_date) or "all data") if dataset != "users" else "today's users (no period)",
        "rows": len(rows),
        "columns": header,
        "download_url": url,
        "file_name": file_name,
        "note": "The download link is attached to your answer automatically. Say what the file contains; do not write the link.",
    }
