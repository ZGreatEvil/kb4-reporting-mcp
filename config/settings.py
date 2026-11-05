from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

REGION_BASE_URLS = {
    "us": "https://us.api.knowbe4.com",
    "eu": "https://eu.api.knowbe4.com",
    "ca": "https://ca.api.knowbe4.com",
    "uk": "https://uk.api.knowbe4.com",
    "de": "https://de.api.knowbe4.com",
}


# values like "xxxxxxxx" or "your-key-here" in .env count as no key
PLACEHOLDER_KEY = re.compile(r"^(x+|\.\.\.|changeme|your[-_ ].*)$", re.IGNORECASE)


class ConsoleConfig(BaseModel):
    # reject unknown keys so e.g. a stray base_url: fails loudly instead of being ignored
    model_config = ConfigDict(extra="forbid")

    display_name: str
    region: str = "us"
    api_key_env: str

    @field_validator("region")
    @classmethod
    def _known_region(cls, value: str) -> str:
        region = value.lower().strip()
        if region not in REGION_BASE_URLS:
            raise ValueError(
                f"Unsupported KnowBe4 region: {value}. Use one of: {', '.join(REGION_BASE_URLS)}"
            )
        return region

    @property
    def base_url(self) -> str:
        return REGION_BASE_URLS[self.region]

    @property
    def has_api_key(self) -> bool:
        value = os.getenv(self.api_key_env, "").strip()
        return bool(value) and not PLACEHOLDER_KEY.match(value)

    @property
    def api_key(self) -> str:
        value = os.getenv(self.api_key_env, "").strip()
        if not self.has_api_key:
            raise RuntimeError(
                f"Missing API key for console '{self.display_name}'. "
                f"Set environment variable {self.api_key_env}."
            )
        return value


def _optional_float(name: str) -> float | None:
    # unset means "use the model's own default" (ollama ships qwen's recommended sampling)
    value = os.getenv(name, "").strip()
    return float(value) if value else None


class AppConfig(BaseModel):
    consoles: Dict[str, ConsoleConfig]
    llm_base_url: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"))
    llm_api_key: str = Field(default_factory=lambda: os.getenv("LLM_API_KEY", "ollama"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen3.5:4b"))
    llm_temperature: float | None = Field(default_factory=lambda: _optional_float("LLM_TEMPERATURE"))
    llm_top_p: float | None = Field(default_factory=lambda: _optional_float("LLM_TOP_P"))
    llm_reasoning_effort: str = Field(default_factory=lambda: os.getenv("LLM_REASONING_EFFORT", "").strip())
    llm_max_tokens: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "8192")))
    llm_max_tool_loops: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOOL_LOOPS", "8")))
    llm_max_tool_chars: int = Field(default_factory=lambda: int(os.getenv("LLM_MAX_TOOL_CHARS", "12000")))
    llm_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "180")))
    llm_expose_raw_get: bool = Field(default_factory=lambda: os.getenv("LLM_EXPOSE_RAW_GET", "false").lower() == "true")
    web_host: str = Field(default_factory=lambda: os.getenv("WEB_HOST", "127.0.0.1"))
    web_port: int = Field(default_factory=lambda: int(os.getenv("WEB_PORT", "8080")))
    mcp_host: str = Field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"))
    mcp_port: int = Field(default_factory=lambda: int(os.getenv("MCP_PORT", "8000")))
    mcp_path: str = Field(default_factory=lambda: os.getenv("MCP_PATH", "/mcp"))
    mcp_bearer_token: str = Field(default_factory=lambda: os.getenv("MCP_BEARER_TOKEN", ""))
    kb4_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("KB4_TIMEOUT_SECONDS", "30")))
    kb4_max_retries: int = Field(default_factory=lambda: int(os.getenv("KB4_MAX_RETRIES", "4")))
    kb4_per_page: int = Field(default_factory=lambda: min(int(os.getenv("KB4_PER_PAGE", "500")), 500))
    kb4_max_records: int = Field(default_factory=lambda: int(os.getenv("KB4_MAX_RECORDS_PER_TOOL", "5000")))
    kb4_rate_limit_rps: float = Field(default_factory=lambda: float(os.getenv("KB4_RATE_LIMIT_RPS", "8")))
    enable_raw_get: bool = Field(default_factory=lambda: os.getenv("ENABLE_RAW_GET", "true").lower() == "true")


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or (ROOT / "config" / "consoles.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Console config not found: {config_path}. Copy config/consoles.example.yaml to config/consoles.yaml."
        )
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig(consoles=data.get("consoles", {}))
