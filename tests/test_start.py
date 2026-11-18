import importlib.util
import socket
import subprocess
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("start", Path(__file__).resolve().parents[1] / "docker" / "start.py")
start = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start)
REAL_POPEN = subprocess.Popen


def test_waiting_stops_when_the_process_has_already_exited():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert start.wait_for_port(1, p, 5) is False


def test_waiting_sees_an_open_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            assert start.wait_for_port(s.getsockname()[1], p, 5) is True
        finally:
            start.stop([p])
    assert p.poll() is not None


def test_the_container_exits_when_the_mcp_server_never_starts(monkeypatch):
    # an mcp server that dies at start-up must not leave the web chat running without it
    started = []

    def fake_popen(args, cwd=None):
        started.append(args[-1])
        return REAL_POPEN([sys.executable, "-c", "raise SystemExit(3)"])

    monkeypatch.setattr(start.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(start.signal, "signal", lambda *a: None)
    assert start.main() == 1
    assert len(started) == 1 and started[0].endswith("run_mcp.py")


def test_the_container_exits_when_the_web_chat_stops(monkeypatch):
    calls = []

    def fake_popen(args, cwd=None):
        calls.append(args[-1])
        code = "import time; time.sleep(30)" if args[-1].endswith("run_mcp.py") else "raise SystemExit(2)"
        return REAL_POPEN([sys.executable, "-c", code])

    monkeypatch.setattr(start.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(start.signal, "signal", lambda *a: None)
    monkeypatch.setattr(start, "wait_for_port", lambda port, process, seconds: True)
    assert start.main() == 2
    assert [Path(c).name for c in calls] == ["run_mcp.py", "run_web.py"]
