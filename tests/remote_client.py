"""Standalone remote MCP integration client.

Connects to a running MCP server over HTTP with bearer auth, lists available
tools, and verifies the expected tool set is present.

Usage (standalone):
    MCP_SERVER_URL=http://server:8765/mcp MCP_AUTH_TOKEN=<token> python remote_client.py

Exit codes:
    0 - All expected tools found, server reachable
    1 - Connection failed or expected tools missing
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXPECTED_TOOLS = {"execute_code", "get_workspace", "list_toolboxes", "get_pool_status"}
_RETRY_TIMEOUT_S = 30.0
_RETRY_INTERVAL_S = 2.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run() -> int:
    """Connect to MCP server, list tools, and return 0 on success or 1 on failure."""
    server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8765/mcp")
    auth_token = os.environ.get("MCP_AUTH_TOKEN", "")

    if not auth_token:
        print("ERROR: MCP_AUTH_TOKEN environment variable is not set.")
        return 1

    headers = {"Authorization": f"Bearer {auth_token}"}
    http_client = httpx.AsyncClient(headers=headers)

    deadline = time.monotonic() + _RETRY_TIMEOUT_S
    last_error: str = ""

    while time.monotonic() < deadline:
        try:
            async with streamable_http_client(server_url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()

            tool_names = {tool.name for tool in result.tools}
            missing = _EXPECTED_TOOLS - tool_names

            if missing:
                print(f"FAILURE: Expected tools missing from tools/list: {sorted(missing)}")
                print(f"  Got: {sorted(tool_names)}")
                return 1

            print("SUCCESS: All expected MCP tools found.")
            print(f"  Tools: {sorted(tool_names)}")
            return 0

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                print(f"Connection attempt failed: {exc}. Retrying in {_RETRY_INTERVAL_S}s ...")
                await asyncio.sleep(_RETRY_INTERVAL_S)
            else:
                break

    print(f"FAILURE: Could not connect to {server_url} within {_RETRY_TIMEOUT_S}s.")
    print(f"  Last error: {last_error}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
