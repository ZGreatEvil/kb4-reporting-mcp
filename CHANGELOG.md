# Changelog

All notable changes to this project are listed here. Dates are in YYYY-MM-DD format.

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
