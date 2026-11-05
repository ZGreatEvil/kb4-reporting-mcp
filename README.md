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
- Health-check script
- No Docker required

## Requirements

- Windows 10 or 11. The commands below are for Windows PowerShell; the Python parts also run on macOS and Linux.
- Python 3.12 (tested). `pyproject.toml` allows 3.10 and later.
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

The project uses the stable MCP v2 line (`mcp>=2,<3`). Do not create a top-level folder named `mcp`: it would shadow the installed MCP SDK. The chat agent uses the `openai` package (`openai>=3.46,<4`) only as a client for the local Ollama server; nothing is sent to OpenAI.

## 3. Install Ollama and the model

1. Install Ollama with the installer from [ollama.com/download/windows](https://ollama.com/download/windows) (`OllamaSetup.exe`), or in PowerShell:

   ```powershell
   irm https://ollama.com/install.ps1 | iex
   ```

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

   `q8_0` stores the context cache at about half the memory of the default; it applies to every Ollama model on the machine.

4. Check that it works and fits on the GPU:

   ```powershell
   ollama run qwen3.5:4b --think=false "Reply with just the word OK."
   ollama ps
   ```

   `ollama ps` should show `100% GPU` under `PROCESSOR` and `32768` under `CONTEXT`. If it shows a CPU share (for example `29%/71% CPU/GPU`), the model plus context does not fit: set a smaller `OLLAMA_CONTEXT_LENGTH` (`24576`, then `16384`), restart Ollama and check again. With more GPU memory, try a larger value; Ollama recommends at least 64k for agents.

   Measured on the 6 GB test laptop:

   | `OLLAMA_CONTEXT_LENGTH` | Memory | `PROCESSOR` |
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
| `LLM_MODEL` | `qwen3.5:4b` | Model name on that server; change it to try another model, no code change needed |
| `LLM_TEMPERATURE`, `LLM_TOP_P` | empty | Empty uses the model's own defaults (Ollama ships Qwen's recommended values) |
| `LLM_REASONING_EFFORT` | empty | Empty keeps thinking on. `none` is faster but in testing answered 6 of 8 questions correctly instead of 16 of 16, once without looking at the data |
| `LLM_MAX_TOKENS` | `8192` | Cap on one reply, including thinking |
| `LLM_MAX_TOOL_LOOPS` | `8` | Tool-call rounds per question |
| `LLM_MAX_TOOL_CHARS` | `12000` | Longer tool results are cut down before the model sees them |
| `LLM_TIMEOUT_SECONDS` | `180` | Per model call |
| `LLM_EXPOSE_RAW_GET` | `false` | Hides the open-ended `knowbe4_raw_get` tool from the chat model |
| `KB4_RATE_LIMIT_RPS` | `0.8` | KnowBe4 requests per second (about 48 a minute) |

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

For a local-only deployment the default server binds to `127.0.0.1`. If you later expose it beyond localhost, add a proper MCP authentication layer before doing so. The `.env` file includes `MCP_BEARER_TOKEN` as a reserved setting for that next step; the sample server deliberately does not claim that value is enforced automatically by the MCP SDK.

## 8. Start the web chat

Make sure Ollama is running (`ollama ps` answers), then in a second terminal:

```powershell
.\.venv\Scripts\python.exe run_web.py
```

Check `http://127.0.0.1:8080/health`: it should show `"status": "ok"` with `"reachable": true` and `"model_pulled": true` under `llm`. `"degraded"` means Ollama is not running or the model is not pulled.

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
| `find_user(console, query)` | Users matching a name, email, job title or department, with their ids |
| `phishing_campaign_summary(console, limit, sort)` | Phishing security tests, newest first (`sort=latest`) or worst first (`sort=highest_ppp`), with `phish_prone_percent` |
| `training_completion_summary(console, campaign_id, start_date, end_date, limit)` | Training campaigns, newest first, with completion % and the average |

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

The default is 0.8 requests a second (about 48 a minute), below the burst limit KnowBe4 is reported to apply. The client retries network errors, 429 and 502/503/504 with exponential backoff and honours `Retry-After`; a 500 is not retried. If 429s persist, lower the rate further.

### Local model errors

- "Tidak bisa terhubung ke server LLM": Ollama is not running. Start it from the Start menu, then check `ollama ps`.
- "Model ... belum tersedia": run `ollama pull <LLM_MODEL>`.
- Very slow answers: run `ollama ps`. If `PROCESSOR` shows a CPU share, the model plus context does not fit in GPU memory; lower `OLLAMA_CONTEXT_LENGTH` or use a smaller model.

### Port already in use

Change:

```env
MCP_PORT=8001
WEB_PORT=8081
```

Then restart the relevant process.

## 14. Development

Run the tests (no Ollama, KnowBe4 or network needed; the agent, pagination and summary tests use fakes):

```powershell
.\.venv\Scripts\python.exe -m pytest
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
| `agent/llm.py` | OpenAI-compatible client for the local model, with readable errors |
| `agent/agent.py` | Tool loop: MCP session, console checks, truncation, system prompt |
| `web/` | FastAPI app and the chat page |
| `config/settings.py` | `.env` and `consoles.yaml` loading |

## 15. Important implementation note about 2026 pagination

KnowBe4's current Reporting API documentation describes `per_page` with a maximum of 500 and `cursor=0` for large result sets, while the older `page` parameter is being deprecated. This project uses `per_page` + cursor first and deliberately avoids depending on page-based pagination.

If KnowBe4 changes the cursor contract for a specific endpoint, update `KnowBe4Client.list_paginated()` once instead of changing every tool.

## Official references

- KnowBe4 Reporting API: https://developer.knowbe4.com/rest/reporting
- Ollama OpenAI compatibility: https://docs.ollama.com/api/openai-compatibility
- Ollama context length: https://docs.ollama.com/context-length
- MCP Python SDK: https://py.sdk.modelcontextprotocol.io/
