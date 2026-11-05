from __future__ import annotations

import json
from typing import Any

from google import genai
from google.genai import types

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

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
5. If the user asks for a comparison between consoles, call the respective tools for each available console and compare the results.
6. For person lookup:
   - First call list_users with the target console.
   - Find the matching first_name, last_name, or email.
   - Then call get_user with that console and the user's ID.
7. current_risk_score and phish_prone_percentage are different metrics.
8. Never reveal API keys, tokens, Authorization headers, environment variables, or credentials.
9. Answer in Indonesian unless the user asks for another language.
""".strip()


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


class QuotaExhaustedError(Exception):
    """Exception penanda bahwa model tertentu mencapai rate limit / kuota habis."""
    pass


class GeminiAgent:

    def __init__(self, config: AppConfig | None = None):
        self.config = config or load_config()

        if not self.config.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY belum dikonfigurasi.")

        self.gemini = genai.Client(api_key=self.config.gemini_api_key)
        self.system_prompt = build_system_prompt(self.config)

        self.mcp_url = (
            f"http://{self.config.mcp_host}:{self.config.mcp_port}{self.config.mcp_path}"
        )
        self.max_tool_loops = 8

        # Daftar urutan model fallback (Gemini 3 -> Gemini 2.5 / 2.0 -> Gemini 1.5)
        raw_models = [
            self.config.gemini_model,
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash"
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
        ]
        self.available_models = list(dict.fromkeys([m for m in raw_models if m]))

    @staticmethod
    def _tool_schema(tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}}
        return {
            "name": tool.name,
            "description": tool.description or f"KnowBe4 MCP tool: {tool.name}",
            "parameters": schema,
        }

    @staticmethod
    def _mcp_result_text(result: Any) -> str:
        if getattr(result, "is_error", False):
            return json.dumps(
                {"error": True, "message": "MCP tool returned an error.", "details": str(result)},
                ensure_ascii=False,
                default=str,
            )

        structured = getattr(result, "structured_content", None)
        if structured is not None:
            return json.dumps(structured, ensure_ascii=False, default=str)

        parts: list[str] = []
        for item in getattr(result, "content", None) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts)

    @staticmethod
    def _is_quota_error(exc: Any) -> bool:
        if exc is None:
            return False

        if isinstance(exc, QuotaExhaustedError):
            return True

        exc_str = str(exc).lower()
        if any(k in exc_str for k in ("429", "resource_exhausted", "quota exceeded", "rate limit", "quotaexhaustederror")):
            return True

        sub_exceptions = getattr(exc, "exceptions", [])
        for sub in sub_exceptions:
            if GeminiAgent._is_quota_error(sub):
                return True

        return False

    async def _execute_with_model(self, model_name: str, prompt: str) -> str:
        async with streamable_http_client(self.mcp_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tool_result = await session.list_tools()
                gemini_tools = [self._tool_schema(t) for t in tool_result.tools]

                contents: list[types.Content] = [
                    types.Content(
                        role="user",
                        parts=[types.Part(text=prompt)],
                    )
                ]

                generation_config = types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.1,
                    tools=[types.Tool(function_declarations=gemini_tools)],
                )

                for loop in range(self.max_tool_loops):
                    print(f"[GEMINI] {model_name} | Loop {loop + 1}", flush=True)

                    try:
                        response = await self.gemini.aio.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=generation_config,
                        )
                    except Exception as gemini_exc:
                        if self._is_quota_error(gemini_exc):
                            print(f"[GEMINI WARNING] Kuota model {model_name} habis (429).", flush=True)
                            raise QuotaExhaustedError(f"Quota exhausted on {model_name}")
                        raise gemini_exc

                    if not response.candidates:
                        raise RuntimeError("Gemini returned no candidates.")

                    candidate = response.candidates[0]
                    contents.append(candidate.content)

                    function_calls = response.function_calls or []
                    if not function_calls:
                        answer = (response.text or "").strip()
                        print(f"[GEMINI] Final answer generated via {model_name}", flush=True)
                        return answer

                    response_parts = []
                    for call in function_calls:
                        tool_name = call.name
                        tool_args = dict(call.args or {})
                        # argument values can be personal data, so log keys only
                        print(f"[GEMINI] Tool: {tool_name} | Arg keys: {sorted(tool_args)}", flush=True)

                        try:
                            t_res = await session.call_tool(tool_name, arguments=tool_args)
                            t_text = self._mcp_result_text(t_res)
                            response_parts.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response={"result": t_text},
                                )
                            )
                        except Exception as exc:
                            print(f"[MCP TOOL ERROR] {tool_name}: {type(exc).__name__}", flush=True)
                            response_parts.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response={"error": True, "message": str(exc)},
                                )
                            )

                    contents.append(types.Content(role="user", parts=response_parts))

                return "Batas maksimum MCP tool call tercapai."

    async def _ask_internal(self, prompt: str) -> str:
        quota_hit = False

        for current_model in self.available_models:
            print(f"[GEMINI] Mencoba model: {current_model}", flush=True)
            try:
                return await self._execute_with_model(current_model, prompt)
            except QuotaExhaustedError:
                quota_hit = True
                continue
            except (BaseException, Exception) as exc:
                if self._is_quota_error(exc):
                    quota_hit = True
                    continue
                print(f"[MODEL ERROR] {current_model}: {type(exc).__name__}", flush=True)
                continue

        if quota_hit:
            return (
                "⚠️ **Batas Kuota / Token Gemini API Habis (Rate Limit 429)**\n\n"
                "Semua varian model Gemini yang tersedia pada API Key ini telah mencapai batas kuota gratis (*RESOURCE_EXHAUSTED*).\n\n"
                "**Solusi:**\n"
                "1. Tunggu sekitar **30-60 detik** lalu kirim ulang pesan Anda.\n"
                "2. Ganti `GEMINI_API_KEY` di file `.env` dengan API Key baru."
            )

        return "Maaf, terjadi kendala saat menghubungkan ke server MCP atau Gemini."

    async def ask(self, prompt: str) -> str:
        prompt = prompt.strip()
        if not prompt:
            return "Masukkan pertanyaan."

        print(f"[GEMINI] User question received ({len(prompt)} chars)", flush=True)
        return await self._ask_internal(prompt)