from __future__ import annotations

import bisect
import json
import re
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent.llm import LLMClient
from agent.messages import DEFAULT_LANGUAGE, LANGUAGE_NAMES, msg
from agent.normalise import normalise_with_fixes
from agent.period import default_period, parse_period
from config.settings import AppConfig, load_config
from kb4_mcp.summaries import risk_level

SYSTEM_PROMPT_TEMPLATE = """
You are KnowBe4 Security Awareness Reporting Analyst.

You have read-only access to KnowBe4 Reporting API through MCP.

Today is {today}. Dates up to today are past or present, never the future.

Configured Consoles:
{console_lines}

Rules:
1. Every answer that contains KnowBe4 data must come from a tool call made for THIS question, even if the
   same data appeared earlier in the conversation. Never answer data from memory. Never invent values,
   user ids, names or rows.
2. Every tool that needs "console" MUST receive one of these console ids: {available_ids}.
   Consoles marked UNAVAILABLE have no API key; never call tools for them, tell the user they are not configured.
3. {default_rule}
4. Use the tools marked PREFER: account_risk_overview (the organisation's risk and trend),
   user_risk_summary (one person's risk and history), find_user, list_users_page (lists of users),
   top_users_by_risk, compare_consoles_risk, phishing_campaign_summary, training_completion_summary,
   risk_by_group (groups, teams, departments), repeat_phishing_failures (people who failed several tests),
   phishing_test_detail (one test: who clicked, who reported, report rate, how fast people failed), overdue_training
   (Past Due training), training_by_module (progress per training module, course or video), training_library (which
   training content the company has), group_risk_trend (a group's risk over time), sign_in_activity (who never signed in),
   new_joiners (new employees), callback_phishing_summary (phone / callback phishing), make_chart (charts),
   export_csv (files), search_nist (NIST guidance). When available: industry_benchmark (official industry benchmark),
   reported_emails (emails employees reported as suspicious, PhishER), phisher_rules, usb_test_results,
   physical_qr_results, simulation_overview (all campaign and simulation types), admin_audit_log (what admins changed),
   security_coaching (Real-Time Coaching), password_risks (PasswordIQ), user_events (events from other security tools),
   product_status (which KnowBe4 products are in use).
5. Person questions: call find_user, then user_risk_summary with the id. "Full" or "selengkapnya" history
   also means user_risk_summary; the raw history is never shown. If several people match,
   list them numbered and ask which one.
6. The earlier conversation is included. Earlier answers end with a "[Data used: ...]" note for you
   (never show it). Resolve short replies with it: "2" or "yang kedua" means person 2 in the note's
   list, so call user_risk_summary with that id; "more", "lanjut", "next" or "show 20" means the next
   page, so call list_users_page with the note's next_offset; "21-40" means offset 20.
7. Risk score and phish-prone % are different metrics (see Definitions). Never call the risk score a phishing rate.
8. Never reveal API keys, tokens, Authorization headers, environment variables or credentials.
9. Answer in {answer_language} unless the user explicitly asks for another language.
10. The tools are read-only. Clearly refuse requests to create, change or delete anything in KnowBe4.
11. You cannot predict the future. If asked for a forecast or a future value, the answer must start with
    this sentence in bold: "**{no_prediction}**" Then offer the recent trend instead.
12. For long lists say "the first N of TOTAL" and offer to show the next ones. Never say "truncated".
13. Users from list_users_page: show one page (at most 20 users) per answer, even when asked for all users.
    Show every user as its own table row with columns No, Name, Risk score, Level and Phish-prone %.
    Never merge users into ranges. Then say which numbers of the total they are and offer the next 20.
14. Risk trends: the current score is live; history points are weekly snapshots. Describe the change from
    30 and 90 days ago to the current score, exactly as the tool gives it.
15. Write only in {answer_language}. Never use Chinese or any other script.
16. Charts: when asked for a chart, graph, grafik, diagram or visualisation, call make_chart. The image is
    attached to your answer automatically: never write image links. Explain what it shows from its summary.
17. Files: when asked to export, download, unduh, CSV or Excel, call export_csv. The download link is attached
    automatically: never write it. Say what the file contains and how many rows it has.
18. NIST guidance: for best practice, frameworks, how to run, measure or improve an awareness or training
    programme, how to reduce phishing clicks or risk, or how hard a phishing email is to spot, call search_nist with
    English keywords, even when the question does not mention NIST. Answer only from the passages it
    returns and cite them like (NIST SP 800-50r1, PDF page 69). When the question is also about our own data,
    combine it with the KnowBe4 tools.
19. Questions that are not about KnowBe4, security awareness or phishing (news, politics, general knowledge):
    say in one sentence that you only answer questions about this KnowBe4 data and security awareness. No numbers.
20. Periods ("dari 2026", "tahun lalu", "3 bulan terakhir"): the tools get the period automatically and their results
    say which period they cover. Without a period in the question they cover the past 12 months. Say the period in
    your first line. Never mix in data from outside it.
21. Training modules (modul, course, video, materi, a module's name): call training_by_module, with module set to words
    from the module's name when the question names one. Progress (watched, passed, finished, not started, overdue,
    time spent; "terbaik" = sort most_completed) is always training_by_module. For which content the company has, the newest
    ("terbaru": sort newest) or what to recommend, call training_library; recommend only from its facts (new or never assigned).
    Training campaigns are not modules; never answer a module question from training_completion_summary.
22. Benchmark or industry comparisons: call industry_benchmark when it is available (KnowBe4's official figures per
    industry and company size). Emails employees reported as suspicious in real life are reported_emails (PhishER);
    who reported a phishing TEST is phishing_test_detail. If a tool says a product is not set up or has no data, say so.

How to answer:
- First line: a one-sentence direct answer in bold. Never answer with questions back, never say "it depends".
  When a tool result has a "headline", base the first line on it and keep its numbers and names exactly.
- Then the key facts as short bullet points under the heading "{facts_heading}", with the important numbers in bold. Round numbers to at most
  2 decimals. Use plain words, never field names such as current_risk_score or phish_prone_percent.
- Then a short "{why_heading}" part that explains the numbers using only the tool data: the risk level,
  the trend (change over 30 and 90 days), phishing failures, training status (for example enrolments
  that are Past Due), and how it compares with others. If the data does not explain it, say so.
- Never calculate averages, totals or percentages yourself; use the figures the tools give.
- Never invent benchmarks, advice or reasons that are not in the tool data or the Definitions below.
  For example, do not write "the score fell because awareness improved" or "follow up with these users"
  unless a tool result says so.
- Stop after the "{why_heading}" part. Do not add suggested questions.

Definitions (KnowBe4):
- Risk score: 0-100 (shown between 10 and 90), higher = riskier. Levels: Low 10-40, Medium 41-47,
  High 48-53, Critical 54-90. Tool results already include the level.
- Phish-prone %: phishing failures (clicking, opening an attachment, entering data, and similar)
  divided by phishing emails delivered. For one person it can go above 100% when they fail in more than one way.
- Training completion %: the completion figure KnowBe4 reports for a training campaign.
- KnowBe4's 2026 global benchmark applies ONLY to phish-prone %, never to the risk score. Tool results
  include a ready-made comparison ("phish_prone_vs_benchmark"); use that wording instead of comparing yourself.
""".strip()

# exposed to mcp clients, but too open-ended for a small local model; the health check is an admin tool that
# gives a bare score (the model once answered "risk score?" with it instead of account_risk_overview)
HIDDEN_TOOLS = {"knowbe4_raw_get", "knowbe4_health_check", "refresh_data"}
# the user explicitly wants fresh data, not the 10-minute copy; "tes phishing terbaru" (the latest test) is not this
FRESH_ASK = re.compile(
    r"\b(?:refresh\w*|reload\w*|re-?fetch\w*|perbarui\w*|segarkan|muat ulang|ambil ulang|tarik ulang|update (?:the )?data"
    r"|data (?:yang )?(?:terbaru|terkini|paling baru|fresh|baru)|(?:fresh|new|latest|live|up[- ]to[- ]date) data"
    r"|(?:jangan|tanpa) (?:pakai |pake |gunakan )?cache|no cache|(?:without|ignore|skip) (?:the )?cache|real[- ]?time)\b",
    re.I,
)
# per earlier message sent back with a question
HISTORY_CHARS = 2000
# blocked in the same answer once find_user has asked "which one?"
PERSON_DETAIL_TOOLS = {"user_risk_summary", "get_user", "get_user_risk_score_history"}
# a second call in the same answer is refused, so "show all" gives one page plus an offer
ONE_PER_ANSWER_TOOLS = {"list_users_page"}
# qwen sometimes slips into chinese mid-answer; such an answer is rewritten once
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
# raw lists and histories flood a small model (one history is up to 1,000 points); the summary tools cover them
RAW_LIST_TOOLS = {
    "list_users",
    "get_user_risk_score_history",
    "get_account_risk_score_history",
    "get_group_risk_score_history",
    "list_training_enrollments",
    "list_phishing_recipients",
    "list_group_members",
}


def build_system_prompt(config: AppConfig, language: str = DEFAULT_LANGUAGE) -> str:
    lines = []
    available = []
    for key, console in config.consoles.items():
        if console.has_api_key:
            available.append(key)
            lines.append(f"- {key} : {console.display_name}")
        else:
            lines.append(f"- {key} : {console.display_name} (UNAVAILABLE: no API key configured)")

    if available:
        default_rule = f'If the user does not specify a console, default to console="{available[0]}".'
    else:
        default_rule = "No console has an API key; tell the user that KnowBe4 is not configured."

    return SYSTEM_PROMPT_TEMPLATE.format(
        console_lines="\n".join(lines) or "- (none)",
        available_ids=", ".join(f'"{k}"' for k in available) or "(none)",
        default_rule=default_rule,
        answer_language=LANGUAGE_NAMES.get(language, LANGUAGE_NAMES[DEFAULT_LANGUAGE]),
        no_prediction=msg("no_prediction", language),
        why_heading=msg("why_heading", language),
        facts_heading=msg("facts_heading", language),
        # without it the model reasons from its training date and called 2026 "the future"
        today=date.today().isoformat(),
    )


def _error(message: str) -> str:
    return json.dumps({"error": True, "message": message}, ensure_ascii=False)


def _note_for(name: str, args: dict[str, Any], text: str) -> str:
    """one line of what a tool returned, kept with the answer so follow-ups ("2", "lanjut") resolve reliably"""
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict) and name == "list_users_page":
        return f"list_users_page sort={data.get('sort')} showing {data.get('showing')} next_offset={data.get('next_offset')}"
    if isinstance(data, dict) and name == "find_user":
        matches = data.get("matches") or []
        names = Counter(m.get("name") for m in matches)

        def who(m: dict[str, Any]) -> str:
            # two people with the same full name were listed identically in "which one?"
            if names[m.get("name")] < 2:
                return str(m.get("name"))
            extra = [str(m.get("email") or m.get("department") or m.get("job_title") or "")]
            if m.get("status") and m.get("status") != "active":
                extra.append(str(m.get("status")))
            return " · ".join([str(m.get("name")), *(e.replace(",", " ") for e in extra if e)])

        people = ", ".join(f"{i + 1}. {who(m)} (id {m.get('id')})" for i, m in enumerate(matches))
        return f"find_user '{args.get('query')}': {people or 'no matches'}"
    if isinstance(data, dict) and name == "user_risk_summary":
        user = data.get("user") or {}
        return f"user_risk_summary {user.get('name')} (id {user.get('id')})"
    shown = {k: v for k, v in args.items() if k != "console"}
    return f"{name} {json.dumps(shown, ensure_ascii=False)}" if shown else name


def _with_users_table(answer: str, page: dict[str, Any], language: str) -> str:
    """the model invented rows and totals when copying a 20-row table, so the heading and table come from the data"""
    users = page.get("users") or []
    if not users:
        return answer
    first, last = users[0].get("number"), users[-1].get("number")
    lines = [
        f"**{msg('users_page_heading', language, first=first, last=last, total=page.get('total_users'), order=msg('order_name' if page.get('sort') == 'by name' else 'order_risk', language))}**",
        "",
        msg("users_table_header", language),
        "|---|---|---|---|---|",
    ]
    for u in users:
        ppp = u.get("phish_prone_percent")
        lines.append(
            f"| {u.get('number')} | {u.get('name')} | {u.get('risk_score')} | {u.get('risk_level') or '-'} | "
            f"{'-' if ppp is None else f'{ppp}%'} |"
        )
    # keep only the model's explanation: drop its own headline and any table it wrote
    rest = [ln for ln in answer.splitlines() if not ln.lstrip().startswith("|")]
    if rest and rest[0].lstrip().startswith("**"):
        rest = rest[1:]
    text = "\n".join(lines) + "\n\n" + "\n".join(rest).strip()
    if page.get("next_offset") is not None:
        text += "\n\n" + msg("users_page_more", language)
    return text.strip()


RISK_WORDS = re.compile(r"\b(risk|risiko|skor|score)\b", re.I)
# a level written next to a risk score: "38.01 (level Medium)", "38,01 (Sedang)", "skor 38.01 dengan level Low"
LEVEL_NEAR_SCORE = re.compile(
    r"(?P<num>(?<![\d.,])\d{2}(?:[.,]\d+)?)(?![\d%])(?P<gap>[^.\n\d%|]{0,25}?(?:\(|\blevel\b|\btingkat\b)[^.\n\d%|]{0,12}?)"
    r"(?P<level>Low|Medium|High|Critical|Rendah|Sedang|Tinggi|Kritis)\b",
    re.I,
)
LEVEL_NAMES = {
    "en": {"Low": "Low", "Medium": "Medium", "High": "High", "Critical": "Critical"},
    "id": {"Low": "Rendah", "Medium": "Sedang", "High": "Tinggi", "Critical": "Kritis"},
}
INDONESIAN_LEVELS = {"rendah", "sedang", "tinggi", "kritis"}


# misspellings the model wrote in indonesian answers ("Prodak KnowBe4", "Kampain", "Kampayan"); whole words only
ANSWER_TYPOS = {"prodak": "produk", "kampain": "kampanye", "kampayan": "kampanye", "kampanya": "kampanye"}
ANSWER_TYPO = re.compile(r"\b(" + "|".join(ANSWER_TYPOS) + r")\b", re.I)
# 14.31 -> 14,31 (one or two decimals); never 2.233 (indonesian thousands), 1.64.1, ip addresses, 800-50r1 or dates
ID_DECIMAL = re.compile(r"(?<![\w.,/-])(\d+)\.(\d{1,2})(?![\d\w]|\.\d)")


def _fix_typos_in_answer(answer: str) -> str:
    def fix(m: re.Match[str]) -> str:
        right = ANSWER_TYPOS[m.group(1).lower()]
        return right.capitalize() if m.group(1)[0].isupper() else right

    def tidy(text: str) -> str:
        # indonesian writes decimals with a comma; the model mixed "14.31%" with the risk line's "38,01"
        return ID_DECIMAL.sub(r"\1,\2", ANSWER_TYPO.sub(fix, text))

    # real names stay as KnowBe4 has them: quoted text ("Kampain Q3"), table rows and links are left alone
    lines = []
    for line in answer.split("\n"):
        if line.lstrip().startswith("|") or "](" in line:
            lines.append(line)
            continue
        parts = re.split(r'("[^"\n]*"|`[^`\n]*`|https?://\S+)', line)
        lines.append("".join(p if p[:1] in ('"', "`") or p.startswith("http") else tidy(p) for p in parts))
    return "\n".join(lines)


def _fix_levels(answer: str) -> str:
    """a level that contradicts KnowBe4's bands for the score next to it is corrected (the model once wrote
    38.01 as Medium; 38 is Low). only in sentences about the risk score, never on percentages"""
    def fix(m: re.Match[str]) -> str:
        try:
            score = float(m.group("num").replace(",", "."))
        except ValueError:
            return m.group(0)
        right = risk_level(score) if 10 <= score <= 90 else None
        written = m.group("level")
        names = LEVEL_NAMES["id" if written.lower() in INDONESIAN_LEVELS else "en"]
        if not right or names[right].lower() == written.lower():
            return m.group(0)
        return m.group("num") + m.group("gap") + names[right]

    # sentences and lines, keeping every separator so the layout is untouched
    parts = re.split(r"(\n|(?<=[.!?])[ \t]+)", answer)
    return "".join(LEVEL_NEAR_SCORE.sub(fix, p) if RISK_WORDS.search(p) else p for p in parts)
PERIOD_30 = re.compile(r"\b(30 hari|sebulan|satu bulan|1 bulan|30 days|a month|one month|last month)\b", re.I)
PERIOD_90 = re.compile(r"\b(90 hari|tiga bulan|3 bulan|90 days|three months|3 months|quarter|kuartal)\b", re.I)


def _with_risk_line(answer: str, summary: dict[str, Any], language: str, asked_period: Any = None) -> str:
    """the risk score answer's first line, from the data: the model once called the 30-day value "three months ago".
    only replaces a first line about the risk score, so "dia ada training yg telat?" keeps its own"""
    trend = summary.get("risk_trend") or {}
    current = summary.get("current") or {}
    score = current.get("score", trend.get("current_score"))
    level = current.get("level", trend.get("current_level"))
    if score is None:
        return answer
    lines = answer.splitlines()
    first = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first is None or not lines[first].lstrip().startswith("**") or not RISK_WORDS.search(lines[first]):
        return answer

    def num(value: Any) -> str:
        text = f"{value}"
        return text.replace(".", ",") if language == "id" else text

    person = (summary.get("user") or {}).get("name")
    subject = msg("risk_subject_person", language, name=person) if person else msg("risk_subject_org", language)
    parts = []
    for days in (30, 90):
        c = trend.get(f"change_vs_{days}_days_ago")
        if c:
            parts.append(msg("risk_then", language, days=days, score=num(c["from_score"]), change=num(f"{c['change']:+}")))
        else:
            parts.append(msg("risk_then_missing", language, days=days))
    period = summary.get("period")
    if asked_period is not None and isinstance(period, dict):
        # the summary's label is english; this one follows the chat
        start = asked_period.start.isoformat() if asked_period.start else msg("period_data_start", language)
        end = asked_period.end.isoformat() if asked_period.end else msg("period_today", language)
        label = f"{start} – {end}"
        if period.get("snapshots"):
            parts.append(msg("risk_period", language, period=label, score=num(period["first_snapshot"]["score"]),
                             date=period["first_snapshot"]["date"], change=num(f"{period['change']:+}")))
        else:
            parts.append(msg("risk_period_missing", language, period=label))
    line = msg("risk_line", language, subject=subject, score=num(score), level=level, then="; ".join(parts))
    lines[first] = f"**{line}**"
    # the body may still put a value under the other period ("47,18 tiga bulan lalu"): those sentences go,
    # the first line already has both right
    values = {d: (trend.get(f"change_vs_{d}_days_ago") or {}).get("from_score") for d in (30, 90)}

    def mentions(sentence: str, value: Any) -> bool:
        return value is not None and any(v in sentence for v in {f"{value}", f"{value}".replace(".", ",")})

    def wrong(sentence: str) -> bool:
        return (mentions(sentence, values[30]) and PERIOD_90.search(sentence) and not mentions(sentence, values[90])) or (
            mentions(sentence, values[90]) and PERIOD_30.search(sentence) and not mentions(sentence, values[30]))

    body = []
    for ln in lines[first + 1:]:
        marker = re.match(r"\s*(?:[-*]|\d+\.)\s+", ln)
        lead = marker.group(0) if marker else ""
        sentences = re.split(r"(?<=[.!?])\s+", ln[len(lead):])
        kept = [s for s in sentences if not wrong(s)]
        if len(kept) == len(sentences):
            body.append(ln)
        elif kept:
            body.append(lead + " ".join(kept))
    return "\n".join([*lines[: first + 1], *body])


# a number as written, not glued to letters ("KnowBe4") or other digits; "2.233", "39,4", "1,234.5"
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z\d.,])\d+(?:[.,]\d+)*")
# list numbers and small counts ("1.", "dua dari 3") are prose, not data
SMALL_COUNT = 10


def _readings(token: str) -> set[tuple[float, int]]:
    """every value a written number can mean, with its decimals: "2.233" is 2.233 or 2233, "39,4" is 39.4"""
    out = set()
    parts = re.split(r"[.,]", token)
    if len(parts) == 1:
        return {(float(token), 0)}
    # last separator as the decimal point
    out.add((float("".join(parts[:-1]) + "." + parts[-1]), len(parts[-1])))
    # every separator as thousands
    if all(len(p) == 3 for p in parts[1:]):
        out.add((float("".join(parts)), 0))
    return out


def _grounded_values(messages: list[dict[str, Any]]) -> list[float]:
    """every number the model was given this turn: system prompt, history, question and tool results"""
    values = set()
    for m in messages:
        for token in NUMBER_TOKEN.findall(str(m.get("content") or "")):
            values.update(v for v, _ in _readings(token))
    return sorted(values)


def _ungrounded_numbers(answer: str, grounded: list[float]) -> list[str]:
    def supported(token: str) -> bool:
        for value, decimals in _readings(token):
            if decimals == 0 and value <= SMALL_COUNT:
                return True
            # rounding is fine: 39.4 for 39.398, 86 for 85.62
            tol = 0.5 * 10 ** -decimals + 1e-9
            i = bisect.bisect_left(grounded, value - tol)
            if i < len(grounded) and grounded[i] <= value + tol:
                return True
        return False
    return list(dict.fromkeys(t for t in NUMBER_TOKEN.findall(answer) if not supported(t)))


def _drop_sentences_with(answer: str, numbers: list[str]) -> str:
    """last resort: remove every sentence that still carries a number the data does not contain"""
    bad = re.compile(r"(?<![A-Za-z\d.,])(" + "|".join(re.escape(n) for n in numbers) + r")(?![\d])")
    kept = []
    for line in answer.splitlines():
        if not bad.search(line):
            kept.append(line)
            continue
        # a bold sentence ends in ".**"
        sentences = [s for s in re.split(r"(?<=[.!?])\s+|(?<=[.!?]\*\*)\s+", line) if not bad.search(s)]
        if sentences:
            kept.append(" ".join(sentences))
    return "\n".join(kept).strip()


LANGUAGE_WORDS = {
    "id": {"adalah", "dan", "yang", "dengan", "dari", "untuk", "ini", "saat", "tidak", "pada", "dalam", "pengguna", "kenapa"},
    "en": {"the", "is", "and", "of", "with", "are", "this", "which", "for", "from", "users", "why", "current", "in", "it", "has"},
}


def _wrong_language(answer: str, language: str) -> bool:
    """after an english turn the model sometimes answers an indonesian question in english (and the other way round)"""
    words = re.findall(r"[a-z]+", answer.lower())
    if len(words) < 8 or language not in LANGUAGE_WORDS:
        return False
    other = "en" if language == "id" else "id"
    own_hits = sum(w in LANGUAGE_WORDS[language] for w in words)
    other_hits = sum(w in LANGUAGE_WORDS[other] for w in words)
    return (other_hits >= 3 and other_hits > 2 * own_hits) or (other_hits >= 2 and own_hits == 0)


MODEL_LINK = re.compile(r"!?\[[^\]]*\]\((?:/static/|/exports/|https?://)[^)]*\)")
# any image the model writes is made up (it once drew a broken "Detail tes phishing" image); only code adds images
MODEL_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _with_attachments(answer: str, made: list[dict[str, Any]], language: str) -> str:
    """charts and csv links come from the tool results; links the model wrote itself are dropped (it garbles them)"""
    parts = [MODEL_LINK.sub("", answer).strip()]
    for item in made:
        if item.get("image_url"):
            parts.append(f"![{item.get('title') or 'chart'}]({item['image_url']})")
        if item.get("download_url"):
            label = msg("download_csv", language, file=item.get("file_name"), rows=item.get("rows"))
            parts.append(f"**[{label}]({item['download_url']})**")
    return "\n\n".join(p for p in parts if p)


NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
USERS_WORD = re.compile(r"\b(users?|pengguna)\b", re.I)
# a reply that only picks an item: "2", "no 2", "nomor 2", "yang kedua"
PICK = re.compile(r"^\s*(?:no\.?|nomor|number|#)?\s*(\d{1,2})\s*[.!?]?\s*$|\byang\s+(pertama|kedua|ketiga|keempat|kelima)\b", re.I)
ORDINALS = {"pertama": 1, "kedua": 2, "ketiga": 3, "keempat": 4, "kelima": 5}
# "1. Rina Sari (id 100000001), 2. Rina Putri (id 100000002)" inside a find_user note
LISTED_PEOPLE = re.compile(r"(\d+)\. [^,;\]]*?\(id (\d+)\)")
WHY_ASK = re.compile(r"\b(kenapa|mengapa|why|alasan\w*|penyebab\w*)\b", re.I)
# the first tool of the last [Data used: ...] note: what a "why" follow-up is about
LAST_NOTE_TOOL = re.compile(r"\[Data used: (\w+)")
# summaries that need nothing but the console, so they can be fetched again as they are
REFETCH_TOOLS = {
    "account_risk_overview", "training_completion_summary", "phishing_campaign_summary", "overdue_training",
    "risk_by_group", "top_users_by_risk", "repeat_phishing_failures", "phishing_test_detail",
    "training_by_module", "training_library", "group_risk_trend", "sign_in_activity", "new_joiners", "callback_phishing_summary",
    "industry_benchmark", "reported_emails", "phisher_rules", "usb_test_results", "physical_qr_results", "simulation_overview",
    "admin_audit_log", "security_coaching", "password_risks", "user_events", "product_status",
}
# topics only one tool answers: (question pattern, tool to call, tools that already answer it). the model once
# answered module questions from training campaigns; when it skips the tool, the call is made in code
# real emails employees reported (PhishER), not who reported a phishing test
PHISHER_ASK = re.compile(
    r"\b(?:phisher|email (?:yang )?(?:mencurigakan|dilaporkan|di-?report\w*)|reported (?:emails?|messages?)|suspicious emails?|"
    r"phish alert|tombol (?:lapor|report)|email (?:asli|nyata) yang dilaporkan)\b",
    re.I,
)
# whole words: "tim\w*" took "over time" for a team
GROUP_WORD = r"\b(?:grup\w*|groups?|kelompok\w*|divisi\w*|departemen\w*|departments?|tim|teams?)\b"
TREND_WORD = (r"\b(?:tren\w*|trend\w*|dari waktu ke waktu|over time|membaik|memburuk|getting (?:better|worse)|improv\w*"
              r"|riwayat|history|naik|turun|perkembangan)\b")
TOPIC_TOOLS = (
    (re.compile(r"\b(?:apa saja|daftar|list|punya|tersedia|available|library|pustaka|katalog|catalog|dibeli|purchased|"
                r"terbaru|newest|latest|rekomendasi\w*|recommend\w*)\b"
                r"[^.?!]{0,40}\b(?:modul\w*|modules?|konten|content|materi|video\w*|courses?|kursus)\b"
                r"|\b(?:modul\w*|modules?|konten|content|materi|courses?|kursus)\b[^.?!]{0,40}"
                r"\b(?:apa saja|tersedia|available|yang (?:kita |kami )?punya|we have|purchased|dibeli)\b", re.I),
     "training_library", {"training_library", "training_by_module"}),
    (re.compile(r"\b(?:modul\w*|modules?|materi\w*|kursus|courses?|video\w*)\b", re.I),
     "training_by_module", {"training_by_module"}),
    (re.compile(r"\b(?:log ?in\w*|sign(?:ed)? ?in\w*|masuk ke knowbe4|belum pernah masuk)\b", re.I),
     "sign_in_activity", {"sign_in_activity"}),
    (re.compile(r"\b(?:karyawan|pegawai|pengguna|users?|staf|orang)\s+baru\b|\bnew\s+(?:joiners?|hires?|employees?|users?|staff|starters?)\b"
                r"|\bbaru\s+(?:bergabung|masuk|join\w*)\b|\bjoiners?\b", re.I),
     "new_joiners", {"new_joiners"}),
    (re.compile(r"\b(?:callback|vishing|voice phishing|phone phishing|telepon|menelepon|nelpon|ditelepon)\b", re.I),
     "callback_phishing_summary", {"callback_phishing_summary"}),
    (re.compile(GROUP_WORD + r"[^.?!]{0,60}" + TREND_WORD + "|" + TREND_WORD + r"[^.?!]{0,60}" + GROUP_WORD, re.I),
     "group_risk_trend", {"group_risk_trend"}),
    (re.compile(r"\b(?:seberapa cepat|berapa cepat|secepat|paling cepat|tercepat|how (?:fast|quickly)|fastest|berapa lama)\b"
                r"[^.?!]{0,50}\b(?:klik|click\w*|gagal|fail\w*|tertipu|kena)", re.I),
     "phishing_test_detail", {"phishing_test_detail"}),
    # product apis (skipped when the tool is not available)
    (PHISHER_ASK, "reported_emails", {"reported_emails", "phisher_rules"}),
    (re.compile(r"\b(?:benchmark\w*|industri\w*|industry|industries|rata-?rata (?:perusahaan|industri)|perusahaan lain|"
                r"organisasi lain|other companies|peers?)\b", re.I),
     "industry_benchmark", {"industry_benchmark"}),
    (re.compile(r"\b(?:usb|flash ?dis[ck]|flashdrive|flash drive|thumb ?drive)\b", re.I), "usb_test_results", {"usb_test_results"}),
    (re.compile(r"\b(?:qr (?:fisik|poster|physical)|physical qr|poster qr|kode qr fisik|qr di poster|qr code poster)\b", re.I),
     "physical_qr_results", {"physical_qr_results"}),
    (re.compile(r"\b(?:jenis (?:simulasi|kampanye|campaign)|simulasi apa (?:saja|aja)|semua simulasi|campaign types?|"
                r"kinds? of (?:simulations?|campaigns?)|simulations? do we run)\b", re.I),
     "simulation_overview", {"simulation_overview"}),
    (re.compile(r"\b(?:audit ?log\w*|log admin|admin log|perubahan (?:admin|pengaturan|setting\w*)|siapa (?:yang )?(?:mengubah|ubah|ganti)|"
                r"who changed|admin (?:changes|activity)|aktivitas admin)\b", re.I),
     "admin_audit_log", {"admin_audit_log"}),
    (re.compile(r"\b(?:real[- ]?time coaching|securitycoach|security coach|coaching)\b", re.I), "security_coaching", {"security_coaching"}),
    (re.compile(r"\b(?:passwords?|kata sandi|passwordiq|sandi)\b", re.I), "password_risks", {"password_risks"}),
    (re.compile(r"\b(?:user events?|custom events?|event (?:dari|from) (?:tool|alat)|dlp|edr)\b", re.I), "user_events", {"user_events"}),
    (re.compile(r"\b(?:produk (?:knowbe4 )?(?:apa|mana)|knowbe4 products?|products? (?:are|do we)|lisensi|licen[cs]e)\b", re.I),
     "product_status", {"product_status"}),
    # last: a plain risk score question answered from the bare account record lost its level, trend and why
    # (38.01 was once called Medium); any summary that already answers it counts
    (re.compile(r"\b(?:risk ?score|skor risiko|risiko skor|skor risk|nilai risiko|tingkat risiko|risk level)\b", re.I),
     "account_risk_overview", {"account_risk_overview", "user_risk_summary", "top_users_by_risk", "risk_by_group", "group_risk_trend",
                               "list_users_page", "compare_consoles_risk", "find_user", "industry_benchmark", "new_joiners",
                               "sign_in_activity", "make_chart", "export_csv", "search_nist"}),
)
OVERDUE_WORDS = re.compile(r"\b(?:telat|terlambat|overdue|past due|tenggat|lewat)\b", re.I)
# "which content do we have" asks about the library; progress (watched, passed, not started) never does
LIBRARY_TOPIC_EXCLUDES = re.compile(r"\b(?:belum|sudah|lulus|selesai\w*|ditonton|nonton|progres\w*|passed|finished|watched|completion|penyelesaian\w*)\b", re.I)


def _topic_answered(topic: tuple[Any, str, set[str]], prompt: str, state: dict[str, Any]) -> bool:
    """nothing to force: a tool that covers the topic was used, or it is a progress question, which the library
    never answers. overdue training lists the most overdue modules, so it covers module questions about lateness,
    not "how is completion of the modules from 2026" """
    if topic[1] == "training_library" and LIBRARY_TOPIC_EXCLUDES.search(prompt):
        return True
    covered = set(topic[2])
    if topic[1] == "training_by_module" and OVERDUE_WORDS.search(prompt):
        covered.add("overdue_training")
    return any(state.get(x) for x in covered)


NAMED_PEOPLE = re.compile(r"(\d+)\. ([^,;\]]*?) \(id (\d+)\)")
# a person referred to, not "-nya" on any word ("organisasinya")
PERSON_PRONOUN = re.compile(r"\b(dia|beliau|orang itu|orangnya|he|she|him|her|his)\b", re.I)
# who reported a phishing email ("yg report brp", "berapa yang melaporkan", "report rate")
# questions about the future, where the "cannot predict" line belongs
FUTURE_ASK = re.compile(
    r"\b(depan|nanti|besok|akan datang|ke depannya|prediksi\w*|perkiraan|proyeksi|forecast\w*|predict\w*|future|next (?:week|month|quarter|year)|will)\b",
    re.I,
)
# a first line that already refuses a forecast in the model's own words
PREDICT_WORD = re.compile(r"\b(?:prediksi\w*|memprediksi|meramal\w*|forecast\w*|predict\w*|perkira\w*)\b", re.I)
NEGATION = re.compile(r"\b(?:tidak|tak|belum|bukan|cannot|can't|can ?not|unable|not able)\b", re.I)
# not "laporan" (a report document) or "reporting"
REPORT_ASK = re.compile(r"\b(report(?:ed|s|nya)?|report rate|(?:me)?lapor(?:kan|kannya|nya)?|dilaporkan)\b", re.I)
PHISHING_TOPIC = re.compile(r"phish|phising|email palsu|simulasi", re.I)
NIST_ASK = re.compile(r"\b(nist|phish\s*scale|csf|800-50|framework|kerangka|best practice|praktik terbaik|menurut standar)\b", re.I)
# guidance questions use the NIST library even when nobody says "NIST": how to run, measure or improve awareness
GUIDANCE_ASK = re.compile(
    r"\b(bagaimana cara|gimana cara|cara (?:mengukur|meningkatkan|menurunkan|mengurangi|membuat|menjalankan|melatih|mencegah)"
    r"|how (?:to|do|can|should)|tips|saran|rekomendasi|recommend\w*|sebaiknya|apa yang (?:harus|perlu)|langkah|strategi\w*|strateg(?:y|ies)"
    r"|improve|meningkatkan|tingkatkan|menurunkan|mengurangi|reduce|efektivitas|efektif|effective\w*|mengukur|measure\w*|metrik|metrics?"
    r"|kenapa penting|why (?:is|does) .{0,20}matter)\b",
    re.I,
)
AWARENESS_TOPIC = re.compile(
    r"\b(training|pelatihan|awareness|kesadaran|phishing|simulasi|simulation|program|karyawan|employees?|staff|keamanan|security|risiko|risk|klik|click)\w*",
    re.I,
)
# "apa saja yang bisa kamu lakukan?" / "what can you do?": the whole question, so "apa yang bisa kamu lakukan untuk
# menurunkan risiko" still goes to the model. the model's own version opened with the off-topic line and listed
# features that don't exist (excel, departments, several consoles), so the answer is fixed text
CAPABILITY_ASK = re.compile(
    r"^\W*(?:(?:hai|halo|hello|hi|hey)\W+)?(?:"
    r"(?:apa\s+(?:saja\s+)?)?(?:yang\s+)?(?:bisa|dapat)\s+(?:kamu|anda|kau|lo|lu|bot\s+ini|chatbot\s+ini)\s+(?:lakukan|bantu|kerjakan)"
    r"|apa\s+(?:saja\s+)?(?:yang\s+)?(?:kamu|anda|kau|lo|lu)\s+(?:bisa|dapat|mampu)(?:\s+(?:lakukan|bantu|kerjakan))?"
    r"|(?:kamu|anda|kau|lo|lu)?\s*(?:bisa|dapat|mampu)\s+(?:bantu\s+)?(?:apa|ngapain)"
    r"|(?:apa\s+(?:saja\s+)?)?(?:fitur|kemampuan|kapabilitas|keahlian|fungsi)(?:mu|nya|\s+(?:kamu|anda|kau|lo|lu|bot\s+ini|chatbot\s+ini))?(?:\s+apa)?"
    r"|what\s+(?:can|could)\s+(?:you|this\s+bot)\s+(?:do|help\s+(?:me\s+)?with)"
    r"|what\s+are\s+you\s+(?:capable|able)\s+of(?:\s+doing)?"
    r"|what\s+do\s+you\s+do"
    r"|(?:what\s+are\s+)?your\s+(?:capabilit(?:y|ies)|features|skills)"
    r"|capabilit(?:y|ies)|help|bantuan|menu"
    r")(?:\s+(?:saja|sih|ya|dong|ini|itu|nya|for\s+me|untuk\s+saya|buat\s+saya))*\W*$",
    re.I,
)
# tools that take start_date / end_date; the question's period is put into their arguments
PERIOD_TOOLS = {
    "phishing_campaign_summary", "repeat_phishing_failures", "phishing_test_detail", "training_completion_summary",
    "overdue_training", "account_risk_overview", "user_risk_summary", "make_chart", "export_csv",
    "training_by_module", "group_risk_trend", "new_joiners", "callback_phishing_summary",
    "reported_emails", "admin_audit_log", "security_coaching", "user_events", "training_library",
}
# product tools and the api key each needs; hidden from the model when no console has that key
PRODUCT_TOOLS = {
    "industry_benchmark": "ksat", "usb_test_results": "ksat", "physical_qr_results": "ksat", "simulation_overview": "ksat",
    "admin_audit_log": "ksat", "reported_emails": "phisher", "phisher_rules": "phisher", "security_coaching": "coach",
    "password_risks": "piq", "user_events": "events",
}
# current status, not something that happened in a period: the default year is not applied
NO_DEFAULT_PERIOD = {"overdue_training", "training_by_module", "training_library"}
# the chart attached when an answer used one of these tools and has none yet (first match wins)
CHART_FOR_TOOL = (
    ("reported_emails", "reported_emails"),
    ("training_by_module", "modules"),
    ("group_risk_trend", "groups"),
    ("risk_by_group", "groups"),
    ("top_users_by_risk", "top_users"),
    ("phishing_campaign_summary", "phishing_tests"),
    ("training_completion_summary", "training_completion"),
    ("account_risk_overview", "risk_trend"),
)
CHART_ASK = re.compile(r"\b(grafik\w*|chart\w*|graph\w*|diagram\w*|visuali[sz]\w*|plot\w*)\b", re.I)
EXPORT_ASK = re.compile(r"\b(export\w*|ekspor\w*|csv|excel|unduh\w*|download\w*)\b", re.I)
PRONOUN = re.compile(r"\b(dia|nya|beliau|him|her|his|their|them)\b|\w+nya\b", re.I)
LAST_PERSON = re.compile(r"user_risk_summary [^;\]]*\(id (\d+)\)")
# exports and charts mention "semua pengguna" too, but are not page requests
NOT_A_LIST = re.compile(r"\b(export\w*|ekspor\w*|csv|excel|unduh|download|grafik|chart|graph|diagram|visualisa\w*)\b", re.I)
# "tampilkan semua user", "list all users", "daftar pengguna"
LIST_ALL = re.compile(r"\b(semua|all|daftar|list)\b[^.?!]{0,20}\b(users?|pengguna)\b|\b(users?|pengguna)\b[^.?!]{0,10}\b(semua|all)\b", re.I)
# questions about one person's risk or history (not "hapus user ...")
PERSON_DETAIL_ASK = re.compile(r"histor|riwayat|risk|risiko|skor|score|detail|training|pelatihan|telat|terlambat|overdue|past due|phish|klik|click", re.I)
NOTE_LINE = re.compile(r"^\s*\[Data used:[^\]]*\]\s*$", re.M)
NEXT_OFFSET = re.compile(r"list_users_page [^;\]]*?next_offset=(\d+)")
# "lanjut", "next", "show 20", "berikutnya": continue the last users page
CONTINUE = re.compile(r"\b(lanjut\w*|next|more|berikut\w*|selanjutnya|show \d+|tampilkan \d+)\b", re.I)
# "21-40", "21 - 40", "21 sampai 40": that exact slice of users
RANGE = re.compile(r"\b(\d{1,4})\s*(?:-|–|sampai|to|hingga)\s*(\d{1,4})\b", re.I)


class Agent:

    def __init__(
        self,
        config: AppConfig | None = None,
        llm: Any | None = None,
        session_factory: Callable[[], Any] | None = None,
    ):
        self.config = config or load_config()
        self.llm = llm or LLMClient(self.config)
        self.mcp_url = f"http://{self.config.mcp_host}:{self.config.mcp_port}{self.config.mcp_path}"
        self._session_factory = session_factory or self._mcp_session

    @asynccontextmanager
    async def _mcp_session(self) -> AsyncIterator[ClientSession]:
        async with streamable_http_client(self.mcp_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    def _openai_tools(self, mcp_tools: list[Any]) -> list[dict[str, Any]]:
        tools = []
        for tool in mcp_tools:
            if tool.name == "knowbe4_raw_get" and not self.config.llm_expose_raw_get:
                continue
            if tool.name in HIDDEN_TOOLS - {"knowbe4_raw_get"}:
                continue
            if tool.name in RAW_LIST_TOOLS and not self.config.llm_expose_raw_lists:
                continue
            # a product tool without its key would only ever answer "not configured"
            if tool.name in PRODUCT_TOOLS and not self._products().get(PRODUCT_TOOLS[tool.name]):
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"KnowBe4 MCP tool: {tool.name}",
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            })
        return tools

    def _products(self) -> dict[str, bool]:
        """which product apis at least one console has a key for"""
        return {p: any(c.product_key(p) for c in self.config.consoles.values()) for p in ("ksat", "phisher", "piq", "coach", "events")}

    def capability_text(self, language: str) -> str:
        """the fixed "what can you do" answer, with a line for each product api that is configured"""
        lines = [msg(f"capability_{p}", language) for p, on in self._products().items() if on]
        return msg("capabilities", language, products="".join(f"{line}\n" for line in lines))

    def _check_console(self, args: dict[str, Any]) -> str | None:
        if "console" not in args:
            return None
        key = str(args["console"]).lower().strip()
        valid = [k for k, c in self.config.consoles.items() if c.has_api_key]
        if key not in self.config.consoles:
            return f"Unknown console '{args['console']}'. Valid consoles: {', '.join(valid) or '(none)'}."
        if not self.config.consoles[key].has_api_key:
            return (
                f"Console '{key}' is not configured (no API key). "
                f"Tell the user. Valid consoles: {', '.join(valid) or '(none)'}."
            )
        args["console"] = key
        return None

    @staticmethod
    def _mcp_result_text(result: Any) -> str:
        if getattr(result, "is_error", False):
            # ToolError messages (key rejected, daily limit, not found) are meant for the model
            text = " ".join(t for t in (getattr(i, "text", None) for i in getattr(result, "content", None) or []) if t)
            return _error(text or "MCP tool returned an error.")

        structured = getattr(result, "structured_content", None)
        if structured is not None:
            return json.dumps(structured, ensure_ascii=False, default=str)

        parts: list[str] = []
        for item in getattr(result, "content", None) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _truncate(self, text: str) -> str:
        limit = self.config.llm_max_tool_chars
        if len(text) <= limit:
            return text

        note = (
            "Only the first rows_shown of total_records fit. Present them as 'the first N of TOTAL' "
            "(never say 'truncated') and offer to show the next ones or narrow the question."
        )
        try:
            data = json.loads(text)
        except ValueError:
            data = None

        if isinstance(data, list):
            budget = limit - 600
            rows: list[Any] = []
            used = 0
            for row in data:
                size = len(json.dumps(row, ensure_ascii=False, default=str)) + 2
                if used + size > budget:
                    break
                rows.append(row)
                used += size
            return json.dumps(
                {"truncated": True, "total_records": len(data), "rows_shown": len(rows), "note": note, "rows": rows},
                ensure_ascii=False,
                default=str,
            )

        return json.dumps({"truncated": True, "note": note, "partial": text[: limit - 600]}, ensure_ascii=False)

    async def _run_tool(self, session: Any, call: Any, tool_names: set[str], state: dict[str, Any] | None = None) -> str:
        # per-question state: rules the small model ignores when they are only in the prompt
        state = state if state is not None else {}
        function = getattr(call, "function", None)
        name = getattr(function, "name", "") or ""
        if name not in tool_names:
            return _error(f"Unknown tool '{name}'. Use one of the listed tools.")

        try:
            args = json.loads(function.arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
        except ValueError as exc:
            print(f"[AGENT] Tool: {name} | bad arguments ({type(exc).__name__})", flush=True)
            return _error(f"Arguments for {name} are not a valid JSON object ({exc}). Send the call again with valid JSON.")

        problem = self._check_console(args)
        # argument values can be personal data, so log keys only
        print(f"[AGENT] Tool: {name} | Arg keys: {sorted(args)}", flush=True)
        if problem:
            return _error(problem)
        if state.get("ask_user") and name in PERSON_DETAIL_TOOLS:
            return _error("Several people matched. Do not fetch details yet: list them numbered and ask the user which one. Do not mention this rule to the user.")
        if name == "list_users_page":
            # the small model forgets the page number; the agent knows it from the question and the notes
            if state.get("range"):
                start, end = state["range"]
                args["offset"], args["limit"] = start - 1, min(end - start + 1, 20)
            elif state.get("continue_from") is not None:
                # the notes know the next page; the model once sent 40 instead of 20 and skipped one
                args["offset"] = state["continue_from"]
        if name == "make_chart":
            # labels follow the chat language, whatever the model passed
            args["language"] = state.get("language", DEFAULT_LANGUAGE)
        # files and charts only when this question asks for one: it once attached the previous turn's csv to a forecast answer
        if name == "export_csv" and not EXPORT_ASK.search(state.get("prompt", "")):
            return _error("This question does not ask for a file. Do not export; answer the question. Do not mention this rule to the user.")
        # a training enrolment from 2024 that is still unfinished is still overdue: no default year there
        if state.get("period") and name in PERIOD_TOOLS and not (state.get("default_period") and name in NO_DEFAULT_PERIOD):
            # the question's period wins over whatever dates the model sent (it left them out or guessed)
            args.pop("start_date", None)
            args.pop("end_date", None)
            args.update(state["period"].args())
        if name in ("make_chart", "export_csv") and "user_id" in args and not str(args["user_id"]).strip().isdigit():
            # it sent user_id "" or "organisasi" for the organisation's history, which then failed validation
            args.pop("user_id")
        if name in ONE_PER_ANSWER_TOOLS and state.get(name):
            return _error("Only one page per answer. Show the page you already have and offer the next one. Do not mention this rule to the user.")

        try:
            result = await session.call_tool(name, arguments=args)
        except Exception as exc:
            print(f"[MCP TOOL ERROR] {name}: {type(exc).__name__}", flush=True)
            return _error(f"Tool {name} failed ({type(exc).__name__}).")

        text = self._mcp_result_text(result)
        state[name] = True
        if getattr(result, "is_error", False):
            for marker, key in (("could not be reached", "kb4_unreachable"), ("daily API limit", "kb4_daily_limit"), ("API key was rejected", "kb4_key_rejected")):
                if marker in text:
                    state["kb4_failure"] = key
        if not getattr(result, "is_error", False):
            state["data_tools"] = state.get("data_tools", 0) + 1
            # local answers (console list, nist) or a comparison where every console failed hold no KnowBe4 data
            if name not in ("list_consoles", "search_nist") and '"consoles": []' not in text:
                state["kb4_data"] = True
            state.setdefault("notes", []).append(_note_for(name, args, text))
            if name == "list_users_page":
                try:
                    page = json.loads(text)
                except ValueError:
                    page = None
                if isinstance(page, dict):
                    state["users_page"] = page
            if name == "search_nist":
                try:
                    found = json.loads(text)
                except ValueError:
                    found = {}
                for r in found.get("results") or [] if isinstance(found, dict) else []:
                    pages = state.setdefault("nist_sources", {}).setdefault(r.get("source"), [])
                    if r.get("pdf_page") not in pages:
                        pages.append(r.get("pdf_page"))
            if name in ("make_chart", "export_csv"):
                try:
                    made = json.loads(text)
                except ValueError:
                    made = {}
                if isinstance(made, dict) and (made.get("image_url") or made.get("download_url")):
                    state.setdefault("attachments", []).append(made)
        if name == "user_risk_summary" and not getattr(result, "is_error", False):
            state["summary_user_id"] = args.get("user_id")
        if name == "training_by_module" and str(args.get("module") or "").strip():
            # one module asked about: a chart of the lowest modules would not be about it
            state["module_focus"] = True
        if name == "group_risk_trend" and not getattr(result, "is_error", False):
            try:
                gid = json.loads(text).get("group_id")
            except (ValueError, AttributeError):
                gid = None
            if isinstance(gid, int):
                state["trend_group_id"] = gid
        if name in ("account_risk_overview", "user_risk_summary") and not getattr(result, "is_error", False):
            try:
                summary = json.loads(text)
            except ValueError:
                summary = None
            if isinstance(summary, dict) and isinstance(summary.get("risk_trend"), dict):
                state.setdefault("risk_summaries", []).append(summary)
        if name == "find_user":
            try:
                found = json.loads(text)
                state["ask_user"] = bool(found.get("ask_user"))
                if found.get("match_count") == 1:
                    state["single_match_id"] = found["matches"][0].get("id")
                elif state["ask_user"]:
                    # "Rina Putri" in the question picks her even when the model searched only "rina":
                    # the one person with at least two name words in the question
                    asked = set(re.findall(r"\w+", state.get("prompt", "")))
                    named = [
                        m for m in found.get("matches") or []
                        if len(set(re.findall(r"\w+", str(m.get("name") or "").lower())) & asked) >= 2
                    ]
                    if len(named) == 1:
                        state["ask_user"] = False
                        state["single_match_id"] = named[0].get("id")
            except (ValueError, AttributeError, KeyError, IndexError):
                pass
        return self._truncate(text)

    async def ask(self, prompt: str, language: str = DEFAULT_LANGUAGE, history: list[dict[str, Any]] | None = None) -> str:
        return (await self.ask_with_note(prompt, language, history))["answer"]

    async def ask_with_note(
        self, prompt: str, language: str = DEFAULT_LANGUAGE, history: list[dict[str, Any]] | None = None
    ) -> dict[str, str]:
        """the answer and its [Data used: ...] note, which the caller sends back with the history (as the page does)"""
        done = {"answer": "", "note": ""}
        async for event in self._events(prompt, language, stream=False, history=history):
            if event["type"] == "done":
                done = {"answer": event["answer"], "note": event.get("note") or ""}
        return done

    async def ask_stream(
        self, prompt: str, language: str = DEFAULT_LANGUAGE, history: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """events: thinking, tool {name}, delta {text}, reset, done {answer}; LLMError propagates"""
        async for event in self._events(prompt, language, stream=True, history=history):
            yield event

    async def _round(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], stream: bool) -> AsyncIterator[tuple[str, Any]]:
        if not stream:
            yield "end", await self.llm.chat(messages, tools)
            return
        async for kind, value in self.llm.chat_stream(messages, tools):
            yield kind, value

    def _relevant_chart(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """the chart that fits the data this answer used; none for files, refusals, failures or when one exists"""
        if state.get("make_chart") or state.get("export_csv") or not state.get("kb4_data") or state.get("kb4_failure"):
            return None
        console = self._default_console()
        if not console:
            return None
        if state.get("user_risk_summary") and str(state.get("summary_user_id") or "").isdigit():
            return {"console": console, "chart": "risk_trend", "user_id": int(state["summary_user_id"])}
        if state.get("trend_group_id"):
            return {"console": console, "chart": "group_trend", "group_id": state["trend_group_id"]}
        for tool, chart in CHART_FOR_TOOL:
            if tool == "training_by_module" and state.get("module_focus"):
                continue
            if state.get(tool):
                return {"console": console, "chart": chart}
        return None

    async def _refresh(self, session: Any) -> dict[str, Any]:
        """refresh_data for every console with a key; returns whether any was refreshed and the oldest data age"""
        refreshed, ages = False, []
        for key, console in self.config.consoles.items():
            if not console.has_api_key:
                continue
            try:
                result = await session.call_tool("refresh_data", arguments={"console": key})
                data = json.loads(self._mcp_result_text(result))
            except Exception as exc:  # a failed refresh only means the answer may use the cached copy
                print(f"[AGENT] Refresh failed for a console ({type(exc).__name__})", flush=True)
                continue
            refreshed = refreshed or bool(data.get("refreshed"))
            if data.get("data_age_at_most_seconds") is not None:
                ages.append(data["data_age_at_most_seconds"])
        print(f"[AGENT] Fresh data asked: refreshed={refreshed}", flush=True)
        return {"refreshed": refreshed, "age": max(ages) if ages else None}

    def _default_console(self) -> str | None:
        return next((k for k, c in self.config.consoles.items() if c.has_api_key), None)

    def _history(self, history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        # earlier turns from the page, so "2" or "show more" make sense; capped to protect the context
        keep = max(0, self.config.llm_history_messages)
        cleaned = [
            {"role": m["role"], "content": str(m.get("content") or "")[:HISTORY_CHARS]}
            for m in (history or [])
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
        ]
        return cleaned[-keep:] if keep else []

    async def _events(
        self, prompt: str, language: str, stream: bool, history: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        prompt = prompt.strip()
        if not prompt:
            yield {"type": "done", "answer": msg("empty_question", language)}
            return
        # "brp yg klik" -> "berapa yang klik": the small model and the patterns below read plain words better
        prompt, typo_fixes = normalise_with_fixes(prompt)

        print(f"[AGENT] User question received ({len(prompt)} chars, language={language}, stream={stream})", flush=True)
        if typo_fixes:
            print("[AGENT] Typos corrected: " + ", ".join(f"{a} -> {b}" for a, b in typo_fixes), flush=True)
        if CAPABILITY_ASK.search(prompt):
            print("[AGENT] Capability question, answering with the fixed list", flush=True)
            yield {"type": "done", "answer": self.capability_text(language), "note": ""}
            return
        max_loops = self.config.llm_max_tool_loops

        async with self._session_factory() as session:
            listed = await session.list_tools()
            tools = self._openai_tools(listed.tools)
            tool_names = {t["function"]["name"] for t in tools}
            # "export semua pengguna ke csv" is an export, not a request to page through users
            list_intent = bool(LIST_ALL.search(prompt)) and not NOT_A_LIST.search(prompt)
            state: dict[str, Any] = {"prompt": prompt.lower(), "list_intent": list_intent, "language": language}
            if FRESH_ASK.search(prompt) and any(t.name == "refresh_data" for t in listed.tools):
                # asked for fresh data: drop the 10-minute copies before any tool runs (the server allows once a minute)
                state["fresh"] = await self._refresh(session)
            # "dari 2026", "3 bulan terakhir": worked out here and given to every tool that can filter by date
            if period := parse_period(prompt):
                state["period"] = period
            else:
                # no period asked: the past year, not everything since the account began (charts started in 2024)
                state["period"] = default_period()
                state["default_period"] = True
            print(f"[AGENT] Period: {state['period'].label()}{' (default)' if state.get('default_period') else ''}", flush=True)
            earlier_notes =" ".join(m["content"] for m in (history or []) if isinstance(m, dict) and m.get("role") == "assistant")
            offsets = NEXT_OFFSET.findall(earlier_notes)
            if offsets and CONTINUE.search(prompt):
                state["continue_from"] = int(offsets[-1])
            # "dia" / "her" refers to the last person summarised
            if people_seen := LAST_PERSON.findall(earlier_notes):
                state["last_person_id"] = int(people_seen[-1])
            # "2" or "yang kedua" after a list of people: that person's id, from the last find_user note
            if (pick := PICK.search(prompt)) and (people := LISTED_PEOPLE.findall(earlier_notes.split("find_user")[-1] if "find_user" in earlier_notes else "")):
                number = int(pick.group(1)) if pick.group(1) else ORDINALS[pick.group(2).lower()]
                ids = {int(n): uid for n, uid in people}
                if number in ids:
                    state["single_match_id"] = int(ids[number])
                    state["picked"] = True
            # "berapa risk score dia?" right after a search that found several people: it once picked one by itself
            if not state.get("picked") and PERSON_PRONOUN.search(prompt):
                found_at, summary_at = earlier_notes.rfind("find_user"), earlier_notes.rfind("user_risk_summary")
                listed = NAMED_PEOPLE.findall(earlier_notes[found_at:]) if found_at > summary_at else []
                if len(listed) >= 2:
                    print("[AGENT] 'dia' after several matches, asking which person", flush=True)
                    people = "\n".join(f"{n}. {name.strip()}" for n, name, _ in listed)
                    yield {"type": "done", "answer": msg("which_person", language, count=len(listed)) + "\n\n" + people, "note": ""}
                    return
            # only about users: "kenapa 41-47 disebut medium" is not a page request
            if (r := RANGE.search(prompt)) and 0 < int(r.group(1)) <= int(r.group(2)) and (offsets or USERS_WORD.search(prompt)):
                state["range"] = (int(r.group(1)), int(r.group(2)))

            # after a language switch the earlier turns pull the model back to the old language
            earlier = self._history(history)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_system_prompt(self.config, language)},
                *earlier,
                {"role": "user", "content": prompt + (f"\n\n({msg('answer_in_language', language)})" if earlier else "")},
            ]

            # numbers the answer may use without a new fetch: the question, the definitions and earlier real answers
            known_numbers = set(NUMBER.findall(" ".join(str(m.get("content") or "") for m in messages)))

            nudged = False
            rewritten = False
            exact_forced = False
            fetch_forced = False
            grounded_forced = False
            # system prompt, earlier turns and the question; everything after is this turn's work
            asked = len(messages)
            for loop in range(max_loops):
                print(f"[AGENT] {self.config.llm_model} | Loop {loop + 1}", flush=True)
                yield {"type": "thinking"}
                streamed = False
                choice = None
                async for kind, value in self._round(messages, tools, stream):
                    if kind == "content":
                        streamed = True
                        yield {"type": "delta", "text": value}
                    else:
                        choice = value
                message = choice.message
                calls = [c for c in (message.tool_calls or []) if getattr(c, "function", None)]

                if not calls:
                    answer = (message.content or "").strip()
                    # qwen sometimes finishes inside its thinking and writes no answer; ask once more
                    if not answer and not nudged and choice.finish_reason != "length":
                        nudged = True
                        print("[AGENT] Empty answer, asking for the final answer", flush=True)
                        messages.append({"role": "user", "content": msg("nudge", language)})
                        continue
                    # requests the small model tends to answer from memory: tell it exactly which call to make
                    if not exact_forced:
                        exact, call = None, None
                        console = self._default_console()
                        if (state.get("range") or state.get("continue_from") is not None or state.get("list_intent")) and not state.get("list_users_page"):
                            if state.get("range"):
                                offset = state["range"][0] - 1
                            elif state.get("continue_from") is not None:
                                offset = state["continue_from"]
                            else:
                                offset = 0
                            exact = msg("call_page", language, offset=offset)
                            call = ("list_users_page", {"console": console, "offset": offset})
                        elif CHART_ASK.search(prompt) and not state.get("make_chart"):
                            # it once said "grafik telah ditampilkan" without drawing anything
                            person = state.get("single_match_id") or state.get("last_person_id")
                            exact = msg("call_chart", language)
                            if person and PRONOUN.search(prompt):
                                exact += msg("chart_person", language, id=person)
                                call = ("make_chart", {"console": console, "chart": "risk_trend", "user_id": person})
                        elif EXPORT_ASK.search(prompt) and not state.get("export_csv"):
                            exact = msg("call_export", language)
                        elif (NIST_ASK.search(prompt) or (GUIDANCE_ASK.search(prompt) and AWARENESS_TOPIC.search(prompt))) and not state.get("search_nist"):
                            # it answered a phish scale question from general knowledge, with no source
                            exact = msg("call_nist", language)
                        elif (REPORT_ASK.search(prompt) and not state.get("phishing_test_detail") and not PHISHER_ASK.search(prompt)
                              and PHISHING_TOPIC.search(prompt + " " + earlier_notes[-1500:])):
                            # "terus yg report brp?" once got the previous answer repeated; only this tool knows who reported
                            exact = msg("call_report", language)
                            call = ("phishing_test_detail", {"console": console})
                        elif topic := next((t for t in TOPIC_TOOLS if t[1] in tool_names and t[0].search(prompt)
                                            and not _topic_answered(t, prompt, state)), None):
                            exact = msg("call_topic", language, tool=topic[1])
                            call = (topic[1], {"console": console})
                        elif (WHY_ASK.search(prompt) and not state.get("data_tools")
                              and (last := LAST_NOTE_TOOL.findall(earlier_notes)) and last[-1] in REFETCH_TOOLS):
                            # "yg 0% itu kenapa" once got a reason made up without looking at the data again
                            exact = msg("call_again", language, tool=last[-1])
                            call = (last[-1], {"console": console})
                        elif (person := state.get("single_match_id") or (state.get("last_person_id") if PRONOUN.search(prompt) else None)) \
                                and not state.get("user_risk_summary") and (state.get("picked") or PERSON_DETAIL_ASK.search(prompt)):
                            # "dia ada training yg telat?" once got a users list instead of that person
                            exact = msg("call_user_summary", language, id=person)
                            call = ("user_risk_summary", {"console": console, "user_id": person})
                        if exact:
                            exact_forced = True
                            if streamed:
                                yield {"type": "reset"}
                            if call and console and call[0] in tool_names:
                                # the model ignored exact instructions too; when the call is known, make it directly
                                print("[AGENT] The needed call is known, making it directly", flush=True)
                                call_id = f"agent_{loop}"
                                arguments = json.dumps(call[1])
                                messages.append({
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [{"id": call_id, "type": "function", "function": {"name": call[0], "arguments": arguments}}],
                                })
                                yield {"type": "tool", "name": call[0]}
                                synthetic = SimpleNamespace(id=call_id, function=SimpleNamespace(name=call[0], arguments=arguments))
                                content = await self._run_tool(session, synthetic, tool_names, state)
                                messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
                            else:
                                print("[AGENT] Answered without the needed tool, asking for the exact call", flush=True)
                                messages.append({"role": "assistant", "content": answer})
                                messages.append({"role": "user", "content": exact})
                            continue
                    # numbers that appear nowhere (question, definitions, earlier answers) and no tool this turn:
                    # invented (it once made up "user id 1-20, all 75.1"); make it fetch, once
                    unexplained = set(NUMBER.findall(answer)) - known_numbers
                    if unexplained and not state.get("data_tools"):
                        if not fetch_forced:
                            fetch_forced = True
                            print("[AGENT] Numbers without any tool call, asking the model to fetch the data", flush=True)
                            if streamed:
                                yield {"type": "reset"}
                            messages.append({"role": "assistant", "content": answer})
                            messages.append({"role": "user", "content": msg("must_use_tool", language)})
                            continue
                        print("[AGENT] Still no tool call, refusing to show unsourced numbers", flush=True)
                        if streamed:
                            yield {"type": "reset"}
                        answer = msg("no_data_answer", language)
                    # with data fetched, every number must still be one the data, question or definitions contain
                    # (rounding and id/en separators allowed); nothing calculated, estimated or made up
                    if state.get("data_tools"):
                        shown = NOTE_LINE.sub("", answer)
                        if state.get("users_page"):
                            # its headline and table rows are replaced by ones built from the data, so only the rest counts
                            rest = [ln for ln in shown.splitlines() if not ln.lstrip().startswith("|")]
                            shown = "\n".join(rest[1:] if rest and rest[0].lstrip().startswith("**") else rest)
                        # sources: the conversation as asked plus real tool results, never our own rewrite requests
                        # or the model's rejected drafts (those carry the very numbers in question)
                        sources = messages[:asked] + [m for m in messages[asked:] if m.get("role") == "tool"]
                        ungrounded = _ungrounded_numbers(shown, _grounded_values(sources))
                        if ungrounded and not grounded_forced:
                            grounded_forced = True
                            print(f"[AGENT] {len(ungrounded)} number(s) not in the data, asking for a rewrite", flush=True)
                            if streamed:
                                yield {"type": "reset"}
                            messages.append({"role": "assistant", "content": answer})
                            messages.append({"role": "user", "content": msg("ungrounded_numbers", language, numbers=", ".join(ungrounded))})
                            continue
                        if ungrounded:
                            print(f"[AGENT] {len(ungrounded)} number(s) still not in the data, dropping those sentences", flush=True)
                            if streamed:
                                yield {"type": "reset"}
                            answer = _drop_sentences_with(answer, ungrounded) or msg("no_answer", language)
                    if (CJK.search(answer) or _wrong_language(NOTE_LINE.sub("", answer), language)) and not rewritten:
                        rewritten = True
                        print("[AGENT] Answer in the wrong language or script, asking for a rewrite", flush=True)
                        if streamed:
                            yield {"type": "reset"}
                        messages.append({"role": "assistant", "content": answer})
                        messages.append({"role": "user", "content": msg("rewrite_language", language)})
                        continue
                    if (state.get("period") and not state.get("default_period") and state.get("kb4_data")
                            and not any(state.get(t) for t in PERIOD_TOOLS - {"make_chart", "export_csv"})):
                        # only today's state was used (rankings, groups): say the period could not apply
                        answer = f"{answer}\n\n*{msg('period_current_only', language, period=state['period'].label())}*"
                    no_prediction = f"**{msg('no_prediction', language)}**"
                    if FUTURE_ASK.search(prompt) and no_prediction not in answer:
                        # its own wording ("Saya tidak bisa memprediksi nilai risiko untuk bulan depan") instead of the fixed line;
                        # only a first line that already refuses is replaced, never a real answer
                        head, _, tail = answer.partition("\n")
                        if PREDICT_WORD.search(head) and NEGATION.search(head):
                            answer = f"{no_prediction}\n{tail}".strip()
                    if no_prediction in answer and not FUTURE_ASK.search(prompt):
                        # nobody asked about the future: the refusal line is noise there
                        answer = re.sub(r"\n*" + re.escape(no_prediction) + r"[ \t]*\n*", "\n\n", answer).strip()
                    if state.get("kb4_failure") and not state.get("kb4_data"):
                        # nothing could be fetched: a fixed, honest answer instead of guessed causes or promises
                        if streamed:
                            yield {"type": "reset"}
                        answer = msg(state["kb4_failure"], language)
                    if choice.finish_reason == "length":
                        answer += "\n\n" + msg("cut_off", language)
                    # the notes are for the model only
                    answer = NOTE_LINE.sub("", answer).strip()
                    # a forecast question opens with the no-prediction line, which mentions the risk score too
                    if len(state.get("risk_summaries") or []) == 1 and not state.get("users_page") and not FUTURE_ASK.search(prompt):
                        answer = _with_risk_line(answer, state["risk_summaries"][0], language, asked_period=None if state.get("default_period") else state.get("period"))
                    answer = _fix_levels(answer)
                    if language == "id":
                        answer = _fix_typos_in_answer(answer)
                    if state.get("ask_user") and "?" not in answer:
                        answer += "\n\n" + msg("which_one", language)
                    if state.get("users_page"):
                        answer = _with_users_table(answer, state["users_page"], language)
                    if state.get("nist_sources"):
                        # citations come from what search_nist returned, so they are never missing or made up
                        cited = "; ".join(
                            f"NIST {src} ({msg('pdf_pages', language, pages=', '.join(str(p) for p in sorted(pages)))})"
                            for src, pages in state["nist_sources"].items()
                        )
                        answer = f"{answer}\n\n**{msg('sources_heading', language)}:** {cited}"
                    chart = self._relevant_chart(state)
                    if chart and "make_chart" in tool_names:
                        # charts are cheap (the data is already cached), so answers that have one get it
                        yield {"type": "tool", "name": "make_chart"}
                        call_id = f"agent_chart_{loop}"
                        synthetic = SimpleNamespace(id=call_id, function=SimpleNamespace(name="make_chart", arguments=json.dumps(chart)))
                        await self._run_tool(session, synthetic, tool_names, state)
                    answer = re.sub(r"\n{3,}", "\n\n", MODEL_LINK.sub("", MODEL_IMAGE.sub("", answer))).strip()
                    if state.get("attachments"):
                        answer = _with_attachments(answer, state["attachments"], language)
                    if (fresh := state.get("fresh")) and state.get("kb4_data") and answer.strip():
                        note = msg("fresh_data", language) if fresh["refreshed"] or fresh["age"] is None else msg("fresh_recent", language, seconds=fresh["age"])
                        answer = f"{answer.strip()}\n\n*{note}*"
                    answer = answer.strip() or msg("no_answer", language)
                    print("[AGENT] Final answer generated", flush=True)
                    notes = state.get("notes") or []
                    yield {"type": "done", "answer": answer, "note": f"[Data used: {'; '.join(notes)}]" if notes else ""}
                    return

                # text that arrived in a round that turned into tool calls is not the answer
                if streamed:
                    yield {"type": "reset"}

                # history keeps the final output only, not the thinking text (qwen guidance)
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"},
                        }
                        for c in calls
                    ],
                })
                for call in calls:
                    yield {"type": "tool", "name": call.function.name}
                    content = await self._run_tool(session, call, tool_names, state)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                if state.get("kb4_failure") and not state.get("kb4_data"):
                    # the client already retried; asking again only ran into the loop limit
                    print("[AGENT] KnowBe4 failed and nothing was fetched, answering with the fixed message", flush=True)
                    yield {"type": "done", "answer": msg(state["kb4_failure"], language), "note": ""}
                    return

        yield {"type": "done", "answer": msg("loop_limit", language, loops=max_loops)}
