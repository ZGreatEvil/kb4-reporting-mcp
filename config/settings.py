from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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


class SettingsError(ValueError):
    """a mistake in .env or consoles.yaml, worded for whoever runs the app"""


def _number(name: str, default: str, cast: type) -> Any:
    raw = os.getenv(name, "").strip() or default
    try:
        return cast(raw)
    except ValueError:
        kind = "a whole number" if cast is int else "a number"
        raise SettingsError(f"{name}={raw!r} in .env must be {kind}.") from None


def _optional_float(name: str) -> float | None:
    # unset means "use the model's own default" (ollama ships qwen's recommended sampling)
    return _number(name, "", float) if os.getenv(name, "").strip() else None


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() == "true"


# .env names of fields whose name is not simply the upper-cased field name
ENV_NAMES = {"kb4_max_records": "KB4_MAX_RECORDS_PER_TOOL"}


class AppConfig(BaseModel):
    # defaults come from .env, so they are checked against the ranges too
    model_config = ConfigDict(validate_default=True)

    consoles: Dict[str, ConsoleConfig]
    llm_base_url: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"), min_length=1)
    llm_api_key: str = Field(default_factory=lambda: os.getenv("LLM_API_KEY", "ollama"))
    llm_model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "kb4-analyst"), min_length=1)
    llm_temperature: float | None = Field(default_factory=lambda: _optional_float("LLM_TEMPERATURE"), ge=0, le=2)
    llm_top_p: float | None = Field(default_factory=lambda: _optional_float("LLM_TOP_P"), gt=0, le=1)
    llm_presence_penalty: float | None = Field(default_factory=lambda: _optional_float("LLM_PRESENCE_PENALTY"), ge=-2, le=2)
    llm_reasoning_effort: str = Field(default_factory=lambda: os.getenv("LLM_REASONING_EFFORT", "").strip())
    llm_max_tokens: int = Field(default_factory=lambda: _number("LLM_MAX_TOKENS", "8192", int), ge=256)
    llm_max_tool_loops: int = Field(default_factory=lambda: _number("LLM_MAX_TOOL_LOOPS", "8", int), ge=1, le=30)
    llm_max_tool_chars: int = Field(default_factory=lambda: _number("LLM_MAX_TOOL_CHARS", "12000", int), ge=2000)
    llm_timeout_seconds: float = Field(default_factory=lambda: _number("LLM_TIMEOUT_SECONDS", "180", float), gt=0)
    llm_expose_raw_get: bool = Field(default_factory=lambda: _flag("LLM_EXPOSE_RAW_GET", "false"))
    # raw user lists and full risk histories; the summary tools cover them in a few lines
    llm_expose_raw_lists: bool = Field(default_factory=lambda: _flag("LLM_EXPOSE_RAW_LISTS", "false"))
    # earlier messages sent along with each question, so follow-ups like "2" or "show more" work
    llm_history_messages: int = Field(default_factory=lambda: _number("LLM_HISTORY_MESSAGES", "6", int), ge=0, le=20)
    web_host: str = Field(default_factory=lambda: os.getenv("WEB_HOST", "127.0.0.1"), min_length=1)
    web_port: int = Field(default_factory=lambda: _number("WEB_PORT", "8080", int), ge=1, le=65535)
    # extra host names the web chat answers to (comma-separated); 127.0.0.1 and localhost always work
    web_allowed_hosts: list[str] = Field(
        default_factory=lambda: [h.strip().lower() for h in os.getenv("WEB_ALLOWED_HOSTS", "").split(",") if h.strip()]
    )
    mcp_host: str = Field(default_factory=lambda: os.getenv("MCP_HOST", "127.0.0.1"), min_length=1)
    mcp_port: int = Field(default_factory=lambda: _number("MCP_PORT", "8000", int), ge=1, le=65535)
    mcp_path: str = Field(default_factory=lambda: os.getenv("MCP_PATH", "/mcp"), pattern=r"^/")
    kb4_timeout_seconds: float = Field(default_factory=lambda: _number("KB4_TIMEOUT_SECONDS", "30", float), gt=0)
    kb4_max_retries: int = Field(default_factory=lambda: _number("KB4_MAX_RETRIES", "4", int), ge=0, le=10)
    # knowbe4 allows at most 500 per page
    kb4_per_page: int = Field(default_factory=lambda: _number("KB4_PER_PAGE", "500", int), ge=1, le=500)
    kb4_max_records: int = Field(default_factory=lambda: _number("KB4_MAX_RECORDS_PER_TOOL", "5000", int), ge=1)
    # knowbe4 documents 4 requests a second at most
    kb4_rate_limit_rps: float = Field(default_factory=lambda: _number("KB4_RATE_LIMIT_RPS", "0.8", float), gt=0, le=4)
    # successful KnowBe4 responses are reused for this long; 0 turns the cache off
    kb4_cache_seconds: float = Field(default_factory=lambda: _number("KB4_CACHE_SECONDS", "600", float), ge=0)
    # requests per console per rolling 24 h; unset = 2,000 + the account's licensed seats (KnowBe4's documented limit)
    kb4_daily_limit: int | None = Field(
        default_factory=lambda: _number("KB4_DAILY_LIMIT", "", int) if os.getenv("KB4_DAILY_LIMIT", "").strip() else None, ge=1
    )
    kb4_usage_file: Path = Field(default_factory=lambda: Path(os.getenv("KB4_USAGE_FILE", "") or ROOT / ".kb4_usage.json"))
    enable_raw_get: bool = Field(default_factory=lambda: _flag("ENABLE_RAW_GET", "true"))


def _where(loc: tuple[Any, ...]) -> str:
    if loc and loc[0] == "consoles":
        inner = ".".join(str(p) for p in loc[1:])
        return "config/consoles.yaml, consoles" + (f": {inner}" if inner else "")
    field = str(loc[0]) if loc else "?"
    return f"{ENV_NAMES.get(field, field.upper())} in .env"


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.getenv("KB4_CONSOLES_FILE", "").strip() or (ROOT / "config" / "consoles.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Console config not found: {config_path}. Copy config/consoles.example.yaml to config/consoles.yaml."
        )
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = f" (line {mark.line + 1})" if mark else ""
        raise SettingsError(f"{config_path.name} is not valid YAML{line}. Compare it with config/consoles.example.yaml.") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{config_path.name} must start with 'consoles:'. Compare it with config/consoles.example.yaml.")
    try:
        return AppConfig(consoles=data.get("consoles") or {})
    except ValidationError as exc:
        problems = "\n".join(f"- {_where(e['loc'])}: {e['msg']}" for e in exc.errors())
        raise SettingsError(f"Invalid settings:\n{problems}") from None
