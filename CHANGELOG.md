# Changelog

All notable changes to this project are listed here. Dates are in YYYY-MM-DD format.

## [Unreleased]

### Added
- Periods: "dari 2026", "tahun lalu", "3 bulan terakhir", "Q3 2026", "since January", "antara Maret dan Juni 2026" and similar are worked out in code (`agent/period.py`) and given to every tool that can filter by date, including charts and CSV exports; answers state the period. Before, only training questions kept their dates (2 of 16 period questions in the test set); a question about 2026 came back with data from 2024.
- Casual wording: chat spellings and common misspellings are spelled out before the model reads the question (`agent/normalise.py`). In a live test of 53 casual and dated questions, the right data was used for 52 (the 53rd, which used an admin health check, is fixed: that tool is no longer offered to the chat model) and the right period reached the tools for 17 of 17 (before: 2 of 16). Restating follow-ups with an extra model call was tried and dropped: slower, and 3 more wrong.
- The model is told today's date (it called 2026 "the future").
- Four new kinds of question, each worked out in code: which group or department is riskiest (`risk_by_group`), who failed two or more recent phishing tests (`repeat_phishing_failures`), one phishing test person by person with the report rate (`phishing_test_detail`), and Past Due training per person and module (`overdue_training`). A `groups` chart shows the riskiest groups.
- No invented numbers: every number in an answer must appear in this turn's tool results, the question or the definitions. Otherwise the model rewrites once, and any sentence still carrying such a number is removed. In a live probe of 10 questions built to tempt invention, no invented number reached the user.
- Charts are attached automatically when an answer used data that has one (risk trend, groups, top users, phishing tests, training completion); CSV files are made only when the question asks for one (a forecast answer once came with the previous turn's CSV).
- Summary tools return a `headline`, one sentence built from the data that the answer starts from, so names, numbers and periods (30 vs 90 days) are no longer garbled.
- When KnowBe4 cannot be reached, the daily limit is reached or the key is rejected, the answer is a fixed, honest message instead of guessed causes or promises to retry.
- Questions that are not about KnowBe4 or security awareness get a one-line reply saying so.
- Chat page: a **Baru / New** button for a fresh conversation, a status badge that shows whether the bot can answer (checked every 30 seconds), dark mode following the system setting, a favicon, a character counter near the 4,000-character limit, and error messages in the chosen language.
- `ollama/Modelfile` and the `kb4-analyst` model: `qwen3.5:4b` with the 32k context and sampling built in, so the context no longer falls back to Ollama's 4,096 when `OLLAMA_CONTEXT_LENGTH` is not picked up. `/health` warns when the loaded model has too little context, and also checks the MCP server and that a console has a key.
- Settings are checked at start-up with readable errors that name the setting (`WEB_PORT='eighty' in .env must be a whole number.`), including ranges (ports, rate at most KnowBe4's 4 per second) and mistakes in `consoles.yaml`.
- `WEB_ALLOWED_HOSTS` and `KB4_CONSOLES_FILE` settings.
- Tests for the web layer (validation, headers, downloads, health), settings, the new tools and failure paths, periods and wording: 410 in total, run with warnings as errors, plus a `ruff` lint baseline in `pyproject.toml`.
- Charts: `make_chart` draws a risk score trend (line, with level borders), users per risk level (pie), top users, recent phishing tests and training completion (bar) with matplotlib, and the chart appears in the answer.
- CSV export: `export_csv` writes users, phishing tests, training campaigns or a risk history to a CSV that opens in Excel with names intact, with a download link in the answer. Files are deleted after one hour and cells that Excel would run as formulas are neutralised.
- NIST guidance: `search_nist` searches NIST SP 800-50 Rev. 1, CSF 2.0 and TN 2276 (Phish Scale) locally, and answers cite the publication and PDF pages. Build the library once with `python -m kb4_mcp.knowledge`.
- `docs/DEMO.md`: a demo script that shows every capability in order.
- An answer that comes back in the wrong language (for example English after the user switched back to Indonesian) is rewritten once.
- Message queue: questions sent while an answer is still coming are shown as queued and sent automatically, in order (up to 5). Every answer shows how long it took ("Dijawab dalam 12 dtk" / "Replied in 12 s").
- Safeguards against invented data: an answer with numbers that appear nowhere (question, definitions, earlier answers) and no tool call this turn is sent back to fetch first, and never shown unsourced. Users tables and their "21-40 of 55" headings are built from the data in code. Paging ("lanjut", "show 20", "21-40"), picking a person ("2", "yang kedua") and "show all users" are resolved by the agent from hidden notes kept with each answer.
- Conversation memory: the page sends the last few messages with each question, so replies such as "2" or "show 20 more" are understood. Nothing is stored on the server.
- Answers that explain: a bold one-line answer first, key facts and a "Kenapa / Why" part built only from the data. Future predictions are refused clearly in bold.
- New summary tools `account_risk_overview`, `user_risk_summary` and `list_users_page`, with KnowBe4 risk levels, trends measured from today, and the phish-prone comparison with KnowBe4's 2026 benchmark computed in code. Raw lists and full histories are hidden from the model.
- Safeguards the model cannot skip: details are not fetched until the user picks one of several matching people, one page of users per answer, and an answer that slips into Chinese is rewritten once.
- Short-term memory for KnowBe4 answers (`KB4_CACHE_SECONDS`, default 10 minutes): repeat and follow-up questions reuse data instead of fetching it again. Errors are never cached.
- Daily request counter per console (rolling 24 hours, saved in `.kb4_usage.json`), following KnowBe4's documented limit of 2,000 requests a day plus licensed users (`KB4_DAILY_LIMIT` overrides it). It warns at 80 % and refuses with a clear message at the limit; `list_consoles` shows the count.
- KnowBe4 failures (key rejected, not found, rate or daily limit, network) now reach the model as readable messages instead of "Error executing tool".
- Language choice: the chat page asks for Bahasa Indonesia or English on the first visit, remembers it, and has an ID | EN switch in the header. The model answers in the chosen language, and every server message exists in both (`agent/messages.py`). `POST /api/chat` accepts `"language": "id" | "en"`.
- Streaming answers: `POST /api/chat/stream` sends newline-delimited JSON events (thinking, tool, delta, reset, done, error). The page shows the answer as it is written and what the agent is doing meanwhile ("Thinking…", "Fetching data: …").

### Changed
- Sampling set to Qwen's "precise" thinking-mode values (temperature 0.6, presence penalty 0) to stop Chinese slipping into answers.
- Long answers no longer freeze the page: rendering is throttled to about 10 times a second.
- Tailwind CSS is pre-built into `web/static/app.css` (Tailwind 3.4.19 standalone CLI) instead of being compiled in the browser from the unpinned development CDN. The page looks the same; the build steps are in the README.
- The page now times out after 180 seconds with no new event, instead of 180 seconds in total.
- `KB4_MAX_RETRIES` is now used: it sets the number of retries after the first try (it was ignored and retries were fixed at 4 attempts).
- The model is told to report what the tools return without adding scales, ratings or interpretations unless asked.
- Chat page redesigned for every screen from a 320 px phone to an ultrawide monitor: every button and the question box are 44 px high with the same radius and type, the header is one row from 640 px and a tidy two rows on phones, phones use the full screen height (also with browser bars), wide tables scroll inside their bubble, and colours meet contrast guidelines. Checked on Edge, Firefox and WebKit (Safari) on 14 device profiles in light and dark mode.
- The page script lives in `web/static/app.js`; marked, DOMPurify and Lucide are served from `web/static/vendor/` instead of a CDN, so the page works offline.
- The "users" CSV export lists active users by default (like every other answer), so its row count matches the chat; `status=all` includes archived users.
- Requires Python 3.11 or later (`matplotlib` 3.11 already did; `pyproject.toml` said 3.10).
- Clearer messages when the data service or the model is unavailable, and the right command when the model is missing (`ollama create`, not `ollama pull`).
- README: resumable `curl` download for the Ollama installer, and a note to restart Ollama after installing or updating it.
- The "Pertanyaan berikutnya / Next question" suggestion at the end of answers is gone.

### Fixed
- Questions without a period no longer pull data from the beginning of the account: over-time data (risk trends, phishing tests, training campaigns, charts, exports) covers the past 12 months unless the question says otherwise.
- Answers no longer vanish and reappear: the page shows progress until the answer is final, then the whole answer with its chart at once. Queued questions were checked live and are sent exactly once.
- Guidance questions ("bagaimana cara mengukur efektivitas training?") use the NIST library without having to mention NIST.
- "lanjut" always continues from the right page (the model once skipped users 21-40); a follow-up about "dia" asking about training, phishing or risk fetches that same person; when KnowBe4 cannot be reached the answer comes at once instead of after eight retries.
- Images the model writes itself (a broken "Detail tes phishing" image) are removed from every answer; only charts made in code are shown.
- Phishing-test and training charts use horizontal bars, so long names no longer overlap; chart titles no longer get cut off and show the period on their own line in the chat's language.
- Chart and CSV links now really expire after an hour: before, files were only removed when a newer one was made, so on a quiet server they stayed downloadable. Old files are also cleared when the web app starts.
- Date arguments are checked (YYYY-MM-DD, start before end): a loose date such as "Jan 2026" filtered silently wrong.
- An answer claimed "all 55 users are Low" while three were Medium; the organisation headline now states the users per level.
- The "cannot predict the future" line no longer appears in answers to questions that are not about the future.
- "Who reported it" follow-ups always fetch the test detail (one was answered by repeating the previous answer).
- The chat model no longer sees the admin `knowbe4_health_check`, which gave a bare score without level, trend or why.
- An Indonesian question asked after an English answer was sometimes answered in English.
- Asking for a named person's full history could end with only the name search when the model's first answer had been sent back for data.
- The chat no longer jumps away from what you are reading, and keeps following a new answer when you were at the bottom (it checked after the long answer had already moved the bottom).
- The tests ran only on a machine with a local `config/consoles.yaml`; they now run on a fresh clone.
- Two processes counting KnowBe4 requests at once could lose counts, and a crash mid-write could reset the counter.
- A failed NIST download left a broken PDF that blocked every later build; damaged files and a damaged index now give a clear message.
- A chart figure was left open when a fetch failed half-way, and charts with no data were drawn empty.
- `test_knowbe4.py` stopped at the first rejected key; `test_mcp_call.py` and the start scripts printed tracebacks instead of a plain message.
- Server logs could fail on a Windows console that cannot print every character.

### Security
- `knowbe4_raw_get` refused paths outside `/v1/` only by prefix, so `/v1/../v2/...` got through; dot segments, encoded dots, backslashes and empty segments are now refused.
- The web chat answers only to its own host names, so a DNS-rebinding page cannot read KnowBe4 data through the browser.
- Strict Content-Security-Policy and other security headers on every response, no third-party scripts, model output parsed in an inert template after sanitising, request size limits, CSV downloads marked `no-store`.
- `/health/routes` (a debug listing) is gone, and `/health/mcp` no longer returns exception text.

### Removed
- `MCP_BEARER_TOKEN`: it was documented but never enforced. The README now says plainly that the server has no authentication and must stay on localhost unless something authenticated is put in front of it.

## [1.1.0] - 2026-11-05

### Changed
- The chat agent now runs on a free open-weight model on the local machine instead of Google Gemini. It talks to any OpenAI-compatible server through the `openai` package, defaulting to `qwen3.5:4b` on Ollama, so KnowBe4 data no longer leaves the machine. The `GEMINI_*` settings are replaced by `LLM_*` settings (see `.env.example`).
- `gemini/` is renamed to `agent/` (`agent/llm.py` for the model server, `agent/agent.py` for the tool loop).
- The console list in the system prompt is built from `config/consoles.yaml` at runtime, and consoles without a real API key are marked unavailable.
- `consoles.yaml` uses `region:`; unknown keys such as `base_url:` are rejected at start-up.
- Default KnowBe4 rate limit lowered from 8 to 0.8 requests a second.
- The web chat shows a running timer, gives up after 180 seconds, sanitises rendered Markdown with DOMPurify, pins its CDN scripts and uses system fonts.
- Logs record tool names and argument keys only, never argument values or the user's question; the chat no longer returns raw exception text.
- Project renamed `knowbe4-reporting-mcp`.

### Added
- Summary tools that do the sorting and arithmetic in Python and return small results: `compare_consoles_risk`, `top_users_by_risk`, `find_user`, `phishing_campaign_summary`, `training_completion_summary`.
- One-line descriptions for every MCP tool.
- Agent safeguards: console check before each tool call, bad JSON arguments fed back to the model, large results truncated to `LLM_MAX_TOOL_CHARS`, one retry when the model returns an empty answer, `knowbe4_raw_get` hidden from the chat model unless `LLM_EXPOSE_RAW_GET=true`.
- `/health` reports whether the model server answers and the model is pulled.
- Retries for KnowBe4 429 and 502/503/504 responses, honouring `Retry-After`.
- `.env.example`, `config/consoles.example.yaml`, a step-by-step Windows setup guide in the README, and tests for the agent loop, pagination and summary tools.

### Fixed
- List tools returned only the first page. KnowBe4 answers cursor requests with `{data, pagination: {nextCursor}}`; the client now follows `nextCursor` until it is `null` and no longer stops on pages shorter than `per_page`.
- Account risk score history failed with HTTP 500 because paging parameters were sent to an endpoint that rejects them.
- Tools were sent to the model with empty parameter lists (the code read `inputSchema`; the MCP SDK uses `input_schema`).
- Phish-prone values on phishing security tests are a fraction in the API (failure events per delivered email); the summary tool now reports them as a percentage.
- `pip install -e .` failed because setuptools found several top-level packages.
- A missing comma in the old Gemini model fallback list joined two model names.

### Removed
- Google Gemini, `google-genai` and the quota fallback logic.
- Broken duplicate scripts under `scripts/`.

## [1.0.0]

- First version: read-only multi-console KnowBe4 Reporting API MCP server with a Gemini-based web chat.
