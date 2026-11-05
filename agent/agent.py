from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from agent.llm import LLMClient
from config.settings import AppConfig, load_config


SYSTEM_PROMPT_TEMPLATE = """
You are KnowBe4 Security Awareness Reporting Analyst.

You have read-only access to KnowBe4 Reporting API through MCP.

Configured Consoles:
{console_lines}

Rules:
1. Always use MCP tools for live KnowBe4 data.
2. Never invent KnowBe4 values.
3. Every KnowBe4 tool requiring "console" MUST receive one of these console ids: {available_ids}.
   Consoles marked UNAVAILABLE have no API key; never call tools for them, tell the user they are not configured.
4. {default_rule}
5. Prefer the summary tools (marked PREFER): compare_consoles_risk, top_users_by_risk, find_user,
   phishing_campaign_summary, training_completion_summary. They return complete, pre-sorted results.
   Use the raw list_* tools only when no summary tool fits.
6. For person lookup: call find_user with a name, email or job title, then use the returned id
   with get_user or get_user_risk_score_history. If there are several matches, list them and ask which one.
7. current_risk_score (the overall risk score, higher is riskier) and phish_prone_percentage
   (the share of people who failed phishing tests) are different metrics. Never call the risk score a phishing rate.
8. Never reveal API keys, tokens, Authorization headers, environment variables, or credentials.
9. Answer in Indonesian unless the user asks for another language.
10. The tools are read-only. Refuse requests to create, change or delete anything in KnowBe4.
11. If a tool result says "truncated", say the data was cut and ask the user to narrow the question (a console, status, group, campaign or date range).
12. Copy names, numbers and dates exactly as they appear in tool results. Do not translate, round or re-spell them.
""".strip()

# exposed to mcp clients, but too open-ended for a small local model
HIDDEN_TOOLS = {"knowbe4_raw_get"}


def build_system_prompt(config: AppConfig) -> str:
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
    )


def _error(message: str) -> str:
    return json.dumps({"error": True, "message": message}, ensure_ascii=False)


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
        self.system_prompt = build_system_prompt(self.config)
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
            if tool.name in HIDDEN_TOOLS and not self.config.llm_expose_raw_get:
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
            return _error("MCP tool returned an error.")

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
            "Result truncated to fit the model's context. Tell the user and suggest narrowing "
            "the question with filters such as status, group_id, campaign_id, user_id or max_records."
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

    async def _run_tool(self, session: Any, call: Any, tool_names: set[str]) -> str:
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

        try:
            result = await session.call_tool(name, arguments=args)
        except Exception as exc:
            print(f"[MCP TOOL ERROR] {name}: {type(exc).__name__}", flush=True)
            return _error(f"Tool {name} failed ({type(exc).__name__}).")

        return self._truncate(self._mcp_result_text(result))

    async def ask(self, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            return "Masukkan pertanyaan."

        print(f"[AGENT] User question received ({len(prompt)} chars)", flush=True)
        max_loops = self.config.llm_max_tool_loops

        async with self._session_factory() as session:
            listed = await session.list_tools()
            tools = self._openai_tools(listed.tools)
            tool_names = {t["function"]["name"] for t in tools}

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]

            nudged = False
            for loop in range(max_loops):
                print(f"[AGENT] {self.config.llm_model} | Loop {loop + 1}", flush=True)
                choice = await self.llm.chat(messages, tools)
                message = choice.message
                calls = [c for c in (message.tool_calls or []) if getattr(c, "function", None)]

                if not calls:
                    answer = (message.content or "").strip()
                    # qwen sometimes finishes inside its thinking and writes no answer; ask once more
                    if not answer and not nudged and choice.finish_reason != "length":
                        nudged = True
                        print("[AGENT] Empty answer, asking for the final answer", flush=True)
                        messages.append({
                            "role": "user",
                            "content": "Tuliskan jawaban akhir untuk pengguna sekarang, berdasarkan hasil tool di atas.",
                        })
                        continue
                    if choice.finish_reason == "length":
                        answer += "\n\n_(Jawaban terpotong karena batas LLM_MAX_TOKENS.)_"
                    print("[AGENT] Final answer generated", flush=True)
                    return answer.strip() or "Model tidak memberikan jawaban."

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
                    content = await self._run_tool(session, call, tool_names)
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})

        return (
            f"Batas maksimum {max_loops} putaran tool call tercapai tanpa jawaban akhir. "
            "Coba persempit pertanyaan."
        )
