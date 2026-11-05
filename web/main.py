from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent.agent import Agent
from agent.llm import LLMError
from agent.messages import DEFAULT_LANGUAGE, Language, msg
from config.settings import load_config


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="KnowBe4 AI Analyst",
    version="1.0.0",
)


# =========================================================
# CONFIG
# =========================================================

CONFIG = load_config()

AGENT = Agent(CONFIG)


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

@app.get("/health")
async def health():

    try:
        models = await AGENT.llm.list_models()
        llm = {
            "reachable": True,
            "model_pulled": CONFIG.llm_model in models,
        }
    except Exception as exc:
        llm = {
            "reachable": False,
            "error_type": type(exc).__name__,
        }

    return {
        "status": "ok" if llm.get("model_pulled") else "degraded",
        "service": "knowbe4-ai-web",
        "mcp_url": AGENT.mcp_url,
        "llm_base_url": CONFIG.llm_base_url,
        "llm_model": CONFIG.llm_model,
        "llm": llm,
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
    language = req.language

    if not message:

        return {
            "answer":
            msg("empty_question", language)
        }

    try:

        answer = await AGENT.ask(
            message,
            language,
        )

        return {
            "answer": answer,
        }

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
                f"{type(error).__name__}: {error}",
                flush=True,
            )

        return {
            "answer": msg("mcp_transport", language),
            "error_type": "ExceptionGroup",
        }

    except Exception as exc:

        import traceback

        traceback.print_exc()

        return {
            "answer": msg("pipeline_error", language),
            "error_type": (
                type(exc).__name__
            ),
        }