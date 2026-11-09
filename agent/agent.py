from __future__ import annotations

import bisect
import json
import re
from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent.llm import LLMClient
from agent.messages import DEFAULT_LANGUAGE, LANGUAGE_NAMES, msg
from agent.normalise import normalise
from agent.period import parse_period
from config.settings import AppConfig, load_config

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
   phishing_test_detail (one test: who clicked, who reported, report rate), overdue_training (Past Due training),
   make_chart (charts), export_csv (files), search_nist (NIST guidance).
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
18. NIST: for best practice, frameworks, "menurut NIST", how to run an awareness or training programme, or how
    hard a phishing email is to spot, call search_nist with English keywords. Answer only from the passages it
    returns and cite them like (NIST SP 800-50r1, PDF page 69). When the question is also about our own data,
    combine it with the KnowBe4 tools.
19. Questions that are not about KnowBe4, security awareness or phishing (news, politics, general knowledge):
    say in one sentence that you only answer questions about this KnowBe4 data and security awareness. No numbers.
20. Periods ("dari 2026", "tahun lalu", "3 bulan terakhir"): the tools get the period automatically and their results
    say which period they cover. Say that period in your first line. Never mix in data from outside it.

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
HIDDEN_TOOLS = {"knowbe4_raw_get", "knowbe4_health_check"}
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
        people = ", ".join(f"{i + 1}. {m.get('name')} (id {m.get('id')})" for i, m in enumerate(data.get("matches") or []))
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
# who reported a phishing email ("yg report brp", "berapa yang melaporkan", "report rate")
# questions about the future, where the "cannot predict" line belongs
FUTURE_ASK = re.compile(
    r"\b(depan|nanti|besok|akan datang|ke depannya|prediksi\w*|perkiraan|proyeksi|forecast\w*|predict\w*|future|next (?:week|month|quarter|year)|will)\b",
    re.I,
)
# not "laporan" (a report document) or "reporting"
REPORT_ASK = re.compile(r"\b(report(?:ed|s|nya)?|report rate|(?:me)?lapor(?:kan|kannya|nya)?|dilaporkan)\b", re.I)
PHISHING_TOPIC = re.compile(r"phish|phising|email palsu|simulasi", re.I)
NIST_ASK = re.compile(r"\b(nist|phish\s*scale|csf|800-50|framework|kerangka|best practice|praktik terbaik|menurut standar)\b", re.I)
# tools that take start_date / end_date; the question's period is put into their arguments
PERIOD_TOOLS = {
    "phishing_campaign_summary", "repeat_phishing_failures", "phishing_test_detail", "training_completion_summary",
    "overdue_training", "account_risk_overview", "user_risk_summary", "make_chart", "export_csv",
}
# the chart attached when an answer used one of these tools and has none yet (first match wins)
CHART_FOR_TOOL = (
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
PERSON_DETAIL_ASK = re.compile(r"histor|riwayat|risk|risiko|skor|score|detail", re.I)
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
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"KnowBe4 MCP tool: {tool.name}",
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            })
        return tools

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
            elif state.get("continue_from") is not None and not args.get("offset"):
                args["offset"] = state["continue_from"]
        if name == "make_chart":
            # labels follow the chat language, whatever the model passed
            args["language"] = state.get("language", DEFAULT_LANGUAGE)
        # files and charts only when this question asks for one: it once attached the previous turn's csv to a forecast answer
        if name == "export_csv" and not EXPORT_ASK.search(state.get("prompt", "")):
            return _error("This question does not ask for a file. Do not export; answer the question. Do not mention this rule to the user.")
        if state.get("period") and name in PERIOD_TOOLS:
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
        answer = ""
        async for event in self._events(prompt, language, stream=False, history=history):
            if event["type"] == "done":
                answer = event["answer"]
        return answer

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
        for tool, chart in CHART_FOR_TOOL:
            if state.get(tool):
                return {"console": console, "chart": chart}
        return None

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
        prompt = normalise(prompt)

        print(f"[AGENT] User question received ({len(prompt)} chars, language={language}, stream={stream})", flush=True)
        max_loops = self.config.llm_max_tool_loops

        async with self._session_factory() as session:
            listed = await session.list_tools()
            tools = self._openai_tools(listed.tools)
            tool_names = {t["function"]["name"] for t in tools}
            # "export semua pengguna ke csv" is an export, not a request to page through users
            list_intent = bool(LIST_ALL.search(prompt)) and not NOT_A_LIST.search(prompt)
            state: dict[str, Any] = {"prompt": prompt.lower(), "list_intent": list_intent, "language": language}
            # "dari 2026", "3 bulan terakhir": worked out here and given to every tool that can filter by date
            if period := parse_period(prompt):
                state["period"] = period
                print(f"[AGENT] Period: {period.label()}", flush=True)
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
                        elif NIST_ASK.search(prompt) and not state.get("search_nist"):
                            # it answered a phish scale question from general knowledge, with no source
                            exact = msg("call_nist", language)
                        elif (REPORT_ASK.search(prompt) and not state.get("phishing_test_detail")
                              and PHISHING_TOPIC.search(prompt + " " + earlier_notes[-1500:])):
                            # "terus yg report brp?" once got the previous answer repeated; only this tool knows who reported
                            exact = msg("call_report", language)
                            call = ("phishing_test_detail", {"console": console})
                        elif state.get("single_match_id") and not state.get("user_risk_summary") and (state.get("picked") or PERSON_DETAIL_ASK.search(prompt)):
                            exact = msg("call_user_summary", language, id=state["single_match_id"])
                            call = ("user_risk_summary", {"console": console, "user_id": state["single_match_id"]})
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
                    if (state.get("period") and state.get("kb4_data")
                            and not any(state.get(t) for t in PERIOD_TOOLS - {"make_chart", "export_csv"})):
                        # only today's state was used (rankings, groups): say the period could not apply
                        answer = f"{answer}\n\n*{msg('period_current_only', language, period=state['period'].label())}*"
                    no_prediction = f"**{msg('no_prediction', language)}**"
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
                    if state.get("attachments"):
                        answer = _with_attachments(answer, state["attachments"], language)
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

        yield {"type": "done", "answer": msg("loop_limit", language, loops=max_loops)}
