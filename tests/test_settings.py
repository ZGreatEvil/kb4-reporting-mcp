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
        ConsoleConfig(display_name="X", api_key_env="KB4_TEST_KEY").api_key


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
