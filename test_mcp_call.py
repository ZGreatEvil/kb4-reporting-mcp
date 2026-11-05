import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from config.settings import load_config


CONFIG = load_config()
MCP_URL = f"http://{CONFIG.mcp_host}:{CONFIG.mcp_port}{CONFIG.mcp_path}"
# first console that has an api key
CONSOLE = next((k for k, c in CONFIG.consoles.items() if c.has_api_key), None)


async def main():
    print(f"Connecting to {MCP_URL}")

    async with streamable_http_client(MCP_URL) as (
        read_stream,
        write_stream,
    ):
        print("Transport connected")

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            print("Initializing MCP session...")
            await session.initialize()

            print("MCP initialized")

            tools = await session.list_tools()

            print("\nTOOLS:")
            for tool in tools.tools:
                print(
                    f"- {tool.name}"
                )

            if CONSOLE is None:
                print("\nNo console has an API key; skipping get_account.")
                return

            result = await session.call_tool(
            "get_account",
            arguments={
                "console": CONSOLE
                    },
                )

            print("\nRESULT:")
            print(
                json.dumps(
                    result.model_dump(),
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())