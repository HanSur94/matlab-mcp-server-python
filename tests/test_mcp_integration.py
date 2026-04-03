"""End-to-end MCP integration test for the MATLAB MCP server.

Starts the server as a subprocess in --inspect mode (no MATLAB required),
connects a real MCP client via streamable HTTP with bearer auth, calls
tools/list, and verifies known tool names appear in the response.

Run with:
    pytest tests/test_mcp_integration.py -v -m integration
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from typing import Any

import httpx
import pytest

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SERVER_HOST = "127.0.0.1"
_SERVER_PORT = 8765
_AUTH_TOKEN = "test-token-for-ci"
_HEALTH_URL = f"http://{_SERVER_HOST}:{_SERVER_PORT}/health"
_MCP_URL = f"http://{_SERVER_HOST}:{_SERVER_PORT}/mcp"
_STARTUP_TIMEOUT_S = 15.0
_POLL_INTERVAL_S = 0.5
_TEARDOWN_TIMEOUT_S = 5.0

# Known tools that must appear in the tool listing for the test to pass
_EXPECTED_TOOLS = {
    "execute_code",
    "get_workspace",
    "list_toolboxes",
    "get_pool_status",
}


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_server_process() -> Any:
    """Start the MCP server subprocess in --inspect mode and yield it.

    Uses MATLAB_MCP_AUTH_TOKEN and MATLAB_MCP_POOL_MIN_ENGINES env vars to
    configure bearer auth and skip engine pool startup. Tears down the process
    after the test module finishes.
    """
    env = os.environ.copy()
    env["MATLAB_MCP_AUTH_TOKEN"] = _AUTH_TOKEN
    env["MATLAB_MCP_POOL_MIN_ENGINES"] = "0"

    cmd = [
        sys.executable,
        "-c",
        "from matlab_mcp.server import main; main()",
        "--inspect",
        "--transport",
        "streamablehttp",
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Poll /health until server is ready or timeout expires
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    ready = False
    while time.monotonic() < deadline:
        try:
            response = httpx.get(_HEALTH_URL, timeout=2.0)
            if response.status_code < 500:
                ready = True
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            pass
        # Check if process already died
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"Server process exited early with code {proc.returncode}.\n"
                f"stderr: {stderr.decode(errors='replace')}"
            )
        time.sleep(_POLL_INTERVAL_S)

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=_TEARDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
        _, stderr = proc.communicate()
        raise RuntimeError(
            f"Server did not become ready within {_STARTUP_TIMEOUT_S}s.\n"
            f"stderr: {stderr.decode(errors='replace')}"
        )

    yield proc

    # Teardown: send SIGTERM, wait, then SIGKILL if needed
    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=_TEARDOWN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mcp_tools_list_via_streamable_http(mcp_server_process: Any) -> None:
    """Connect to the MCP server, list tools, and verify known tools appear.

    Uses the official mcp.client.streamable_http transport which handles SSE
    framing automatically. Authenticates with the test bearer token.
    """
    headers = {"Authorization": f"Bearer {_AUTH_TOKEN}"}
    http_client = httpx.AsyncClient(headers=headers)

    async with streamable_http_client(_MCP_URL, http_client=http_client) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool_names = {tool.name for tool in result.tools}

    missing = _EXPECTED_TOOLS - tool_names
    assert not missing, (
        f"Expected tools missing from tools/list response: {missing}.\n"
        f"Got: {sorted(tool_names)}"
    )
