import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


MCP_URL = "http://127.0.0.1:8000/mcp"


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

            result = await session.call_tool(
            "get_account",
            arguments={
                "console": "sis"
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