import sys

import uvicorn

from config.settings import SettingsError, load_config

if __name__ == "__main__":
    # a windows console (cp1252) cannot print every character; a log line must never stop the server
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="backslashreplace")
    # settings mistakes are shown as a short list, not a traceback
    try:
        cfg = load_config()
        from web.main import app
    except (SettingsError, FileNotFoundError) as exc:
        sys.exit(str(exc))
    uvicorn.run(app, host=cfg.web_host, port=cfg.web_port)
