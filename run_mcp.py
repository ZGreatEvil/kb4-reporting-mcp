import sys

from config.settings import SettingsError, load_config

if __name__ == "__main__":
    # a windows console (cp1252) cannot print every character; a log line must never stop the server
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    # settings mistakes are shown as a short list, not a traceback
    try:
        load_config()
        from kb4_mcp.server_impl import run_mcp
    except (SettingsError, FileNotFoundError) as exc:
        sys.exit(str(exc))
    run_mcp()
