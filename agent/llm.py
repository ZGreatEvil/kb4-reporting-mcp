from __future__ import annotations

from typing import Any

import openai

from config.settings import AppConfig


class LLMError(RuntimeError):
    """failure whose message is safe to show to the user"""


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

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
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

        try:
            response = await self.client.chat.completions.create(**kwargs)
        # APITimeoutError subclasses APIConnectionError, so it goes first
        except openai.APITimeoutError as exc:
            raise LLMError(
                f"Model tidak menjawab dalam {cfg.llm_timeout_seconds:.0f} detik. "
                "Coba pertanyaan yang lebih sempit, atau naikkan LLM_TIMEOUT_SECONDS."
            ) from exc
        except openai.APIConnectionError as exc:
            raise LLMError(
                f"Tidak bisa terhubung ke server LLM di {cfg.llm_base_url}. Pastikan Ollama sedang berjalan."
            ) from exc
        except openai.NotFoundError as exc:
            raise LLMError(
                f"Model '{cfg.llm_model}' belum tersedia di server LLM. Jalankan: ollama pull {cfg.llm_model}"
            ) from exc
        except openai.BadRequestError as exc:
            if "context" in str(exc).lower():
                raise LLMError(
                    "Percakapan melebihi context length model. Persempit pertanyaan, "
                    "atau naikkan OLLAMA_CONTEXT_LENGTH jika memori GPU cukup."
                ) from exc
            raise LLMError("Server LLM menolak permintaan (HTTP 400).") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"Server LLM mengembalikan error HTTP {exc.status_code}.") from exc

        if not response.choices:
            raise LLMError("Server LLM tidak mengembalikan jawaban.")
        return response.choices[0]

    async def list_models(self) -> list[str]:
        page = await self.client.models.list()
        return [m.id for m in page.data]
