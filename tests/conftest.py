import os
from pathlib import Path

import pytest

# set before any test module imports the web app.
# fastapi's test client sends "Host: testserver"
os.environ["WEB_ALLOWED_HOSTS"] = "testserver"
# tests run on the committed example consoles, so a fresh clone (no config/consoles.yaml) can run them
# and a local setup cannot change the results
os.environ["KB4_CONSOLES_FILE"] = str(Path(__file__).resolve().parents[1] / "config" / "consoles.example.yaml")


@pytest.fixture(autouse=True)
def isolated_kb4_usage(monkeypatch, tmp_path):
    # keep tests away from the real request counter, and skip the automatic limit lookup
    monkeypatch.setenv("KB4_USAGE_FILE", str(tmp_path / "usage.json"))
    monkeypatch.setenv("KB4_DAILY_LIMIT", "100000")
