from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config.settings import load_config
from gemini.agent import GeminiAgent


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="KnowBe4 Gemini AI Analyst",
    version="1.0.0",
)


# =========================================================
# CONFIG
# =========================================================

CONFIG = load_config()

AGENT = GeminiAgent(CONFIG)


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
# REQUEST MODEL
# =========================================================

class ChatRequest(BaseModel):
    message: str


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

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": "knowbe4-gemini-web",
        "mcp_url": AGENT.mcp_url,
        "gemini_model": CONFIG.gemini_model,
        "consoles": list(
            CONFIG.consoles.keys()
        ),
    }


# =========================================================
# ROUTE DEBUG
# =========================================================

@app.get("/health/routes")
async def health_routes():

    return {
        "routes": [
            {
                "path": route.path,
                "methods": sorted(
                    route.methods or []
                ),
            }
            for route in app.routes
        ]
    }


# =========================================================
# MCP HEALTH
# =========================================================

@app.get("/health/mcp")
async def health_mcp():

    try:

        from mcp import ClientSession
        from mcp.client.streamable_http import (
            streamable_http_client,
        )

        # IMPORTANT:
        # Your installed MCP SDK returns 2 values.
        async with streamable_http_client(
            AGENT.mcp_url
        ) as (
            read_stream,
            write_stream,
        ):

            async with ClientSession(
                read_stream,
                write_stream,
            ) as session:

                await session.initialize()

                tools = (
                    await session.list_tools()
                )

                return {
                    "status": "ok",
                    "mcp_url": AGENT.mcp_url,
                    "tool_count": len(
                        tools.tools
                    ),
                    "tools": [
                        tool.name
                        for tool in tools.tools
                    ],
                }

    except Exception as exc:

        import traceback

        traceback.print_exc()

        return {
            "status": "error",
            "mcp_url": AGENT.mcp_url,
            "error_type": (
                type(exc).__name__
            ),
            "error": str(exc),
        }


# =========================================================
# CHAT
# =========================================================

@app.post("/api/chat")
async def chat(
    req: ChatRequest,
):

    message = req.message.strip()

    if not message:

        return {
            "answer":
            "Masukkan pertanyaan terlebih dahulu."
        }

    try:

        answer = await AGENT.ask(
            message
        )

        return {
            "answer": answer,
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
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        return {
            "answer": (
                "MCP mengalami error "
                "pada transport."
            ),
            "error_type": "ExceptionGroup",
        }

    except Exception as exc:

        import traceback

        traceback.print_exc()

        return {
            "answer": (
                "Terjadi error pada "
                "Gemini → MCP → KnowBe4."
            ),
            "error_type": (
                type(exc).__name__
            ),
        }