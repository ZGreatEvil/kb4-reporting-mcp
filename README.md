# KnowBe4 Gemini MCP — Multi-Console Reporting (No Docker)

A local, read-only MCP server and web chat application for KnowBe4 Reporting API, using Gemini API as the LLM.

## What is included

- Multi-console configuration (one KnowBe4 console per company or business unit, any names you choose)
- KnowBe4 Reporting API Bearer-token authentication
- Regional endpoints: US / EU / CA / UK / DE
- Reporting endpoints for account, risk score history, users, groups, phishing campaigns, phishing security tests and recipients, training campaigns, training enrollments, training store purchases and policies
- Read-only generic `knowbe4_raw_get` for newly documented `/v1/*` GET endpoints
- Pagination with `per_page` up to 500 + cursor-based iteration and a configurable record ceiling
- Rate limiting and retry/backoff for transient network failures
- MCP Streamable HTTP server on localhost
- Gemini API chat agent using the same read-only reporting functions
- Simple local web chat UI
- Health-check script
- No Docker required

## Requirements

- Windows 10/11, macOS, or Linux
- Python 3.10+
- A KnowBe4 subscription with Reporting API access and one Reporting API key per console
- A Gemini API key

KnowBe4 currently documents the Reporting API base URLs for US, EU, CA, UK and DE. Authentication uses `Authorization: Bearer <token>`. Pagination uses `per_page` (maximum 500) and `cursor`; the older `page` parameter is being deprecated. All API timestamps are UTC.

## 1. Create the project

Extract the ZIP into a normal folder, for example:

```powershell
C:\Projects\knowbe4-gemini-mcp
```

Open that folder in VS Code.

## 2. Create a Python virtual environment

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

If PowerShell blocks activation, you can run the interpreter directly without activating:

```powershell
.\.venv\Scripts\python.exe --version
```

## 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The project uses the current stable MCP v2 line (`mcp>=2,<3`). Do not create a top-level folder named `mcp`, because that would shadow the installed MCP SDK package. and the Google GenAI SDK (`google-genai>=2.3.0`) because Gemini's current Interactions API documentation requires that SDK line for Interactions API features.

## 4. Configure Gemini

Copy:

```text
.env.example -> .env
```

Then set:

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.6-flash
```

The SDK reads `GEMINI_API_KEY` from the environment.

## 5. Configure KnowBe4 consoles

Copy:

```text
config/consoles.example.yaml -> config/consoles.yaml
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

Do not commit `.env` or `config/consoles.yaml` to Git.

## 6. Test the KnowBe4 API keys

From the project root:

```powershell
python test_knowbe4.py
```

Expected output is similar to:

```text
{'console': 'main', 'status': 'ok', 'account_name': '...', 'subscription_level': 'Diamond', 'current_risk_score': 43.5}
{'console': 'subsidiary', 'status': 'skipped', 'reason': 'KB4_SUBSIDIARY_API_KEY not set'}
```

If you get `401`, the token is wrong, expired/revoked, or belongs to a different API type. Reporting API keys are separate from User Event API keys.

## 7. Start the MCP server

```powershell
python run_mcp.py
```

Default MCP endpoint:

```text
http://127.0.0.1:8000/mcp
```

This server is **read-only**. No POST/PUT/PATCH/DELETE KnowBe4 operation is exposed.

### MCP authentication

For a local-only deployment the default server binds to `127.0.0.1`. If you later expose it beyond localhost, add a proper MCP authentication layer before doing so. The `.env` file includes `MCP_BEARER_TOKEN` as a reserved setting for that next step; the sample server deliberately does not claim that value is enforced automatically by the MCP SDK.

## 8. Start the Gemini web chat

Open another terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python run_web.py
```

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

The Gemini agent calls the reporting functions directly. The MCP server exposes the same functions to an MCP-compatible host.

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

## 11. Data size and LLM context safety

The API can return very large datasets. The project therefore uses `KB4_MAX_RECORDS_PER_TOOL` as a safety ceiling (default 5,000). For large investigations, filter at the API level using supported parameters such as `status`, `group_id`, `campaign_id`, `user_id`, or `store_purchase_id`.

The model should not be given an entire organization dataset unless that is truly required.

## 12. Security notes

- API keys remain server-side and are never sent to Gemini as credentials.
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
python -m pip install -r requirements.txt
python -c "import mcp; print(\"MCP SDK:\", getattr(mcp, \"__version__\", \"installed\"), mcp.__file__)"
```

### `Missing API key for console`

Check that the env variable named by `api_key_env` exists in `.env`.

### HTTP 401

Regenerate/verify the KnowBe4 Reporting API key in the KnowBe4 Reporting API Management Console. Do not use a User Event API key here.

### HTTP 429

Lower:

```env
KB4_RATE_LIMIT_RPS=4
```

The client also retries transient network errors with exponential backoff. If the API returns 429, your environment may need a more conservative request rate.

### `gemini` errors

Check:

```powershell
python -c "from google import genai; print('google-genai OK')"
```

and confirm `GEMINI_API_KEY` is present.

### Port already in use

Change:

```env
MCP_PORT=8001
WEB_PORT=8081
```

Then restart the relevant process.

## 14. Development

Run tests:

```powershell
pip install -e ".[dev]"
pytest
```

Basic syntax check:

```powershell
python -m compileall .
```

## 15. Important implementation note about 2026 pagination

KnowBe4's current Reporting API documentation describes `per_page` with a maximum of 500 and `cursor=0` for large result sets, while the older `page` parameter is being deprecated. This project uses `per_page` + cursor first and deliberately avoids depending on page-based pagination.

If KnowBe4 changes the cursor contract for a specific endpoint, update `KnowBe4Client.list_paginated()` once instead of changing every tool.

## Official references

- KnowBe4 Reporting API: https://developer.knowbe4.com/rest/reporting
- Google Gemini function calling: https://ai.google.dev/gemini-api/docs/function-calling
- Google Gemini Interactions API: https://ai.google.dev/gemini-api/docs/interactions-overview
- MCP Python SDK: https://py.sdk.modelcontextprotocol.io/
