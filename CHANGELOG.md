# Changelog

All notable changes to this project are listed here. Dates are in YYYY-MM-DD format.

## [Unreleased]

### Added
- `modstore_content`: ModStore's media catalogue (453 videos and coaching items in the test account, through the Real-Time Coaching API), searchable by title, type, style and language, with whether the account already has each item and whether an Indonesian version exists. ModStore questions use it when the coaching key is set and end with a line saying what it covers (training courses are not listed by any KnowBe4 API).
- `templates`: KnowBe4's template library or the account's own templates (phishing emails with difficulty and categories, landing pages, notification emails, callback scripts). One template type per request, since all types at once timed out at KnowBe4.
- `account_settings` (admin roles and Second Chance settings) and `campaign_settings` (how phishing and training campaigns are scheduled and set up).
- `security_coaching` also lists coaching campaigns (and how many are in test mode), detection rules and notification templates; if that part fails, the rest still answers.
- ModStore questions ("modstore", "katalog konten knowbe4", "training catalogue") are answered from the account's own library and end with a line saying the whole ModStore catalogue is not available through KnowBe4's API (checked live: the KSAT and Reporting APIs only list content already added; the Real-Time Coaching catalogue query covers coaching media only and returned errors). The library headline says the same.
- CSV exports of every module's progress (`modules`) and of the emails reported to PhishER (`reported_emails`). `/health` lists which product API keys each console has (names only), and `list_consoles` shows each product's requests in the last 24 hours. `test_knowbe4.py` checks each product key with one read-only query.
- KnowBe4 product APIs, read-only, each with its own optional key (`ksat_key_env`, `phisher_key_env`, `piq_key_env`, `coach_key_env`, `events_key_env` in `consoles.yaml`): KnowBe4's official **industry benchmarks** (`industry_benchmark`), emails employees **reported** to PhishER (`reported_emails`, `phisher_rules`, chart `reported_emails`), **USB** and **physical QR** tests, **all campaign types** including callback and vishing (`simulation_overview`), the **admin audit log**, **Real-Time Coaching**, **PasswordIQ**, **User Event API** events, and which products are in use (`product_status`). The GraphQL client refuses anything that is not a query before it is sent; tools without a key are not offered to the model, and the "what can you do?" answer lists only configured products.
- Fresh data on request: "ambil data terbaru", "refresh", "perbarui", "jangan pakai cache", "fetch fresh data" and similar clear the 10-minute KnowBe4 copy before the answer (a hidden `refresh_data` MCP tool, at most once a minute per console so repeated requests cannot drain the daily limit), and the answer says the data was just fetched. "Tes phishing terbaru" (the latest test) does not count as a refresh.
- From KnowBe4's developer documentation (all Reporting API, read-only, current key): training per **module** (`training_by_module`: enrolled, passed, Past Due, not started, completion %, typical minutes; one module by name with who is overdue), the **training library** (`training_library`: content types, retired, never assigned), a **group's risk trend** (`group_risk_trend`, using the group risk score history endpoint the client did not call before), **sign-ins** (`sign_in_activity`: who never signed in), **new joiners** (`new_joiners`), **callback (phone) phishing** (`callback_phishing_summary`), and in `phishing_test_detail` how fast people failed, who opened but did nothing and bounces. Charts `modules` and `group_trend`.
- Module, library, sign-in, new-joiner, callback, group-trend and click-speed questions reach their tool even when the model skips it (the call is made in code); module questions are never answered from training campaigns. The capability answer lists the new abilities.
- README: how to share the chat on the office network (`WEB_HOST`, `WEB_ALLOWED_HOSTS`, a firewall rule for private networks), and the newer abilities in "What is included".
- Risk score answers start with a line built from the data: the score and level now, the value 30 and 90 days ago with the change, and the asked period's change when a period was named, in the chat's language. An answer once called the 30-day value "three months ago". Answers whose first line is about something else (a person's overdue training) or that refuse a forecast keep their own. Sentences further down that put the 30-day value under "three months" (or the other way round) are removed.
- Typos and uncommon words: misspellings of the words the bot works with are corrected before anything reads the question ("trainnig yg terlmbat" → "training yang terlambat", "rsik scroe" → "risk score", "phisingnya" → "phishingnya"), and more slang and less common words are spelled out ("nunggak", "molor", "jatuh tempo", "kecolongan", "kejebak", "rawan", "pegawai", "gw", "kpn", "nurunin", "ppl", "whats"). The corrector only fixes one missing, extra or swapped letter (two from 10 letters), only towards the bot's own words, and leaves names, acronyms, links, emails and real words with endings alone; on the 3,505 distinct words of the NIST PDFs it changed none.
- "Apa saja yang bisa kamu lakukan?", "kamu bisa apa aja?", "What can you do?" and similar get a fixed list of what the bot does and doesn't do, with example questions, in the chosen language. The model's own list opened like an off-topic refusal and offered features that don't exist (Excel export, departments, several consoles). Questions that only start that way ("apa yang bisa kamu lakukan untuk menurunkan risiko?") still go to the model.
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
- "Which ModStore videos would you recommend for new staff?" was answered with NIST passages: asking to recommend videos, modules, content or templates, or anything about ModStore, no longer triggers the NIST guidance nudge ("how do we make training more effective" still does).
- `modstore_content`: a title search that matches nothing (the model searched for "new") is left out with a note instead of returning an empty list, and the headline counts Indonesian versions over every match (from 20 rows the model once said there were none; 316 items have one). Items with an Indonesian version come first.
- Comparative judgements ("more targeted", "lebih praktis") are removed like other judgements.
- Judgements the data cannot hold ("Animated and Humorous suit awareness engagement", "sangat efektif", "lebih menarik") are removed from answers. Each judgement is checked as a concept in both languages, so wording found in a tool result (a NIST passage saying "effective") stays; titles and quoted names ("Respectful Workplace: Effective Communication") are never read as judgements; a section left empty loses its heading.
- A ModStore question answered from the ModStore catalogue no longer forces a library or module-progress call as well.
- A "why" sentence that gives a cause the data cannot hold ("high completion because the module is mandatory") is removed; the word is allowed when a tool result or the question contains it (a module titled "Mandatory ...").
- On ModStore questions the model's own catalogue remarks are removed before the fixed line is added (it once advised contacting a team for full ModStore access, which is made up).
- A table of library items could be out of order under a "sorted by publish date" heading (a 2023 item on top); rows that are all library items now follow the tool's order.
- An Indonesian answer listing English module titles was taken for English and rewritten; the model then replied with a remark about the request ("Jawaban saya sebelumnya sudah ... Bahasa Indonesia"), which was shown as the answer. The language check now skips quoted text, table rows and the text after a bullet's label, and a remark instead of a rewrite keeps the original draft.
- Closing offers ("Apakah Anda ingin melihat ...?", "Let me know if ...") are removed from the end of answers.
- A year on its own anywhere in a question ("rekomendasikan modul dari modstore 2026") now sets the period; it is ignored when there are two years, when it is part of a date, id or quoted title, when it is more than ten years old, or when a count word follows ("2010 request").
- Library answers start with a line built from the counts (total, retired, never assigned; new, published and added for a period), and a sentence calling the never-assigned count "new" is dropped (seen live in English).
- Module answers and the module chart: episodes of one series ("The Inside Man: Season 1", 12 episodes) are one row, so the top 10 shows ten different things instead of near-identical episodes; asking for a series by name still lists each episode. The chart shows each module's split (passed, in progress, not started, Past Due) as 100% bars with "% passed · enrolments" beside them, so a 1,548-enrolment series no longer squashes the rest. Each module carries facts built from the data ("only 7 enrolled…", "every enrolment is Past Due", its length) and the answer may only explain with those (a "best module" answer had said "because it is a short, mandatory module"). The headline leads with what was asked (best, lowest, most overdue). Names now match from the start of words and numbers match whole ("season 1" matched "Season 2 Ep 01").
- "Newest / recommend modules" answered that there is no date; the training library now gives each item's KnowBe4 publish date and the date it was added to the account, sorts by either, and takes a period ("terbaru di 2026": 2 published, 7 added).
- Product status said "Second Chance on 0 devices", which came out as "aktif untuk 0 perangkat"; it now says Second Chance is not installed on any device. Product labels are plain names (an English explanation in them ended up inside Indonesian answers), and the product status headline is whole sentences (its label style, "In use: … Connected but not in use: …", was copied untranslated; clean in 5 of 5 live Indonesian answers after the change). Indonesian answers have the model's misspellings seen so far corrected ("Prodak", "Kampain", "Kampayan"), and decimals written with a dot become commas ("14.31%" next to the risk line's "38,01" read inconsistently, and an Indonesian reader takes a dot for thousands); thousands such as "2.233", dates, versions, IP addresses, links, quoted names and table rows are left alone.
- A risk score answered from the bare account record once came with the wrong level ("38.01 (level Medium)"; 38 is Low). The raw account and user records now carry KnowBe4's level, a level written next to a risk score that contradicts KnowBe4's bands is corrected in the answer, and a plain risk score question answered only from the bare account record also fetches the full overview (level, 30/90-day change, reasons).
- A table wider than the answer bubble showed its last column cut off mid-word with nothing saying it scrolls. The side with more columns now fades out (and flips as you scroll), and the table's scrollbar is visible; on touch screens, which hide scrollbars, the fade is the cue.
- Product API errors: an unknown console in `product_status` read as the SDK's masked "Error executing tool"; a rejected product key (KnowBe4 answers 403) now says the key was rejected or lacks access.
- "Why is that campaign at 0%?" got made-up reasons ("those are phishing tests"). Training campaigns now carry their enrolment statuses (passed, Past Due, not started, in progress), so the reason comes from the data: on the test account every 0% campaign is closed with all its enrolments Past Due.
- A forecast refusal in the model's own words is replaced by the fixed sentence ("Saya tidak bisa memprediksi nilai di masa depan."), so it reads the same every time; answers that do not refuse are left alone.
- People with the same full name are told apart in search results and in "which one?" by their email, and "archived" when they are; they used to be listed identically.
- A "why" follow-up ("yg 0% itu kenapa") answered without looking at the data again now fetches the summary the previous answer used, so the reason comes from the data instead of a guess (seen once in four live runs).
- "dia", "him", "her" right after a search that found several people get "which one?" with the numbered list again, instead of an answer about whichever person the model picked.
- `POST /api/chat` returns the `[Data used: ...]` note as `note`, as the streaming endpoint does, so API clients can keep "2" and "lanjut" working.
- The overdue training summary says "N people have at least one" instead of "held by N people", which came out as "ditahan oleh" (detained by) in Indonesian.
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
