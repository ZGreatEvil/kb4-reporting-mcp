# KnowBe4 Reporting MCP — Multi-Console Reporting (No Docker)

A local, read-only MCP server and web chat application for KnowBe4 Reporting API, using a free open-weight model running locally (Ollama by default), so KnowBe4 data never leaves the machine.

## What is included

- Multi-console configuration (one KnowBe4 console per company or business unit, any names you choose)
- KnowBe4 Reporting API Bearer-token authentication
- Regional endpoints: US / EU / CA / UK / DE
- Reporting endpoints for account, risk score history, users, groups, phishing campaigns, phishing security tests and recipients, training campaigns, training enrollments, training store purchases and policies
- Read-only generic `knowbe4_raw_get` for newly documented `/v1/*` GET endpoints
- Pagination with `per_page` up to 500 + cursor-based iteration and a configurable record ceiling
- Rate limiting and retry/backoff for transient network failures
- MCP Streamable HTTP server on localhost
- Local LLM chat agent (any OpenAI-compatible server: Ollama, LM Studio, llama.cpp, vLLM) using the same read-only tools over MCP
- Simple local web chat UI
- Charts (line, bar, pie) drawn with matplotlib and CSV exports, both produced in code from KnowBe4 data
- Group and department breakdowns, repeat phishing clickers, one phishing test in detail (who clicked, who reported it, report rate, how fast) and overdue training
- Training per module and the training content library, group risk trends, who never signed in, new joiners and callback (phone) phishing
- With optional product API keys: KnowBe4's official industry benchmarks, emails employees reported (PhishER), USB and physical QR tests, all campaign types, the admin audit log, Real-Time Coaching, PasswordIQ and events from other security tools
- Answers on security awareness guidance from three NIST publications, with page citations, searched locally
- Periods in the question ("dari 2026", "3 bulan terakhir", "last quarter"), applied to every tool that can filter by date; without one, the past 12 months
- Casual Indonesian and English, chat spellings, uncommon words and typos ("brp yg nunggak trainnig") understood
- A fixed answer to "apa saja yang bisa kamu lakukan?" / "what can you do?" listing only what the bot really does
- Health-check script
- No Docker required

## Requirements

- Windows 10 or 11. The commands below are for Windows PowerShell; the Python parts also run on macOS and Linux.
- Python 3.12 (tested). 3.11 or later is required (`matplotlib` 3.11 needs it).
- [Ollama](https://ollama.com) and about 4 GB of free disk for the default model.
- An NVIDIA GPU is strongly recommended. Tested on an RTX 3060 Laptop GPU with 6 GB of VRAM: `qwen3.5:4b` with a 32k context runs entirely on the GPU. Without a GPU, Ollama falls back to the CPU and answers are much slower.
- A KnowBe4 subscription with Reporting API access and one **Reporting API** key per console (User Event API keys do not work here).

KnowBe4 currently documents the Reporting API base URLs for US, EU, CA, UK and DE. Authentication uses `Authorization: Bearer <token>`. Pagination uses `per_page` (maximum 500) and `cursor`; the older `page` parameter is deprecated from November 2026. All API timestamps are UTC.

## 1. Get the code

With Git:

```powershell
git clone https://github.com/ZGreatEvil/kb4-reporting-mcp.git C:\Projects\kb4-reporting-mcp
cd C:\Projects\kb4-reporting-mcp
```

Without Git: on the GitHub page choose **Code → Download ZIP** and extract it to `C:\Projects\kb4-reporting-mcp`.

Keep the folder out of any web server's document root (for example `C:\xampp\htdocs`): the `.env` file you create later holds the API keys.

## 2. Install Python and the dependencies

Check for Python 3.12:

```powershell
py -3.12 --version
```

If that fails, install it (or use the installer from [python.org](https://www.python.org/downloads/windows/)), then open a new terminal:

```powershell
winget install --id Python.Python.3.12 --exact
```

Create the virtual environment and install the project:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

This guide always calls `.\.venv\Scripts\python.exe` directly, so you never need to activate the venv (PowerShell blocks `Activate.ps1` by default). `pip install -r requirements.txt` also works if you do not need the tests.

Charts use `matplotlib` (`>=3.11,<4`) and the NIST library uses `pypdf` (`>=6.21,<7`); both are installed by the command above.

The project uses the stable MCP v2 line (`mcp>=2,<3`). Do not create a top-level folder named `mcp`: it would shadow the installed MCP SDK. The chat agent uses the `openai` package (`openai>=3.46,<4`) only as a client for the local Ollama server; nothing is sent to OpenAI.

## 3. Install Ollama and the model

1. Install Ollama with the installer from [ollama.com/download/windows](https://ollama.com/download/windows) (`OllamaSetup.exe`, about 1.6 GB), or in PowerShell:

   ```powershell
   irm https://ollama.com/install.ps1 | iex
   ```

   The PowerShell command cannot resume: on an unreliable connection it can fail part-way with "connection was aborted". If that happens, download the installer with `curl`, which resumes where it stopped (run the same line again if it gives up), then run it:

   ```powershell
   curl.exe -L -C - --retry 5 -o "$env:USERPROFILE\Downloads\OllamaSetup.exe" https://ollama.com/download/OllamaSetup.exe
   & "$env:USERPROFILE\Downloads\OllamaSetup.exe"
   ```

   The installer leaves your downloaded models (in `%USERPROFILE%\.ollama`) and the `OLLAMA_*` settings alone, so reinstalling or upgrading does not mean downloading models again.

2. Download the model (about 3.3 GB):

   ```powershell
   ollama pull qwen3.5:4b
   ```

   If the progress stops for minutes, press `Ctrl+C` and run the same command again: it resumes where it stopped. A VPN can make downloads stall repeatedly; `%LOCALAPPDATA%\Ollama\server.log` shows `stalled; retrying` when that happens.

3. Give the model enough context and save GPU memory. These are user environment variables; `setx` only affects programs started afterwards:

   ```powershell
   setx OLLAMA_CONTEXT_LENGTH 32768
   setx OLLAMA_FLASH_ATTENTION 1
   setx OLLAMA_KV_CACHE_TYPE q8_0
   ```

   Then quit Ollama from its tray icon (right-click → Quit) and start it again from the Start menu.

   Do the same after installing or updating Ollama: the copy the installer starts can miss these settings (it ran with a 4096 context in testing) until Ollama is restarted from the Start menu. The model from step 4 has its context built in, so it is not affected; step 5 shows how to check.

   `q8_0` stores the context cache at about half the memory of the default; it applies to every Ollama model on the machine.

4. Create the chat model from the project's `ollama\Modelfile`. It is `qwen3.5:4b` with the 32k context and the sampling settings built in, so the context no longer depends on Ollama having picked up `OLLAMA_CONTEXT_LENGTH` (Ollama's OpenAI-compatible API cannot set the context size itself). It reuses the downloaded model, so nothing more is downloaded:

   ```powershell
   ollama create kb4-analyst -f ollama\Modelfile
   ```

   If your GPU needs a smaller context (see below), change `num_ctx` in `ollama\Modelfile` and run the command again.

5. Check that it works and fits on the GPU:

   ```powershell
   ollama run kb4-analyst --think=false "Reply with just the word OK."
   ollama ps
   ```

   `ollama ps` should show `100% GPU` under `PROCESSOR` and `32768` under `CONTEXT`. If it shows a CPU share (for example `29%/71% CPU/GPU`), the model plus context does not fit: set a smaller `num_ctx` in `ollama\Modelfile` (`24576`, then `16384`), run `ollama create` again and check again. With more GPU memory, try a larger value; Ollama recommends at least 64k for agents.

   Measured on the 6 GB test laptop:

   | Context | Memory | `PROCESSOR` |
   | --- | --- | --- |
   | 65536 | 5.3 GB | 29%/71% CPU/GPU |
   | 40960 | 4.6 GB | 17%/83% CPU/GPU |
   | 32768 | 3.7 GB | 100% GPU |
   | 24576 | 3.5 GB | 100% GPU |

## 4. Configure the chat model

Create your settings file:

```powershell
Copy-Item .env.example .env
notepad .env
```

The `LLM_*` defaults already point at Ollama on this machine:

| Setting | Default | What it does |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Any OpenAI-compatible server (Ollama, LM Studio, llama.cpp, vLLM) |
| `LLM_MODEL` | `kb4-analyst` | Model name on that server (made in step 3); change it to try another model, no code change needed |
| `LLM_TEMPERATURE`, `LLM_TOP_P`, `LLM_PRESENCE_PENALTY` | `0.6`, `0.95`, `0` | Qwen's "precise" thinking-mode sampling from its model card. A high presence penalty (Ollama's default for this model is 1.5) can make it slip into Chinese. Empty uses the model's own default |
| `LLM_REASONING_EFFORT` | empty | Empty keeps thinking on. `none` is faster but in testing answered 6 of 8 questions correctly instead of 16 of 16, once without looking at the data |
| `LLM_MAX_TOKENS` | `8192` | Cap on one reply, including thinking |
| `LLM_MAX_TOOL_LOOPS` | `8` | Tool-call rounds per question |
| `LLM_MAX_TOOL_CHARS` | `12000` | Longer tool results are cut down before the model sees them |
| `LLM_TIMEOUT_SECONDS` | `180` | Per model call |
| `LLM_EXPOSE_RAW_GET` | `false` | Hides the open-ended `knowbe4_raw_get` tool from the chat model |
| `LLM_EXPOSE_RAW_LISTS` | `false` | Hides raw user lists and full risk histories (up to 1,000 points) from the chat model; the summary tools cover them |
| `LLM_HISTORY_MESSAGES` | `6` | Earlier messages sent with each question, so follow-ups such as "2" or "show 20 more" work. Kept only in the open page |
| `KB4_RATE_LIMIT_RPS` | `0.8` | KnowBe4 requests per second (about 48 a minute) |
| `KB4_CACHE_SECONDS` | `600` | KnowBe4 answers are reused for this long, so repeat and follow-up questions cost no requests. `0` always fetches fresh. A question that asks for fresh data ("ambil data terbaru", "refresh", "jangan pakai cache", "fetch fresh data") skips the copy for that answer, at most once a minute per console |
| `KB4_USAGE_FILE` | `.kb4_usage.json` | Where the rolling 24-hour request count is kept (git-ignored). Change it only to keep the count somewhere else, for example on a shared drive when two copies run against the same console |
| `KB4_DAILY_LIMIT` | empty | Requests per console per rolling 24 hours. Empty uses KnowBe4's limit: 2,000 plus the account's licensed seats |
| `WEB_ALLOWED_HOSTS` | empty | Extra host names the web chat answers to, comma-separated (for a LAN or Docker demo). `127.0.0.1` and `localhost` always work; any other name gets "Invalid host header" |
| `KB4_CONSOLES_FILE` | empty | Path to a consoles file other than `config/consoles.yaml` |

Every setting is checked at start-up. A mistake stops the server with a short list naming the setting and the problem, for example `WEB_PORT='eighty' in .env must be a whole number.` or `KB4_RATE_LIMIT_RPS in .env: Input should be less than or equal to 4`.

## 5. Configure KnowBe4 consoles

```powershell
Copy-Item config\consoles.example.yaml config\consoles.yaml
notepad config\consoles.yaml
```

Example:

```yaml
consoles:
  main:
    display_name: Main Company
    region: us
    api_key_env: KB4_MAIN_API_KEY

  subsidiary:
    display_name: Subsidiary
    region: us
    api_key_env: KB4_SUBSIDIARY_API_KEY
```

Each console needs `display_name`, `region` (`us`, `eu`, `ca`, `uk` or `de`) and `api_key_env`. Unknown keys (for example `base_url:`) are rejected at start-up.

Then add the API keys to `.env`:

```env
KB4_MAIN_API_KEY=...
KB4_SUBSIDIARY_API_KEY=...
```

A console whose key is missing, empty or a placeholder such as `xxxx` is listed as unavailable, and the chat tells the user it is not configured.

Do not commit `.env` or `config/consoles.yaml` to Git (both are in `.gitignore`).

## 6. Test the KnowBe4 API keys

From the project folder:

```powershell
.\.venv\Scripts\python.exe test_knowbe4.py
```

Expected output is similar to:

```text
{'console': 'main', 'status': 'ok', 'account_name': '...', 'subscription_level': 'Diamond', 'current_risk_score': 43.5}
{'console': 'subsidiary', 'status': 'skipped', 'reason': 'KB4_SUBSIDIARY_API_KEY not set'}
```

If you get `401`, the token is wrong, expired or revoked, or belongs to a different API type. Reporting API keys are separate from User Event API keys.

Product API keys named in `consoles.yaml` are checked too, one line each, with the smallest read-only query, for example `{'console': 'main', 'product': 'PhishER', 'status': 'ok'}`.

## 7. Start the MCP server

Once, before the first start, build the NIST library:

```powershell
.\.venv\Scripts\python.exe -m kb4_mcp.knowledge
```

It downloads three public PDFs from `nvlpubs.nist.gov` (NIST SP 800-50 Rev. 1, the Cybersecurity Framework 2.0 and NIST TN 2276, the Phish Scale) into `knowledge\pdfs\` and writes a search index to `knowledge\nist_index.json`. This is the only download; questions are searched locally and nothing is sent anywhere. If the PDFs are already in `knowledge\pdfs\`, add `--no-download`. Without the library the bot still works and says the NIST library is not set up when asked about NIST.

In a first terminal:

```powershell
.\.venv\Scripts\python.exe run_mcp.py
```

Default MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

This server is **read-only**. No POST/PUT/PATCH/DELETE KnowBe4 operation is exposed.

### MCP authentication

The server has no authentication of its own and binds to `127.0.0.1`, so only programs on this machine can reach it. Do not expose it beyond localhost without putting a real authentication layer (for example an authenticated reverse proxy over HTTPS) in front of it.

## 8. Start the web chat

Make sure Ollama is running (`ollama ps` answers), then in a second terminal:

```powershell
.\.venv\Scripts\python.exe run_web.py
```

Check `http://127.0.0.1:8080/health`: it should show `"status": "ok"` with `"reachable": true` and `"model_pulled": true` under `llm`, and `"reachable": true` under `mcp`. `"degraded"` means Ollama is not running, the model has not been created (README step 3), the MCP server is down, or the loaded model has less context than the app needs; `warnings` says which. `product_apis` lists which optional product API keys each console has (names only). The MCP tool `list_consoles` also shows each product's requests in the last 24 hours. The status badge in the page header shows the same thing.

On the first visit the page asks for a language, **Bahasa Indonesia** or **English**. The choice is remembered in that browser and can be changed any time with the **ID | EN** switch in the header. It sets the page text and the language the model answers in. Other clients can pass it to the API directly: `POST /api/chat` with `{"message": "...", "language": "id"}` or `"en"` (default `id`; anything else is rejected with HTTP 422).

The page uses `POST /api/chat/stream` (same request body), which answers with one JSON event per line (`application/x-ndjson`) so the answer appears as it is written:

| Event | Meaning |
| --- | --- |
| `{"type": "thinking"}` | The model is working on the next step |
| `{"type": "tool", "name": "..."}` | A tool is being called |
| `{"type": "delta", "text": "..."}` | More answer text |
| `{"type": "reset"}` | Discard the text so far (it belonged to a step that turned into a tool call) |
| `{"type": "done", "answer": "...", "note": "..."}` | Finished; `answer` is the complete final text, `note` the hidden `[Data used: ...]` line to send back with the history |
| `{"type": "error", "message": "..."}` | Failed; `message` is already in the chosen language |

The page gives up only after 180 seconds without any event, so long answers that keep progressing are not cut off. Questions sent while an answer is still coming are queued (up to 5) and sent in order; each answer shows how long it took. While the bot works the bubble shows what it is doing; the answer then appears once, complete with its chart (showing text as it was written made a checked or redone answer vanish and appear twice). **Baru / New** starts a fresh conversation. The badge in the header shows whether the bot can answer (Online, Terbatas / Limited, Offline), checked every 30 seconds. The page follows the system's light or dark mode and works from a 320 px phone to an ultrawide screen.

The small local model sometimes answers from memory or loses track of pages, so the agent enforces a few rules in code: numbers that appear nowhere in the question, the definitions or earlier answers must come from a tool call made for this question; users tables and their headings are built from the data; and "lanjut" / "show 20" / "21-40" / "2" are resolved from short hidden notes stored with each answer. An answer that comes back in the wrong language (or slips into Chinese) is rewritten once. Every number in an answer must appear in the data the tools returned this turn, the question or the definitions (rounding and Indonesian/English separators allowed; small counts up to 10 are prose). If not, the model is told which numbers and rewrites once; any sentence that still carries one is removed. This guarantees each number exists in the data, not that it is used in the right context, which is why the summary tools also give a ready-made headline. `POST /api/chat` returns the whole answer in one response, `{"answer": "...", "note": "..."}`. Clients keep follow-ups working the way the page does: send each earlier answer back in `history` as an `assistant` message with its `note` on the line before the answer.

Answers about the organisation's or a person's risk, groups, top users, phishing tests or training completion come with the fitting chart automatically (charts are cheap: the data is already fetched). Ask for a chart ("tampilkan grafiknya", "show a chart") to get one for anything else. A CSV is made only when the question asks for one ("export", "CSV", "unduh"), never on its own initiative, and the answer then carries a download link. Charts are kept in `web\static\charts\` and CSV files in `exports\` for one hour, then deleted. A CSV is reachable only through its random 32-character link, opens in Excel with names intact (UTF-8 with BOM), and cells that start with `=`, `+`, `-` or `@` are prefixed so Excel does not run them as formulas.

Questions about NIST guidance are answered from the NIST library, with a **Sumber / Sources** line giving the publication and PDF pages. That includes any question about how to run, measure or improve awareness training or reduce phishing clicks ("bagaimana cara mengukur efektivitas training?"), whether or not it mentions NIST.

**Periods.** Questions about a period ("dari 2026", "tahun lalu", "3 bulan terakhir", "Q3 2026", "since January", "antara Maret dan Juni 2026", "sebelum 2026") are read in code, not by the model, and the dates go to every tool that can filter: phishing tests, repeat clickers, one test in detail, training completion, overdue training (by enrolment date), risk trends, charts and CSV exports. The answer says the period it covers. **Without a period in the question, over-time data covers the past 12 months**, not everything since the account began; overdue training is the exception, because an unfinished enrolment from years ago is still overdue today. Rankings of people and groups are today's state, which KnowBe4 does not keep per period; the answer then says so. The model is also told today's date, so it never treats this year as the future.

**Casual wording.** Chat spellings, slang and less common words are spelled out before the model reads the question ("brp yg nunggak training" becomes "berapa yang terlambat training"), and typos of the words the bot works with are corrected ("trainnig yg terlmbat", "rsik scroe"). The corrector fixes one missing, extra or swapped letter, only towards the bot's own words, and leaves names, acronyms, links and real words alone; on the 3,505 distinct words of the NIST PDFs it changed none. Short follow-ups that lean on the chat ("kalau grup?", "dia ada training yg telat?", "sama kayak tadi tapi buat tahun lalu") are understood from the earlier messages and the short notes kept with each answer; "dia" right after a search that found several people gets "which one?" instead of a guess. In live tests, the right data was used for 53 of 53 casual and dated questions, 42 of 42 questions with slang, uncommon words and typos, 22 of 22 questions about training modules and 20 of 20 questions about the product APIs, and the right period reached the tools for all 21 dated ones. Restating follow-ups with an extra model call first was also tried: it was slower and got 3 of them wrong, so it is not used.

Risk score answers start with a line built from the data (score and level now, the value 30 and 90 days ago, and the asked period's change), so the periods are never mixed up; "apa saja yang bisa kamu lakukan?" / "what can you do?" gets a fixed list of what the bot does.

It also answers four kinds of question that need several KnowBe4 lists combined, all worked out in code:

- **Which group (or department) is riskiest**: KnowBe4's own group risk score, members and phish-prone %. In accounts where the department field is empty, it says so and uses groups.
- **Who failed several phishing tests** (repeat clickers) over the last 6 tests (up to 12), or every test in a period such as "sejak Juli 2026". Failing means clicking, entering data, opening an attachment, enabling macros, replying or scanning the QR code; the first four reproduce KnowBe4's own phish-prone % exactly on the test account's 68 tests.
- **One phishing test in detail**: who failed and how, who reported it, and the report rate.
- **Overdue training**: how many enrolments are Past Due, who has the most and which modules.

[docs/DEMO.md](docs/DEMO.md) is a 12-minute demo script that shows every capability in order.

Open:

```text
http://127.0.0.1:8080
```

Ask questions such as:

```text
Compare the current risk score of all consoles.
```

```text
Show the latest phishing campaigns in main and identify the campaign with the highest phish-prone percentage.
```

```text
Find the 10 active users with the highest current risk score in main.
```

```text
Compare July 2026 training completion between main and subsidiary.
```

The chat agent reaches KnowBe4 only through the MCP server's tools, the same ones any MCP-compatible host can use. `knowbe4_raw_get` is hidden from the chat model unless `LLM_EXPOSE_RAW_GET=true`. Local models are slower than cloud ones. On the 6 GB test laptop, answers took 6–37 seconds (about 17 on average) across eight typical questions; the page shows a running timer and gives up after 180 seconds.

### Share the chat on the office network (optional)

By default the chat only answers on this PC. To let colleagues on the same trusted network use it:

1. Find this PC's address with `ipconfig` (the `IPv4 Address`, for example `192.168.1.20`).
2. In `.env` set `WEB_HOST=0.0.0.0` and `WEB_ALLOWED_HOSTS=192.168.1.20` (add the PC name too if people use it), then restart `run_web.py`.
3. In a PowerShell window opened with **Run as administrator**, allow the port on private networks only:

   ```powershell
   New-NetFirewallRule -DisplayName "KnowBe4 chat" -Direction Inbound -Protocol TCP -LocalPort 8080 -Profile Private -Action Allow
   ```

   Make sure Windows marks the office network as **Private** (Settings → Network & internet). Remove the rule later with `Remove-NetFirewallRule -DisplayName "KnowBe4 chat"`.
4. Colleagues open `http://192.168.1.20:8080`.

The chat has no login: anyone who can reach that address can ask about your KnowBe4 data. Only do this on a network you trust, never on public Wi-Fi. The MCP server stays on `127.0.0.1` either way.

## 9. Connect an MCP client (optional)

The server uses MCP Streamable HTTP. Point your MCP-compatible client to:

```text
http://127.0.0.1:8000/mcp
```

Use the MCP Inspector for local verification if desired. The Python MCP SDK's current stable line is v2 and supports Streamable HTTP.

## 10. API coverage

The server provides dedicated tools for the documented Reporting API resource families:

- Account + account risk score history: `get_account`, `get_account_risk_score_history`, `knowbe4_health_check`
- Users + specific user + user risk score history: `list_users`, `get_user`, `get_user_risk_score_history`
- Groups + specific group + group members + group risk score history: `list_groups`, `get_group`, `list_group_members`, `get_group_risk_score_history`
- Phishing campaigns + campaign detail: `list_phishing_campaigns`, `get_phishing_campaign`
- Phishing Security Tests + PST detail: `list_phishing_security_tests`, `get_phishing_security_test`
- PST recipients + individual recipient: `list_phishing_recipients`, `get_phishing_recipient`
- Training campaigns + campaign detail: `list_training_campaigns`, `get_training_campaign`
- Training enrollments + enrollment detail: `list_training_enrollments`, `get_training_enrollment`
- Training store purchases + purchase detail: `list_training_store_purchases`, `get_training_store_purchase`
- Training policies + policy detail: `list_training_policies`, `get_training_policy`
- Generic read-only GET for documented `/v1/*` endpoints not yet wrapped: `knowbe4_raw_get` (hidden from the chat model unless `LLM_EXPOSE_RAW_GET=true`)

KnowBe4 may add new endpoints. The raw GET tool is the compatibility escape hatch for any documented read-only `/v1/*` endpoint that has not yet received a dedicated wrapper.

### Summary tools

These fetch the full collection, do the sorting and arithmetic in Python and return a small result. The chat model is told to prefer them:

| Tool | Returns |
| --- | --- |
| `compare_consoles_risk()` | Current risk score of every console, ranked, plus consoles without a key |
| `top_users_by_risk(console, limit, status)` | Users ranked by `current_risk_score` |
| `find_user(console, query, limit)` | Users matching a name, email, job title or department, with their ids |
| `phishing_campaign_summary(console, limit, sort, start_date, end_date)` | Phishing security tests, newest first (`sort=latest`) or worst first (`sort=highest_ppp`), with `phish_prone_percent` |
| `training_completion_summary(console, campaign_id, start_date, end_date, limit)` | Training campaigns, newest first, with completion % and the average |
| `training_by_group(console, campaign, campaign_date, groups, by, include_archived)` | One training campaign per group: people (or enrolments) completed, in progress, not started and Past Due, with totals that count each person once. The campaign by name, id or start date (when several start the same day, the one aimed at the named groups; otherwise the chat asks which); groups by name, or the ones named in the question, or the campaign's own. Archived people are left out unless asked and are counted in a note. The table is built in code; CSV dataset `training_by_group` |
| `phishing_by_group(console, pst_id, test, start_date, end_date, groups, include_archived)` | One phishing test (or every test in a period) per group: delivered, failed, clicked, entered data, opened attachments, reported, failure and report %. Nothing named = the latest test. Groups from the question or every group that got the test; KnowBe4's own system groups (Real-Time Coaching "RTC_" groups) get no row but are counted |
| `campaign_people(console, campaign, campaign_date, groups, status, include_archived, limit)` | The people behind a campaign's numbers: who is Past Due, not started, in progress or completed (name, email, each module's status), optionally in some groups |
| `group_members(console, group, sort, limit)` | Who is in a group, with each person's risk score, level, phish-prone % and Past Due training |
| `person_training(console, user_id, name, limit)` | One person's training enrolments: campaign, module, status, enrolled and completed dates, minutes spent |
| `coverage_gaps(console, start_date, end_date, limit)` | Active people with no phishing test, no training enrolment, or neither, in a period (like KnowBe4's unphished and untrained users report) |
| `compare_periods(console, metric, start_date, end_date, compare_start, compare_end)` | The same phishing or training numbers for two periods side by side, with the change; without a second period, the one just before |
| `account_risk_overview(console, start_date, end_date)` | Current score and KnowBe4 level, change vs 30 and 90 days ago, 3-month figures, and the data behind "why" (phishing failures, users per level, comparison with KnowBe4's benchmark) |
| `user_risk_summary(console, user_id, start_date, end_date)` | The same for one person, plus their training status (for example how many enrolments are Past Due) |
| `list_users_page(console, status, sort, offset, limit)` | One page of at most 20 users with the total and `next_offset`, so "show more" works |
| `make_chart(console, chart, user_id, limit, start_date, end_date, group_id)` | A PNG chart (`risk_trend`, `users_by_level`, `top_users`, `phishing_tests`, `training_completion`, `groups`, `modules`, `group_trend`) and a short summary of what it shows |
| `export_csv(console, dataset, user_id, status, start_date, end_date)` | A CSV download link for `users`, `phishing_tests`, `training_campaigns`, `risk_history`, `modules` (every module's progress) or `reported_emails` (PhishER; needs its key) |
| `search_nist(query, limit)` | The best-matching passages from the local NIST library, with publication and PDF page |
| `risk_by_group(console, by, limit)` | Groups (or `department` / `location` / `division`) ranked by risk, with members and phish-prone % |
| `repeat_phishing_failures(console, tests, limit, start_date, end_date)` | People who failed two or more of the latest tests (1 request per test, cached) |
| `phishing_test_detail(console, pst_id, limit, start_date, end_date)` | One test person by person: who failed, who reported it, report rate, how fast people failed (minutes from delivery), who opened but did nothing, bounces (latest test by default) |
| `overdue_training(console, limit, start_date, end_date)` | Past Due enrolments of current users: total, people with the most, modules |
| `training_by_module(console, module, sort, limit, start_date, end_date)` | Per training module: enrolled, passed, Past Due, not started, in progress, completion %, typical minutes and data-backed facts; episodes of one series are one row; `module` (words from its name) focuses on one module or series, lists each episode and who is overdue |
| `training_library(console, content_type, limit, sort, start_date, end_date)` | The training content the account has (store purchases): types, length, KnowBe4 publish date, date added to the account, retired, enrolments, and content never assigned; `sort` = `most_used`, `newest` or `recently_purchased`; a period keeps what was published or added in it. KnowBe4's APIs do not list the whole ModStore catalogue, so questions about ModStore end with a line saying so and pointing to Training → ModStore in the console |
| `group_risk_trend(console, group, limit, start_date, end_date)` | One group's risk score over time, or the 90-day change of the riskiest groups (1 request per group) |
| `sign_in_activity(console, limit)` | Active users who never signed in to KnowBe4 and those who have not for over 90 days |
| `new_joiners(console, limit, start_date, end_date)` | People who joined in the period (employee start date, or when they were added to KnowBe4) against everyone else: risk, phishing, Past Due training |
| `callback_phishing_summary(console, limit, start_date, end_date)` | Callback (phone) phishing: calls to the number and data given on the call |

`time_spent` on enrolments and the content `duration` have no unit in KnowBe4's docs; `time_spent` only makes sense as seconds against 4–10 minute modules (median 396 on the test account), so it is shown as minutes = value ÷ 60, and the content length is shown as listed.

### Product API tools (optional keys)

KnowBe4's developer site also documents GraphQL APIs (KSAT, PhishER, PasswordIQ, Real-Time Coaching) and a User Event API. Each needs its own key, generated in KnowBe4 under **Account Settings → API** (prefer the read-only scopes): add it to `.env` and name it in `consoles.yaml` with `ksat_key_env`, `phisher_key_env`, `piq_key_env`, `coach_key_env` or `events_key_env` (see `config/consoles.example.yaml`). Every GraphQL product is served at the console's site (`https://training.knowbe4.com/graphql` for US accounts, `eu.`, `ca.`, `uk.`, `de.knowbe4.com/graphql` elsewhere); the User Event API at `https://api.events.knowbe4.com` (or `api-eu.events…` and so on).

These APIs can also change and delete data. The client only sends fixed read-only queries written in `kb4_mcp/products.py`, with values passed as variables, and `knowbe4.client.readonly_query` refuses any document that contains a `mutation` or `subscription` before it is sent; the User Event API is only ever read (`GET /events`). KnowBe4 limits GraphQL queries to a complexity of 150; the queries here stay under it. Their requests are cached like the Reporting API's (and dropped by "refresh"), and counted per product (`console:ksat`, `console:phisher`, …) apart from the Reporting API's daily limit, because KnowBe4 does not document limits for them.

| Tool | Key | Returns |
| --- | --- | --- |
| `industry_benchmark(console, industry)` | KSAT | Our average phish-prone % against KnowBe4's official benchmark for the account's industry and company size (before training, after 90 days, after 1–3 years); another industry by name. Falls back to all industries when the account's benchmark industry is not one KnowBe4 benchmarks |
| `simulation_overview(console)` | KSAT | Every phishing campaign by type (standard, callback, vishing), active ones, latest runs, USB and physical QR tests, AIDA, Second Chance |
| `usb_test_results(console, limit)` | KSAT | USB drive tests: files opened, macros enabled, who |
| `physical_qr_results(console)` | KSAT | Physical QR code tests: scans and data entered per location |
| `admin_audit_log(console, category, limit, start_date, end_date)` | KSAT | What admins changed, by whom and when (default the last 90 days) |
| `reported_emails(console, category, status, limit, start_date, end_date)` | PhishER | Emails employees reported as suspicious: threat / spam / clean / not yet triaged, still open, per month, top reporters, latest |
| `phisher_rules(console, limit)` | PhishER | Rules, active or not, and how many reported emails each matched |
| `security_coaching(console, start_date, end_date)` | Real-Time Coaching | Setup (what is missing), coaching campaigns (and how many are in test mode), detection rules, coaching sent, people coached, repeat offenders |
| `modstore_content(console, search, content_type, style, language, limit)` | Real-Time Coaching | ModStore's media catalogue (videos and coaching content): type, style, languages, Indonesian version, and whether the account already has it. ModStore training courses are not listed by any KnowBe4 API |
| `password_risks(console)` | PasswordIQ | Weak, shared, breached or never-expiring Active Directory passwords from the last scan, or that it never scanned |
| `user_events(console, user_email, limit, start_date, end_date)` | User Event | Events other security tools pushed in, by type, source and person |
| `product_status(console)` | any | Which products are connected and actually in use |
| `templates(console, kind, search, source, difficulty, limit)` | KSAT | KnowBe4's template library or the account's own: phishing email templates (with difficulty and the largest categories), landing pages, notification emails, callback scripts |
| `account_settings(console)` | KSAT | Admin roles (people, groups, areas with access; KnowBe4's access numbers are shown as given) and Second Chance settings |
| `campaign_settings(console, kind, search, limit)` | KSAT | How phishing or training campaigns are set up: recurring or one-off, next run, audience, business hours, tracking, AIDA templates; training status, auto-enrol, duration, knowledge refreshers |

A product tool is only offered to the chat model when a console has that product's key, and the "what can you do?" answer lists only those products. Checked live on the test account (10 Nov 2026): 59 reported emails, 5 PhishER rules, 2 USB tests, 1 physical QR test, 69 campaigns, an audit log, AIDA on; PasswordIQ never scanned, Real-Time Coaching without a campaign, no user events. The User Event field names (`event_type`, `target_user`, `source`, `occurred_date`) come from the API's event schema; there were no events to check them against.

Dates are `YYYY-MM-DD`; anything else (or a start after the end) is refused with a clear message, since a loose date would filter silently wrong. The summary tools return a `headline`: one sentence built in code from the data, which the model starts its answer from, so names, numbers and periods are never garbled.

Note on phish-prone values: on phishing security tests the API's `phish_prone_percentage` is a fraction (failure events ÷ emails delivered, so `0.25` means 25 %, and it can exceed `1` when people fail in more than one way), while on users it is already 0–100. `phishing_campaign_summary` converts the test value to a real percentage as `phish_prone_percent`. This was worked out from live data (it matched every test checked); KnowBe4's documentation does not state it.

## 11. Data size and LLM context safety

The API can return very large datasets. The project therefore uses `KB4_MAX_RECORDS_PER_TOOL` as a safety ceiling (default 5,000). For large investigations, filter at the API level using supported parameters such as `status`, `group_id`, `campaign_id`, `user_id`, or `store_purchase_id`.

The model should not be given an entire organization dataset unless that is truly required. The chat agent cuts any tool result longer than `LLM_MAX_TOOL_CHARS` (default 12,000 characters) down to the total count and the first rows, and tells the model to ask the user to narrow the question.

Pagination follows KnowBe4's cursor scheme: the first request sends `cursor=0`, each response carries `pagination.nextCursor`, and the client sends that value back until it is `null`. Pages can be shorter than `per_page` before the end (training campaigns come back 10 at a time), so the client never stops on a short page. The risk score history endpoints return a plain list and reject paging parameters, so they are called without them.

## 12. Security notes

- API keys remain server-side and are never sent to the model. With the default local model, KnowBe4 data never leaves the machine.
- Logs show tool names and argument keys only, never argument values or the user's question.
- Never log the `Authorization` header.
- Keep `.env` private.
- Use HTTPS if the MCP endpoint is ever exposed outside localhost.
- Put the MCP server behind an authenticated reverse proxy when remote access is required.
- Because KnowBe4 API keys grant access to reporting data, treat them as production secrets.
- Never put the project inside a web server's document root (for example `C:\xampp\htdocs`), where `.env` could be downloaded.
- CSV exports contain KnowBe4 data (names, emails, scores). They are deleted after one hour, but anyone who can reach port 8080 and has the link can download one within that hour, so keep the web chat on localhost.
- The web chat answers only to its own host names (see `WEB_ALLOWED_HOSTS`), so a malicious web page cannot use DNS rebinding to read KnowBe4 data through the browser; the MCP server does the same. Cross-site form posts are refused.
- The page loads no third-party scripts: marked, DOMPurify and Lucide are served from `web/static/vendor/` (checked against jsDelivr's published hashes) under a strict Content-Security-Policy. Model output is sanitised before it is shown, and the policy blocks inline scripts even if something slipped through.
- `knowbe4_raw_get` accepts only `/v1/...` paths; `..`, encoded `..`, backslashes and empty segments are refused, so it cannot reach other paths on KnowBe4's servers.
- Some antivirus products inspect local web traffic too: in testing, Kaspersky's web protection injected its own script into the page and added itself to the security policy. The app still works; it is the antivirus, not the app.

### How to share this project

Never zip the folder as it is: that ships `.env` (the API keys) and `.venv` (which only works on the machine that built it). Instead:

- with Git: `git archive --format=zip -o knowbe4-mcp.zip HEAD` (only tracked files, so `.env` and `.venv` are left out), or
- without Git: zip everything except `.env`, `.venv/`, `config/consoles.yaml` and `__pycache__/`.

The recipient copies `.env.example` to `.env`, fills in their own keys and creates their own venv.

## 13. Troubleshooting

### `ModuleNotFoundError`

If the error is `No module named 'mcp.server'`, make sure the dependency is installed and that the project does not contain a local package named `mcp`. This project uses `kb4_mcp/` specifically to avoid shadowing the official MCP SDK package.

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -c "import mcp; print(mcp.__file__)"
```

### `Missing API key for console`

Check that the env variable named by `api_key_env` exists in `.env`.

### HTTP 401

Regenerate/verify the KnowBe4 Reporting API key in the KnowBe4 Reporting API Management Console. Do not use a User Event API key here.

### HTTP 429

Lower:

```env
KB4_RATE_LIMIT_RPS=0.5
```

KnowBe4's documented limits are 4 requests a second, 50 a minute, and 2,000 a day plus the number of licensed users. The default is 0.8 requests a second (about 48 a minute). The client also counts real requests per console over a rolling 24 hours (saved in `.kb4_usage.json`, git-ignored), warns in the MCP server log at 80 % and, at the limit, refuses with a clear message instead of calling KnowBe4. `list_consoles` shows the current count. Answers from the last `KB4_CACHE_SECONDS` are reused and do not count. The client retries network errors, 429 and 502/503/504 with exponential backoff and honours `Retry-After`; a 500 is not retried. If 429s persist, lower the rate further.

### Local model errors

- "Tidak bisa terhubung ke server LLM": Ollama is not running. Start it from the Start menu, then check `ollama ps`.
- "Model ... belum ada di server LLM": create it with `ollama create kb4-analyst -f ollama\Modelfile` (step 3), or `ollama pull <LLM_MODEL>` for another model.
- Very slow answers: run `ollama ps`. If `PROCESSOR` shows a CPU share, the model plus context does not fit in GPU memory; lower `num_ctx` in `ollama\Modelfile`, run `ollama create` again, or use a smaller model.
- `/health` warns about a small context: the loaded model runs with less than 16,384 tokens of context. Use the `kb4-analyst` model from step 3.

### Settings errors at start-up

The server prints which setting is wrong and stops, for example `WEB_PORT='eighty' in .env must be a whole number.` or `config/consoles.yaml, consoles: main.region: ... Unsupported KnowBe4 region`. Fix that line and start it again.

### "Invalid host header"

The web chat was opened under a name it does not know (a PC name or LAN address). Add that name to `WEB_ALLOWED_HOSTS` in `.env`, for example `WEB_ALLOWED_HOSTS=demo-pc`, and restart `run_web.py`. Only do this on a trusted network: the chat has no login.

### Port already in use

Change:

```env
MCP_PORT=8001
WEB_PORT=8081
```

Then restart the relevant process.

## 14. Development

Run the tests and the linter (no Ollama, KnowBe4, network or `config/consoles.yaml` needed: the tests use fakes and the example consoles file):

```powershell
.\.venv\Scripts\python.exe -m pytest -W error
.\.venv\Scripts\python.exe -m ruff check .
```

### Changing the styles

The page uses Tailwind CSS 3, pre-built into `web/static/app.css` (committed, so running the app needs no build step). After changing class names in `web/static/index.html`, `web/static/app.js`, `tailwind.config.js` or `web/static/tailwind.input.css`, rebuild it with Tailwind's standalone CLI (no Node.js needed). Download it once and check it against the published checksums:

```powershell
$d = "$env:TEMP\tw"; New-Item -ItemType Directory -Force $d | Out-Null
curl.exe -L --retry 5 -o "$d\tailwindcss.exe" https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.19/tailwindcss-windows-x64.exe
curl.exe -L -o "$d\sha256sums.txt" https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.19/sha256sums.txt
(Get-FileHash "$d\tailwindcss.exe" -Algorithm SHA256).Hash.ToLower()
Select-String -Path "$d\sha256sums.txt" -Pattern 'windows-x64'
```

The two hashes must match. Then, from the project folder:

```powershell
& "$env:TEMP\tw\tailwindcss.exe" -c tailwind.config.js -i web/static/tailwind.input.css -o web/static/app.css --minify
```

Basic syntax check:

```powershell
.\.venv\Scripts\python.exe -m compileall -q agent config kb4_mcp knowbe4 web tests
```

Layout:

| Path | Purpose |
| --- | --- |
| `knowbe4/client.py` | Read-only KnowBe4 Reporting API client: auth, rate limit, retries, cursor pagination |
| `kb4_mcp/server_impl.py` | MCP server and tool list |
| `kb4_mcp/summaries.py` | Summary tools (sorting and arithmetic in Python) |
| `kb4_mcp/outputs.py` | Charts (matplotlib) and CSV exports |
| `kb4_mcp/knowledge.py` | NIST library: download, index and local search |
| `docs/DEMO.md` | Demo script |
| `agent/llm.py` | OpenAI-compatible client for the local model, with readable errors |
| `agent/agent.py` | Tool loop: MCP session, console checks, truncation, system prompt |
| `agent/messages.py` | Every user-facing server message in Indonesian and English |
| `web/` | FastAPI app and the chat page: `static/index.html`, its script `static/app.js`, `static/app.css` (built from `static/tailwind.input.css` with `tailwind.config.js`) and the libraries in `static/vendor/` |
| `ollama/Modelfile` | The `kb4-analyst` chat model: `qwen3.5:4b` with its context and sampling built in |
| `config/settings.py` | `.env` and `consoles.yaml` loading |

## 15. Important implementation note about 2026 pagination

KnowBe4's current Reporting API documentation describes `per_page` with a maximum of 500 and `cursor=0` for large result sets, while the older `page` parameter is being deprecated. This project uses `per_page` + cursor first and deliberately avoids depending on page-based pagination.

If KnowBe4 changes the cursor contract for a specific endpoint, update `KnowBe4Client.list_paginated()` once instead of changing every tool.

## Official references

- KnowBe4 Reporting API: https://developer.knowbe4.com/rest/reporting
- Ollama OpenAI compatibility: https://docs.ollama.com/api/openai-compatibility
- Ollama context length: https://docs.ollama.com/context-length
- MCP Python SDK: https://py.sdk.modelcontextprotocol.io/
