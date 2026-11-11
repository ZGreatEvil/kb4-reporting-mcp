from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import AppConfig, ConsoleConfig, load_config


def test_env_example_exists():
    assert Path(".env.example").exists()


def test_console_example_exists():
    assert Path("config/consoles.example.yaml").exists()


def test_console_example_loads():
    cfg = load_config("config/consoles.example.yaml")
    assert cfg.consoles


def test_base_url_key_is_rejected():
    with pytest.raises(ValidationError):
        ConsoleConfig(display_name="X", base_url="https://us.api.knowbe4.com", api_key_env="KB4_X")


def test_unknown_region_is_rejected():
    with pytest.raises(ValidationError):
        ConsoleConfig(display_name="X", region="mars", api_key_env="KB4_X")


def test_region_sets_base_url():
    assert ConsoleConfig(display_name="X", region="EU", api_key_env="KB4_X").base_url == "https://eu.api.knowbe4.com"


@pytest.mark.parametrize("value,expected", [
    ("", False),
    ("   ", False),
    ("xxxxxxxxxxxx", False),
    ("your-reporting-api-key", False),
    ("...", False),
    ("eyJreal.token.value", True),
])
def test_has_api_key(monkeypatch, value, expected):
    monkeypatch.setenv("KB4_TEST_KEY", value)
    console = ConsoleConfig(display_name="X", api_key_env="KB4_TEST_KEY")
    assert console.has_api_key is expected


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("KB4_TEST_KEY", raising=False)
    with pytest.raises(RuntimeError):
        _ = ConsoleConfig(display_name="X", api_key_env="KB4_TEST_KEY").api_key


def test_prompt_lists_consoles_from_config(monkeypatch):
    from agent.agent import build_system_prompt

    monkeypatch.setenv("KB4_A_KEY", "real-token")
    monkeypatch.delenv("KB4_B_KEY", raising=False)
    cfg = AppConfig(consoles={
        "a": ConsoleConfig(display_name="Alpha", api_key_env="KB4_A_KEY"),
        "b": ConsoleConfig(display_name="Beta", api_key_env="KB4_B_KEY"),
    })
    prompt = build_system_prompt(cfg)
    assert "- a : Alpha\n" in prompt
    assert "- b : Beta (UNAVAILABLE" in prompt
    assert 'console ids: "a".' in prompt
    assert 'default to console="a"' in prompt


def test_prompt_with_no_keys(monkeypatch):
    from agent.agent import build_system_prompt

    monkeypatch.delenv("KB4_B_KEY", raising=False)
    cfg = AppConfig(consoles={"b": ConsoleConfig(display_name="Beta", api_key_env="KB4_B_KEY")})
    assert "No console has an API key" in build_system_prompt(cfg)


@pytest.mark.parametrize("name,value,expected", [
    ("KB4_RATE_LIMIT_RPS", "abc", "KB4_RATE_LIMIT_RPS='abc' in .env must be a number"),
    ("WEB_PORT", "eighty", "WEB_PORT='eighty' in .env must be a whole number"),
    ("KB4_RATE_LIMIT_RPS", "0", "KB4_RATE_LIMIT_RPS in .env"),
    ("KB4_RATE_LIMIT_RPS", "5", "KB4_RATE_LIMIT_RPS in .env"),
    ("LLM_MAX_TOOL_LOOPS", "0", "LLM_MAX_TOOL_LOOPS in .env"),
    ("WEB_PORT", "70000", "WEB_PORT in .env"),
    ("KB4_CACHE_SECONDS", "-5", "KB4_CACHE_SECONDS in .env"),
    ("KB4_MAX_RECORDS_PER_TOOL", "0", "KB4_MAX_RECORDS_PER_TOOL in .env"),
    ("KB4_PER_PAGE", "501", "KB4_PER_PAGE in .env"),
    ("LLM_TOP_P", "1.5", "LLM_TOP_P in .env"),
    ("MCP_PATH", "mcp", "MCP_PATH in .env"),
    ("KB4_DAILY_LIMIT", "0", "KB4_DAILY_LIMIT in .env"),
])
def test_bad_env_values_name_the_setting(monkeypatch, name, value, expected):
    from config.settings import SettingsError

    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError, match=expected.replace(".", r"\.").replace("'", "'")):
        load_config("config/consoles.example.yaml")


@pytest.mark.parametrize("text,expected", [
    ("consoles: [\n", "not valid YAML (line 2)"),
    ("- a\n- b\n", "must start with 'consoles:'"),
    ("consoles:\n  a:\n    display_name: A\n    region: mars\n    api_key_env: K\n", "consoles: a.region"),
    ("consoles:\n  a:\n    display_name: A\n    base_url: x\n    api_key_env: K\n", "consoles: a.base_url"),
    ("consoles:\n  a:\n    region: us\n", "consoles: a.display_name"),
    ("consoles:\n  - a\n", "config/consoles.yaml, consoles: Input should be a valid dictionary"),
    # found in the 2026-11-12 audit: these loaded as zero consoles and the server started
    ("main:\n  display_name: A\n  api_key_env: K\n", "unknown top-level entries: main"),
    ("console:\n  a:\n    display_name: A\n    api_key_env: K\n", "unknown top-level entries: console"),
    ("consoles:\n", "lists no consoles"),
    ("", "lists no consoles"),
])
def test_bad_consoles_file_is_explained(tmp_path, text, expected):
    from config.settings import SettingsError

    f = tmp_path / "consoles.yaml"
    f.write_text(text, encoding="utf-8")
    with pytest.raises(SettingsError) as info:
        load_config(f)
    assert expected in str(info.value)


