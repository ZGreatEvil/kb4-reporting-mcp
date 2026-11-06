from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import openai

from agent.messages import DEFAULT_LANGUAGE, msg
from config.settings import AppConfig


class LLMError(RuntimeError):
    """failure whose message is safe to show to the user, in any supported language"""

    def __init__(self, key: str, **params: Any):
        self.key = key
        self.params = params
        super().__init__(msg(key, DEFAULT_LANGUAGE, **params))

    def text(self, language: str) -> str:
        return msg(self.key, language, **self.params)


class LLMClient:
    """thin wrapper over any openai-compatible chat completions server (ollama, lm studio, llama.cpp, vllm)"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.client = openai.AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key=config.llm_api_key or "ollama",
            timeout=config.llm_timeout_seconds,
            max_retries=0,
        )

    def _kwargs(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = self.config
        kwargs: dict[str, Any] = {
            "model": cfg.llm_model,
            "messages": messages,
            "max_tokens": cfg.llm_max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if cfg.llm_temperature is not None:
            kwargs["temperature"] = cfg.llm_temperature
        if cfg.llm_top_p is not None:
            kwargs["top_p"] = cfg.llm_top_p
        if cfg.llm_reasoning_effort:
            kwargs["reasoning_effort"] = cfg.llm_reasoning_effort
        return kwargs

    def _error(self, exc: openai.OpenAIError) -> LLMError:
        cfg = self.config
        # APITimeoutError subclasses APIConnectionError, so it goes first
        if isinstance(exc, openai.APITimeoutError):
            return LLMError("llm_timeout", seconds=cfg.llm_timeout_seconds)
        if isinstance(exc, openai.APIConnectionError):
            return LLMError("llm_unreachable", url=cfg.llm_base_url)
        if isinstance(exc, openai.NotFoundError):
            return LLMError("llm_model_missing", model=cfg.llm_model)
        if isinstance(exc, openai.BadRequestError):
            return LLMError("llm_context") if "context" in str(exc).lower() else LLMError("llm_bad_request")
        if isinstance(exc, openai.APIStatusError):
            return LLMError("llm_http", status=exc.status_code)
        return LLMError("llm_no_choice")

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        try:
            response = await self.client.chat.completions.create(**self._kwargs(messages, tools))
        except openai.OpenAIError as exc:
            raise self._error(exc) from exc

        if not response.choices:
            raise LLMError("llm_no_choice")
        return response.choices[0]

    async def chat_stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AsyncIterator[tuple[str, Any]]:
        """yields ("content", text) as the answer arrives, then ("end", choice) shaped like chat()'s result"""
        content: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish_reason = None
        try:
            stream = await self.client.chat.completions.create(**self._kwargs(messages, tools), stream=True)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    content.append(delta.content)
                    yield "content", delta.content
                # ollama sends each tool call in one delta; others split name and arguments across deltas
                for tc in delta.tool_calls or []:
                    call = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    call["id"] = tc.id or call["id"]
                    if tc.function and tc.function.name:
                        call["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        call["arguments"] += tc.function.arguments
                finish_reason = choice.finish_reason or finish_reason
        except openai.OpenAIError as exc:
            raise self._error(exc) from exc

        tool_calls = [
            SimpleNamespace(id=c["id"] or f"call_{i}", function=SimpleNamespace(name=c["name"], arguments=c["arguments"]))
            for i, c in sorted(calls.items())
        ]
        message = SimpleNamespace(content="".join(content), tool_calls=tool_calls or None)
        yield "end", SimpleNamespace(message=message, finish_reason=finish_reason)

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return [m.id for m in page.data]
