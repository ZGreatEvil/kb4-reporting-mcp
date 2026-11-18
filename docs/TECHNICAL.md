# Technical documentation

This document is for developers and IT staff who maintain the chatbot or review it. To install it, see [INSTALL_SERVER.md](INSTALL_SERVER.md) for a Linux server with Docker, or the [README](../README.md) for a Windows PC. For staff who use the chat, see [USER_GUIDE.md](USER_GUIDE.md) or [USER_GUIDE.id.md](USER_GUIDE.id.md).

## Contents

1. [What it is](#1-what-it-is)
2. [Architecture](#2-architecture)
3. [Repository layout](#3-repository-layout)
4. [How a question is answered](#4-how-a-question-is-answered)
5. [Tools](#5-tools)
6. [Configuration](#6-configuration)
7. [KnowBe4 APIs, limits and caching](#7-knowbe4-apis-limits-and-caching)
8. [Security model](#8-security-model)
9. [Data handling](#9-data-handling)
10. [Languages](#10-languages)
11. [Testing](#11-testing)
12. [Known limitations](#12-known-limitations)
13. [Maintenance tasks](#13-maintenance-tasks)

## 1. What it is

A chat page where security staff ask questions about their KnowBe4 data in Indonesian or English. Examples:

- "what is our risk score and why"
- "who failed the last phishing test"
- "training per group for the October campaign, as Excel"

The parts:

- **The model:** a small AI model (`qwen3.5:4b`, run by Ollama on the same machine) chooses which data to fetch and writes the answer.
- **The data:** comes from a read-only **MCP server** that wraps the KnowBe4 APIs.
- **Code checks:** check and correct the answer before it is shown. Sections 4 and 12 explain why so much is checked in code.

It is read-only: it never changes anything in KnowBe4.

## 2. Architecture

```
browser ──HTTP──> web chat (web/, FastAPI)
                    │  the page: index.html + app.js, strict CSP, no inline script
                    │  POST /api/chat/stream (NDJSON progress + final answer), POST /api/chat
                    ▼
                  agent (agent/)  ──OpenAI-compatible API──>  Ollama: kb4-analyst (qwen3.5:4b, 32k context)
                    │  tool loop, guards, answer checks
                    ▼  MCP, streamable HTTP, 127.0.0.1 only
                  MCP server (kb4_mcp/)  87 read-only tools
                    │
                    ▼
                  KnowBe4 client (knowbe4/)  cache, rate limit, 24 h request counter, retries
                    │  HTTPS
                    ▼
                  KnowBe4 Reporting API (REST) · product APIs (GraphQL) · User Event API
```

**The MCP server:**
- It is a standard [Model Context Protocol](https://modelcontextprotocol.io) server, so other MCP clients can use the same tools.
- It has no authentication, so it listens only on `127.0.0.1`. The MCP library's host-header check is active on that address.

**In Docker:** the web chat and the MCP server run in one container, started by `docker/start.py`. They share the folders for charts and exports. Ollama is a second container. See `docker-compose.yml`.

## 3. Repository layout

| Path | Contents |
|---|---|
| `agent/agent.py` | the tool loop and every answer check (section 4) |
| `agent/llm.py` | client for any OpenAI-compatible server (Ollama by default) |
| `agent/messages.py` | every fixed message the server sends, in `id` and `en` |
| `agent/period.py` | turns "3 bulan terakhir", "Q3 2026", "since March" into dates |
| `agent/normalise.py` | casual wording and typo correction before routing |
| `kb4_mcp/server_impl.py` | MCP tool registration |
| `kb4_mcp/summaries.py`, `breakdowns.py`, `reports.py`, `lookups.py` | summary tools: pure functions over the KnowBe4 client that do all the arithmetic |
| `kb4_mcp/products.py` | tools for the GraphQL product APIs (fixed, read-only queries) |
| `kb4_mcp/outputs.py` | charts (matplotlib PNG) and CSV / Excel exports |
| `kb4_mcp/knowledge.py` | the NIST guidance search (BM25 over three NIST PDFs) |
| `knowbe4/client.py` | HTTP client: pagination, cache, rate limit, request counter, retries |
| `config/settings.py` | settings from the environment / `.env`, validated at start-up |
| `config/consoles.example.yaml` | template for `config/consoles.yaml` (not committed) |
| `web/main.py`, `web/static/` | the web app and the page |
| `ollama/Modelfile` | builds `kb4-analyst` from `qwen3.5:4b` with the context and sampling settings |
| `Dockerfile`, `docker-compose.yml`, `docker/start.py` | the container set-up |
| `tests/` | unit tests (no network, no model) |

## 4. How a question is answered

`Agent._events()` in `agent/agent.py` is the only loop. `/api/chat/stream` and `/api/chat` both use it.

1. **Clean the question.**
   - Script and style tags are stripped.
   - Casual wording and typos are normalised (`normalise.py`).
   - The period is parsed (`period.py`). With no period named, the past 12 months are used.
2. **Answer without the model where possible.** A fixed answer comes straight from code for:
   - "what can you do";
   - requests to change data;
   - an unknown console, or a console without a key;
   - "continue" with nothing to continue;
   - "which one?" when a name matched several people.
3. **Run the tool loop with the model.**
   - **What the model sees:** the system prompt carries today's date, the consoles and the answer format. The model sees the summary tools; raw list tools are hidden unless a setting allows them.
   - **What code changes:** code overrides arguments it knows better than the model, such as the period, the console, the campaign date or archived users. It refuses a tool that does not fit the question and says why, and it makes the obvious call itself when the model skips it (topic routing).
   - **Limits:** results are cut at `LLM_MAX_TOOL_CHARS`, and the loop stops after `LLM_MAX_TOOL_LOOPS` rounds.
4. **Check the answer.** The small model makes mistakes that prompts alone did not stop, so code checks every answer:
   - **Numbers:** a number that does not appear in the fetched data is removed, and the model gets one chance to correct it. Changes ("rose", "fell") and month claims are checked against their numbers.
   - **Tables and headlines:** user tables, group tables, breakdowns, charts as text, and the risk and trend headlines are rebuilt from the data in code.
   - **Content the data does not support:** sentences with reasons, opinions, advice or guesses about the future are dropped. So are references to tool names or internal notes.
   - **Language:** an answer in the wrong language, or with a first line in the other language, is rewritten once.
   - **Links and files:** links the model wrote itself are removed. Chart images, file links and NIST source lines are added by code.
5. **Store the conversation.** Each answer is stored with a short `[Data used: …]` note, so a follow-up such as "2", "lanjut" or "dia" can repeat the exact call. The page sends the last `LLM_HISTORY_MESSAGES` messages with each question.

Each of these checks has unit tests in `tests/test_agent.py`. Most began as a mistake seen in a live answer, and the comment beside the code says which.

## 5. Tools

The MCP server has 87 tools.

**Summary tools (the model is told to prefer these):**
- **Organisation and risk:** `organisation_summary`, `executive_report`, `account_risk_overview`, `compare_consoles_risk`, `top_users_by_risk`, `user_risk_summary`, `risk_by_group`, `group_risk_trend`, `group_report`.
- **Phishing:** `phishing_campaign_summary`, `phishing_test_detail`, `phishing_by_group`, `phishing_by_attribute`, `phishing_trend`, `phishing_by_template`, `reporting_behaviour`, `phishing_click_details`, `repeat_phishing_failures`, `callback_phishing_summary`, `industry_benchmark`.
- **Training:** `training_completion_summary`, `training_by_group`, `training_by_attribute`, `training_by_module`, `training_library`, `overdue_training`, `campaign_people`, `person_training`, `coverage_gaps`, `policy_acknowledgement`.
- **People and lookups:** `find_user`, `list_users_page`, `group_members`, `find_group`, `find_campaign`, `list_dimension_values`, `manager_report`, `sign_in_activity`, `new_joiners`, `subscription_status`, `explain_metric`, `compare_periods`.
- **Product APIs (need their own keys):** `reported_emails`, `phisher_rules`, `usb_test_results`, `physical_qr_results`, `simulation_overview`, `admin_audit_log`, `security_coaching`, `password_risks`, `user_events`, `modstore_content`, `templates`, `account_settings`, `campaign_settings`, `product_status`.

**Outputs and guidance:**
- `make_chart` and `export_csv` (CSV or Excel);
- `search_nist` (NIST SP 800-50r1, CSF 2.0, NIST Phish Scale).

**Raw and admin tools:** these are hidden from the chat model by default but available to other MCP clients.
- `get_*` and `list_*` for every Reporting API resource;
- `knowbe4_raw_get`, which only allows `GET /v1/*` paths;
- `knowbe4_health_check`, `list_consoles` and `refresh_data`.

**How the summary tools work:**
- **Arithmetic is in code.** They do the counting, sorting and comparing themselves, so the model never has to calculate.
- **They write the headline.** Each returns a short `headline` built in code, plus only the rows the answer needs.
- **Definitions follow KnowBe4.** For example, phish-prone % = failure events ÷ delivered emails.

## 6. Configuration

Settings are read from the environment, then from `.env` (`config/settings.py`). They are validated at start-up. A bad value stops the app with a message naming the variable or the `consoles.yaml` entry. Every setting, with its meaning, is listed in `.env.example` and the README's settings table.

The ones that matter most:

| Setting | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL`, `LLM_MODEL` | Ollama on localhost, `kb4-analyst` | the model |
| `LLM_TIMEOUT_SECONDS` | 180 | per model call |
| `LLM_MAX_TOOL_CHARS` | 12000 | largest tool result shown to the model |
| `LLM_HISTORY_MESSAGES` | 6 | earlier messages sent with a question |
| `WEB_HOST`, `WEB_PORT`, `WEB_ALLOWED_HOSTS` | 127.0.0.1, 8080, empty | where the page listens and which host names it answers to |
| `KB4_CACHE_SECONDS` | 600 | how long KnowBe4 answers are reused |
| `KB4_RATE_LIMIT_RPS` | 0.8 | requests per second to KnowBe4 |
| `KB4_DAILY_LIMIT` | empty (KnowBe4's limit) | requests per console per rolling 24 h |
| `ENABLE_RAW_GET`, `LLM_EXPOSE_RAW_GET`, `LLM_EXPOSE_RAW_LISTS` | true, false, false | raw tools for MCP clients and for the model |

**Consoles** are configured in `config/consoles.yaml`:
- **Fields:** `display_name`, `region` (us, eu, ca, uk, de), `api_key_env` and optional product key variables.
- **Validation:** unknown keys are rejected.
- **Default console:** the first console with a key. A question about another console must name it.

**In Docker,** `docker-compose.yml` sets the container-only values (`LLM_BASE_URL`, `MCP_HOST`, `WEB_HOST`, `KB4_CONSOLES_FILE`, `KB4_USAGE_FILE`). These win over `.env`.

## 7. KnowBe4 APIs, limits and caching

| API | Key | Used for |
|---|---|---|
| Reporting API (REST, `/v1/*`) | Reporting API key | users, groups, risk scores, phishing, training, store purchases, policies |
| KSAT, PhishER, PasswordIQ, Real-Time Coaching (GraphQL) | product API keys | benchmarks, other simulation types, audit log, reported emails, passwords, coaching, templates, settings |
| User Event API | its own key | events pushed by other security tools |

**Limits:**
- KnowBe4's [Fair Usage Policy](https://support.knowbe4.com/hc/en-us/articles/45870261990035-KnowBe4-Fair-Usage-Policy-Overview) allows **2,000 Reporting API requests plus one per licensed user per 24 hours**, 4 per second, and a burst of 50 per minute. Going over the burst limit locks the key out for 5 minutes.
- The User Event API has its own limit.

**How the client stays within them:**
- **Rate limit:** at most `KB4_RATE_LIMIT_RPS` requests a second, below the burst limit.
- **Cache:** successful answers are cached for `KB4_CACHE_SECONDS`. Callers get copies, so they cannot change the cache. "Ambil data terbaru" / "fetch fresh data" clears a console's cache, at most once a minute.
- **Counter:** every real request is counted in a rolling-24-hour file (`KB4_USAGE_FILE`). Before the limit is reached, the client refuses, and the chat shows a fixed message.
- **The product APIs** are counted separately.
- **Retries:** network errors, 429 and 502–504 responses are retried (`KB4_MAX_RETRIES`).
- **Pagination:** the Reporting API returns `nextCursor` pages, which the client follows until `null`. Risk-history endpoints return plain lists.

## 8. Security model

| Concern | Control |
|---|---|
| Changing KnowBe4 data | Only GET requests and GraphQL queries. Mutations and subscriptions are refused in code before sending. `knowbe4_raw_get` only allows `/v1/*`. Requests to change data get a fixed "read-only" answer. |
| Secrets | Keys come only from the environment / `.env`. They are never logged; logs record argument names, not values. `.env`, `consoles.yaml` and the request counter are git-ignored and docker-ignored. |
| Web page | Strict Content Security Policy with no inline script. Libraries are vendored and hash-checked. Model HTML is sanitised (DOMPurify) and parsed in an inert `<template>`. Model-written images and links are stripped. |
| Host header | `TrustedHostMiddleware` allows only `127.0.0.1`, `localhost`, `WEB_HOST` and `WEB_ALLOWED_HOSTS`. |
| MCP server | Listens on `127.0.0.1` only, with the MCP library's host check. It has no authentication of its own, so it must never be published. |
| Files | Charts and exports have random 128-bit names and are deleted after one hour. CSV/Excel cells that start with `=`, `+`, `-`, `@`, a tab or a carriage return get a leading `'` so spreadsheets do not run them as formulas (CSV injection). |
| Container | Runs as a non-root user with a read-only filesystem, all capabilities dropped and `no-new-privileges`. Only the web port is published. |
| Who can ask | **No login** (an owner's decision). Access must be restricted at the network: a reverse proxy with HTTPS and a login, or a closed network. See INSTALL_SERVER.md section 7. |

## 9. Data handling

- **Personal data:** answers can contain names, email addresses, job titles, managers and risk scores of employees, straight from KnowBe4. Treat the chat like the KnowBe4 console itself.
- **What is kept:**
  - The server does not store conversations; the page keeps them only in the open browser tab and saves nothing but the language choice.
  - Charts and exports are deleted after an hour.
  - The KnowBe4 cache lives in memory only.
  - The only file kept is the request counter, which holds timestamps and nothing else.
- **What leaves the server:** only the read-only requests to KnowBe4. No other external service is called, and the AI model runs locally. The NIST PDFs are downloaded once, when the index is built.

## 10. Languages

- **Page text:** Indonesian (`id`, the default) and English (`en`), in the `STRINGS` table in `web/static/app.js`.
- **Server messages:** in `agent/messages.py` (`msg(key, language)`).
- **Model answers:** the model answers in the language picked on the page, and code checks it (section 4).
- **New text:** any new user-facing text needs both languages.

## 11. Testing

- **Unit tests:** `python -m pytest -W error` (about 1,100 tests).
  - They need no network and no model: they use a fake model, a fake MCP session and mocked HTTP.
  - `tests/conftest.py` points the tests at the example consoles file and a temporary request counter, so they run on a fresh copy.
- **Lint:** `ruff check .`.
- **Live checks:** these run the real model against a test KnowBe4 console, and they are run before each release. They are kept outside the repository because they contain the test console's real names.
  - **Chat checks:** chat answers with numbers checked against the raw API, casual and misspelt wording, periods, every tool group, unhappy paths, and replayed conversations.
  - **Page checks:** the page on 14 device sizes in light and dark mode in three browsers, with accessibility checks.
- **Inside Docker:** `sudo docker compose exec app python test_knowbe4.py` checks each console's key.

## 12. Known limitations

- **The model is small.** It runs on a 6 GB GPU, which keeps the data local. The price is that it sometimes:
  - picks the wrong tool;
  - words an explanation loosely;
  - mixes a few English words into Indonesian.

  The code checks in section 4 remove the known failure types, but no check can make a language model fully predictable. Important numbers should be confirmed in the KnowBe4 console.
- **Answer time:** answers take about 10–60 seconds on a GPU, and much longer on CPU.
- **Checks prove values, not context:** the number check proves that a number exists in the data, not that it belongs to the right period or group. The period, group and trend checks cover the common cases.
- **One question at a time:** questions are answered one after another per page (up to 10 queued).
- **KnowBe4 data gaps:** some KnowBe4 fields are empty in some accounts, such as department, manager or policies. Tools that depend on them say so and fall back to KnowBe4 groups where that makes sense.

## 13. Maintenance tasks

| Task | How |
|---|---|
| Add or change a tool | Write the logic as a pure function in `kb4_mcp/`, register it in `server_impl.py`, add the tests, and add any user-facing text in both languages. Keep the "what can you do" text (`capabilities` in `messages.py`) in step. |
| Change the page's styles | Tailwind 3.4.19 builds `web/static/app.css` from `tailwind.input.css`; see the README's "Changing the styles". |
| Change the model or its settings | Edit `ollama/Modelfile`, then recreate the model (INSTALL_SERVER.md section 9). Re-run the live checks: model changes affect every answer. |
| Rebuild the NIST index | `python -m kb4_mcp.knowledge`; in Docker it is built into the image. |
| Replace a KnowBe4 key | Edit `.env`, then `docker compose up -d` (or restart both servers on Windows). |
