"""User-facing server messages in every supported language, so nothing comes out half-translated."""
from __future__ import annotations

from typing import Any, Literal

Language = Literal["id", "en"]
DEFAULT_LANGUAGE: Language = "id"

# name used in the system prompt
LANGUAGE_NAMES: dict[str, str] = {"id": "Indonesian", "en": "English"}

MESSAGES: dict[str, dict[str, str]] = {
    "llm_timeout": {
        "id": "Model tidak menjawab dalam {seconds:.0f} detik. Coba pertanyaan yang lebih sempit, atau naikkan LLM_TIMEOUT_SECONDS.",
        "en": "The model did not answer within {seconds:.0f} seconds. Try a narrower question, or raise LLM_TIMEOUT_SECONDS.",
    },
    "llm_unreachable": {
        "id": "Tidak bisa terhubung ke server LLM di {url}. Pastikan Ollama sedang berjalan.",
        "en": "Cannot reach the LLM server at {url}. Make sure Ollama is running.",
    },
    "llm_model_missing": {
        "id": "Model '{model}' belum tersedia di server LLM. Jalankan: ollama pull {model}",
        "en": "Model '{model}' is not available on the LLM server. Run: ollama pull {model}",
    },
    "llm_context": {
        "id": "Percakapan melebihi context length model. Persempit pertanyaan, atau naikkan OLLAMA_CONTEXT_LENGTH jika memori GPU cukup.",
        "en": "The conversation exceeds the model's context length. Narrow the question, or raise OLLAMA_CONTEXT_LENGTH if GPU memory allows.",
    },
    "llm_bad_request": {
        "id": "Server LLM menolak permintaan (HTTP 400).",
        "en": "The LLM server rejected the request (HTTP 400).",
    },
    "llm_http": {
        "id": "Server LLM mengembalikan error HTTP {status}.",
        "en": "The LLM server returned HTTP error {status}.",
    },
    "llm_no_choice": {
        "id": "Server LLM tidak mengembalikan jawaban.",
        "en": "The LLM server returned no answer.",
    },
    "empty_question": {
        "id": "Masukkan pertanyaan terlebih dahulu.",
        "en": "Please enter a question first.",
    },
    "loop_limit": {
        "id": "Batas maksimum {loops} putaran tool call tercapai tanpa jawaban akhir. Coba persempit pertanyaan.",
        "en": "Reached the limit of {loops} tool-call rounds without a final answer. Try a narrower question.",
    },
    "cut_off": {
        "id": "_(Jawaban terpotong karena batas LLM_MAX_TOKENS.)_",
        "en": "_(Answer cut off by the LLM_MAX_TOKENS limit.)_",
    },
    "no_answer": {
        "id": "Model tidak memberikan jawaban.",
        "en": "The model did not give an answer.",
    },
    "nudge": {
        "id": "Tuliskan jawaban akhir untuk pengguna sekarang, berdasarkan hasil tool di atas.",
        "en": "Write the final answer for the user now, based on the tool results above.",
    },
    "mcp_transport": {
        "id": "MCP mengalami error pada transport.",
        "en": "The MCP server had a transport error.",
    },
    "pipeline_error": {
        "id": "Terjadi error pada LLM → MCP → KnowBe4.",
        "en": "Something went wrong in LLM → MCP → KnowBe4.",
    },
}


def msg(key: str, language: str = DEFAULT_LANGUAGE, **params: Any) -> str:
    texts = MESSAGES[key]
    return texts.get(language, texts[DEFAULT_LANGUAGE]).format(**params)
