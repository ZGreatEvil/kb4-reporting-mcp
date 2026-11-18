"""container entry point: the mcp server (127.0.0.1 only) and the web chat in one container.

if either process stops, the other is stopped too and the container exits, so docker's restart policy brings both back.
"""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_WAIT_SECONDS = 60


def wait_for_port(port: int, process: subprocess.Popen, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def stop(processes: list[subprocess.Popen]) -> None:
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> int:
    processes: list[subprocess.Popen] = []

    def on_signal(signum, _frame):
        stop(processes)
        sys.exit(0)

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    mcp = subprocess.Popen([sys.executable, str(ROOT / "run_mcp.py")], cwd=ROOT)
    processes.append(mcp)
    port = int(os.getenv("MCP_PORT", "8000"))
    if not wait_for_port(port, mcp, MCP_WAIT_SECONDS):
        print(f"[start] the mcp server did not start on port {port}", flush=True)
        stop(processes)
        return 1
    processes.append(subprocess.Popen([sys.executable, str(ROOT / "run_web.py")], cwd=ROOT))

    while True:
        for p in processes:
            code = p.poll()
            if code is not None:
                name = "mcp server" if p is mcp else "web chat"
                print(f"[start] the {name} stopped (exit code {code}), stopping the container", flush=True)
                stop(processes)
                return code or 1
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
