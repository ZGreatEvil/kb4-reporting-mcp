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
- Group and department breakdowns, repeat phishing clickers, one phishing test in detail (who clicked, who reported it, report rate) and overdue training
- Answers on security awareness guidance from three NIST publications, with page citations, searched locally
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
| `KB4_CACHE_SECONDS` | `600` | KnowBe4 answers are reused for this long, so repeat and follow-up questions cost no requests. `0` always fetches fresh |
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

Check `http://127.0.0.1:8080/health`: it should show `"status": "ok"` with `"reachable": true` and `"model_pulled": true` under `llm`, and `"reachable": true` under `mcp`. `"degraded"` means Ollama is not running, the model has not been created (README step 3), the MCP server is down, or the loaded model has less context than the app needs; `warnings` says which. The status badge in the page header shows the same thing.

On the first visit the page asks for a language, **Bahasa Indonesia** or **English**. The choice is remembered in that browser and can be changed any time with the **ID | EN** switch in the header. It sets the page text and the language the model answers in. Other clients can pass it to the API directly: `POST /api/chat` with `{"message": "...", "language": "id"}` or `"en"` (default `id`; anything else is rejected with HTTP 422).

The page uses `POST /api/chat/stream` (same request body), which answers with one JSON event per line (`application/x-ndjson`) so the answer appears as it is written:

| Event | Meaning |
| --- | --- |
| `{"type": "thinking"}` | The model is working on the next step |
| `{"type": "tool", "name": "..."}` | A tool is being called |
| `{"type": "delta", "text": "..."}` | More answer text |
| `{"type": "reset"}` | Discard the text so far (it belonged to a step that turned into a tool call) |
| `{"type": "done", "answer": "..."}` | Finished; `answer` is the complete final text |
| `{"type": "error", "message": "..."}` | Failed; `message` is already in the chosen language |

The page gives up only after 180 seconds without any event, so long answers that keep progressing are not cut off. Questions sent while an answer is still coming are queued (up to 5) and sent in order; each answer shows how long it took. **Baru / New** starts a fresh conversation. The badge in the header shows whether the bot can answer (Online, Terbatas / Limited, Offline), checked every 30 seconds. The page follows the system's light or dark mode and works from a 320 px phone to an ultrawide screen.

The small local model sometimes answers from memory or loses track of pages, so the agent enforces a few rules in code: numbers that appear nowhere in the question, the definitions or earlier answers must come from a tool call made for this question; users tables and their headings are built from the data; and "lanjut" / "show 20" / "21-40" / "2" are resolved from short hidden notes stored with each answer. An answer that comes back in the wrong language (or slips into Chinese) is rewritten once. Every number in an answer must appear in the data the tools returned this turn, the question or the definitions (rounding and Indonesian/English separators allowed; small counts up to 10 are prose). If not, the model is told which numbers and rewrites once; any sentence that still carries one is removed. This guarantees each number exists in the data, not that it is used in the right context, which is why the summary tools also give a ready-made headline. `POST /api/chat` still returns the whole answer in one response.

Answers about the organisation's or a person's risk, groups, top users, phishing tests or training completion come with the fitting chart automatically (charts are cheap: the data is already fetched). Ask for a chart ("tampilkan grafiknya", "show a chart") to get one for anything else. A CSV is made only when the question asks for one ("export", "CSV", "unduh"), never on its own initiative, and the answer then carries a download link. Charts are kept in `web\static\charts\` and CSV files in `exports\` for one hour, then deleted. A CSV is reachable only through its random 32-character link, opens in Excel with names intact (UTF-8 with BOM), and cells that start with `=`, `+`, `-` or `@` are prefixed so Excel does not run them as formulas.

Questions about NIST guidance ("Menurut NIST…", "best practice…") are answered from the NIST library, with a **Sumber / Sources** line giving the publication and PDF pages.

**Periods.** Questions about a period ("dari 2026", "tahun lalu", "3 bulan terakhir", "Q3 2026", "since January", "antara Maret dan Juni 2026", "sebelum 2026") are read in code, not by the model, and the dates go to every tool that can filter: phishing tests, repeat clickers, one test in detail, training completion, overdue training (by enrolment date), risk trends, charts and CSV exports. The answer says the period it covers. Rankings of people and groups are today's state, which KnowBe4 does not keep per period; the answer then says so. The model is also told today's date, so it never treats this year as the future.

**Casual wording.** Chat spellings are spelled out before the model reads the question ("brp yg klik phising skrg" becomes "berapa yang klik phishing sekarang"). Short follow-ups that lean on the chat ("kalau grup?", "dia ada training yg telat?", "sama kayak tadi tapi buat tahun lalu") are understood from the earlier messages and the short notes kept with each answer. In a live test of 53 casual and dated questions (slang, typos, mixed Indonesian and English, vague follow-ups), the right data was used for 52 (the other used an admin health check, which is no longer offered to the chat model) and the right period reached the tools for all 17 dated ones. Restating follow-ups with an extra model call first was also tried: it was slower and got 3 of them wrong, so it is not used.

It also answers four kinds of question that need several KnowBe4 lists combined, all worked out in code:

- **Which group (or department) is riskiest**: KnowBe4's own group risk score, members and phish-prone %. In accounts where the department field is empty, it says so and uses groups.
- **Who failed several phishing tests** (repeat clickers) over the last 6 tests (up to 12), or every test in a period such as "sejak Juli 2026". Failing means clicking, entering data, opening an attachment, enabling macros, replying or scanning the QR code; the first four reproduce KnowBe4's own phish-prone % exactly on the test account's 68 tests.
- **One phishing test in detail**: who failed and how, who reported it, and the report rate.
- **Overdue training**: how many enrolments are Past Due, who has the most and which modules.

[docs/DEMO.md](docs/DEMO.md) is a 10-minute demo script that shows every capability in order.

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

## 9. Connect an MCP client (optional)

The server uses MCP Streamable HTTP. Point your MCP-compatible client to:

```text
http://127.0.0.1:8000/mcp
```

Use the MCP Inspector for local verification if desired. The Python MCP SDK's current stable line is v2 and supports Streamable HTTP.

## 10. API coverage

The server provides dedicated tools for the documented Reporting API resource families:

- Account + account risk score history
- Users + specific user + user risk score history
- Groups + specific group + group members
- Phishing campaigns + campaign detail
- Phishing Security Tests + PST detail
- PST recipients + individual recipient
- Training campaigns + campaign detail
- Training enrollments + enrollment detail
- Training store purchases + purchase detail
- Training policies + policy detail
- Generic read-only GET for documented `/v1/*` endpoints not yet wrapped

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
| `account_risk_overview(console, start_date, end_date)` | Current score and KnowBe4 level, change vs 30 and 90 days ago, 3-month figures, and the data behind "why" (phishing failures, users per level, comparison with KnowBe4's benchmark) |
| `user_risk_summary(console, user_id, start_date, end_date)` | The same for one person, plus their training status (for example how many enrolments are Past Due) |
| `list_users_page(console, status, sort, offset, limit)` | One page of at most 20 users with the total and `next_offset`, so "show more" works |
| `make_chart(console, chart, user_id, limit, start_date, end_date)` | A PNG chart (`risk_trend`, `users_by_level`, `top_users`, `phishing_tests`, `training_completion`) and a short summary of what it shows |
| `export_csv(console, dataset, user_id, status, start_date, end_date)` | A CSV download link for `users`, `phishing_tests`, `training_campaigns` or `risk_history` |
| `search_nist(query, limit)` | The best-matching passages from the local NIST library, with publication and PDF page |
| `risk_by_group(console, by, limit)` | Groups (or `department` / `location` / `division`) ranked by risk, with members and phish-prone % |
| `repeat_phishing_failures(console, tests, limit, start_date, end_date)` | People who failed two or more of the latest tests (1 request per test, cached) |
| `phishing_test_detail(console, pst_id, limit, start_date, end_date)` | One test person by person: who failed, who reported it, report rate (latest test by default) |
| `overdue_training(console, limit, start_date, end_date)` | Past Due enrolments of current users: total, people with the most, modules |

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
