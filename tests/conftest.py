import pytest


@pytest.fixture(autouse=True)
def isolated_kb4_usage(monkeypatch, tmp_path):
    # keep tests away from the real request counter, and skip the automatic limit lookup
    monkeypatch.setenv("KB4_USAGE_FILE", str(tmp_path / "usage.json"))
    monkeypatch.setenv("KB4_DAILY_LIMIT", "100000")
