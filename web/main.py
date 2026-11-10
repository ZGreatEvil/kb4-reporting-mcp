from __future__ import annotations

import asyncio
import json
import re
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import AsyncIterator, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agent.agent import Agent
from agent.llm import LLMError
from agent.messages import DEFAULT_LANGUAGE, Language, msg
from config.settings import PRODUCTS, load_config
from kb4_mcp.outputs import CHART_DIR, EXPORT_DIR, KEEP_SECONDS, _cleanup

try:
    VERSION = version("knowbe4-reporting-mcp")
except PackageNotFoundError:
    VERSION = "dev"

# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="KnowBe4 AI Analyst",
    version=VERSION,
)

# everything the page needs is served from here, so the policy can stay strict
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


# =========================================================
# CONFIG
# =========================================================

CONFIG = load_config()

# charts and csv files from an earlier run that are over an hour old
for _folder in (CHART_DIR, EXPORT_DIR):
    if _folder.is_dir():
        _cleanup(_folder)

# only answer to our own host names, so a dns-rebinding web page cannot read KnowBe4 data through the browser
ALLOWED_HOSTS = sorted({"127.0.0.1", "localhost", *CONFIG.web_allowed_hosts} | ({CONFIG.web_host} - {"0.0.0.0", "::"}))
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

AGENT = Agent(CONFIG)

# below this the system prompt, tool list and one tool result no longer fit (ollama's default is 4096)
MIN_CONTEXT = 16384
# limits on what one request may carry; the page enforces the same
MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_CHARS = 20000


# =========================================================
# HTML
# =========================================================

HTML_PATH = (
    Path(__file__).parent
    / "static"
    / "index.html"
)

HTML = HTML_PATH.read_text(
    encoding="utf-8"
)

# =========================================================
# CSV EXPORTS
# =========================================================

@app.get("/exports/{file_id}.csv")
async def download_export(
    file_id: str,
    name: str = "export.csv",
):

    # ids are uuid hex written by kb4_mcp.outputs; anything else could reach outside the folder
    if not re.fullmatch(r"[0-9a-f]{32}", file_id):
        raise HTTPException(status_code=404)

    path = EXPORT_DIR / f"{file_id}.csv"

    if not path.is_file():
        raise HTTPException(status_code=404)

    # links expire after an hour even when no newer export has triggered the cleanup
    if time.time() - path.stat().st_mtime > KEEP_SECONDS:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=404)

    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:120] or "export.csv"

    return FileResponse(
        path,
        media_type="text/csv",
        filename=safe_name if safe_name.endswith(".csv") else safe_name + ".csv",
        # personal data: never keep a copy in a shared cache
        headers={"Cache-Control": "no-store"},
    )


@app.get("/static/charts/{file_id}.png")
async def chart_image(file_id: str):

    # before the static mount: charts can show names, so they expire like csv files
    path = CHART_DIR / f"{file_id}.png"
    if not re.fullmatch(r"[0-9a-f]{32}", file_id) or not path.is_file():
        raise HTTPException(status_code=404)
    if time.time() - path.stat().st_mtime > KEEP_SECONDS:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})


# app.css, app.js and the vendored libraries (built from tailwind.input.css)
app.mount(
    "/static",
    StaticFiles(directory=HTML_PATH.parent),
    name="static",
)


# =========================================================
# REQUEST MODEL
# =========================================================

class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_HISTORY_CHARS)


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
    # earlier turns of this conversation (the page keeps them; nothing is stored server-side)
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)
    # anything other than "id" or "en" is rejected with 422
    language: Language = DEFAULT_LANGUAGE


# =========================================================
# HOME
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
async def index():

    return HTMLResponse(
        HTML
    )


# =========================================================
# HEALTH
# =========================================================

def _same_model(name: str, wanted: str) -> bool:
    # ollama lists "kb4-analyst:latest" for "kb4-analyst"
    return name == wanted or name == f"{wanted}:latest"


async def _mcp_tools() -> list[str]:
    async with asyncio.timeout(5):
        async with AGENT._mcp_session() as session:
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools]


async def _loaded_context() -> int | None:
    """context of the model while ollama has it loaded; None when it is not loaded or the server is not ollama"""
    base = CONFIG.llm_base_url.rstrip("/").removesuffix("/v1")
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{base}/api/ps")
            response.raise_for_status()
            running = response.json().get("models") or []
    except (httpx.HTTPError, ValueError):
        return None
    for model in running:
        if _same_model(str(model.get("name", "")), CONFIG.llm_model):
            return model.get("context_length")
    return None


@app.get("/health")
async def health():

    warnings = []

    try:
        models = await AGENT.llm.list_models()
        llm = {
            "reachable": True,
            "model_pulled": any(_same_model(m, CONFIG.llm_model) for m in models),
        }
        if not llm["model_pulled"]:
            warnings.append(f"model {CONFIG.llm_model} not found on the LLM server (README step 3)")
    except Exception as exc:  # any failure here means "not reachable"
        llm = {
            "reachable": False,
            "error_type": type(exc).__name__,
        }
        warnings.append("LLM server not reachable")

    context = await _loaded_context() if llm.get("model_pulled") else None
    llm["loaded_context"] = context
    if context is not None and context < MIN_CONTEXT:
        warnings.append(f"model loaded with a {context}-token context; it needs at least {MIN_CONTEXT} (README step 3)")

    if not any(c.has_api_key for c in CONFIG.consoles.values()):
        warnings.append("no console in config/consoles.yaml has an API key in .env")

    try:
        mcp = {"reachable": True, "tool_count": len(await _mcp_tools())}
    except Exception as exc:  # any failure here means "not reachable"
        mcp = {"reachable": False, "error_type": type(exc).__name__}
        warnings.append("MCP server not reachable")

    return {
        "status": "ok" if not warnings else "degraded",
        "service": "knowbe4-ai-web",
        "version": VERSION,
        "mcp_url": AGENT.mcp_url,
        "llm_base_url": CONFIG.llm_base_url,
        "llm_model": CONFIG.llm_model,
        "llm": llm,
        "mcp": mcp,
        "warnings": warnings,
        "consoles": list(
            CONFIG.consoles.keys()
        ),
        # which optional product api keys each console has (names only, no request)
        "product_apis": {
            key: [p for p in PRODUCTS if console.product_key(p)]
            for key, console in CONFIG.consoles.items()
        },
    }


# =========================================================
# MCP HEALTH
# =========================================================

@app.get("/health/mcp")
async def health_mcp():

    try:

        tools = await _mcp_tools()

        return {
            "status": "ok",
            "mcp_url": AGENT.mcp_url,
            "tool_count": len(tools),
            "tools": tools,
        }

    except Exception as exc:  # reported, not raised: this endpoint exists to say what is wrong

        print(
            f"[MCP HEALTH] {type(exc).__name__}",
            flush=True,
        )

        return {
            "status": "error",
            "mcp_url": AGENT.mcp_url,
            "error_type": (
                type(exc).__name__
            ),
        }


# =========================================================
# CHAT
# =========================================================

@app.post("/api/chat")
async def chat(
    req: ChatRequest,
):

    message = req.message.strip()
    language = req.language

    if not message:

        return {
            "answer":
            msg("empty_question", language)
        }

    try:

        # the note goes back with the history, so "2" and "lanjut" work here as they do on the page
        return await AGENT.ask_with_note(
            message,
            language,
            [h.model_dump() for h in req.history],
        )

    except LLMError as exc:

        print(
            f"[CHAT LLM ERROR] {exc.key}",
            flush=True,
        )

        return {
            "answer": exc.text(language),
            "error_type": "LLMError",
        }

    except BaseExceptionGroup as exc:

        print(
            "\n[CHAT EXCEPTION GROUP]",
            flush=True,
        )

        for index, error in enumerate(
            exc.exceptions,
            start=1,
        ):

            print(
                f"[CHAT SUBERROR {index}] "
                f"{type(error).__name__}",
                flush=True,
            )

        return {
            "answer": msg("mcp_transport", language),
            "error_type": "ExceptionGroup",
        }

    except Exception as exc:  # the user gets a readable message, the log gets the type

        print(
            f"[CHAT ERROR] {type(exc).__name__}",
            flush=True,
        )

        return {
            "answer": msg("pipeline_error", language),
            "error_type": (
                type(exc).__name__
            ),
        }

# =========================================================
# CHAT (STREAMING)
# =========================================================

def _ndjson(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


@app.post("/api/chat/stream")
async def chat_stream(
    req: ChatRequest,
):
    # one json event per line: thinking, tool, delta, reset, done or error
    language = req.language

    async def events() -> AsyncIterator[str]:

        try:

            async for event in AGENT.ask_stream(
                req.message,
                language,
                [h.model_dump() for h in req.history],
            ):
                yield _ndjson(event)

        except LLMError as exc:

            print(
                f"[CHAT LLM ERROR] {exc.key}",
                flush=True,
            )

            yield _ndjson({"type": "error", "message": exc.text(language)})

        except BaseExceptionGroup as exc:

            for index, error in enumerate(
                exc.exceptions,
                start=1,
            ):

                print(
                    f"[CHAT SUBERROR {index}] "
                    f"{type(error).__name__}",
                    flush=True,
                )

            yield _ndjson({"type": "error", "message": msg("mcp_transport", language)})

        except Exception as exc:  # the user gets a readable message, the log gets the type

            print(
                f"[CHAT STREAM ERROR] {type(exc).__name__}",
                flush=True,
            )

            yield _ndjson({"type": "error", "message": msg("pipeline_error", language)})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        # stop proxies and the browser from holding chunks back
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
