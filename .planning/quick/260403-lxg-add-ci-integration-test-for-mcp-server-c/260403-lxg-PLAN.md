---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_mcp_integration.py
  - .github/workflows/ci.yml
autonomous: true
must_haves:
  truths:
    - "CI runs an end-to-end MCP integration test on every push/PR"
    - "Server starts in --inspect mode (no MATLAB needed) with streamable HTTP transport and bearer auth"
    - "A separate Python MCP client connects via streamable HTTP, authenticates, and lists tools"
    - "Test verifies at least one known tool name appears in the tool list"
    - "Server shuts down cleanly after test completes"
  artifacts:
    - path: "tests/test_mcp_integration.py"
      provides: "Integration test script that starts server, connects client, verifies tools"
    - path: ".github/workflows/ci.yml"
      provides: "New integration-test job in CI workflow"
  key_links:
    - from: "tests/test_mcp_integration.py"
      to: "src/matlab_mcp/server.py"
      via: "subprocess launch with --inspect --transport streamablehttp"
      pattern: "subprocess.*--inspect.*--transport.*streamablehttp"
    - from: "tests/test_mcp_integration.py"
      to: "http://127.0.0.1:8765/mcp"
      via: "fastmcp.Client or httpx connecting with Bearer token"
      pattern: "Bearer|Authorization"
---

<objective>
Add an end-to-end CI integration test that proves a remote MCP client can connect to the MATLAB MCP server over streamable HTTP with bearer auth, list available tools, and get a valid response — all without MATLAB installed.

Purpose: Validate that the MCP server's transport layer, auth middleware, and tool registration work end-to-end in CI, catching integration regressions that unit tests miss.
Output: `tests/test_mcp_integration.py` + new `integration-test` job in `.github/workflows/ci.yml`
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/matlab_mcp/server.py (server entry point — main() with --inspect and --transport flags)
@src/matlab_mcp/auth/middleware.py (BearerAuthMiddleware — reads MATLAB_MCP_AUTH_TOKEN env var)
@src/matlab_mcp/config.py (AppConfig — default host 127.0.0.1, port 8765)
@.github/workflows/ci.yml (existing CI — add new job here)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create MCP integration test script</name>
  <files>tests/test_mcp_integration.py</files>
  <action>
Create `tests/test_mcp_integration.py` — a standalone integration test that:

1. **Starts the server as a subprocess** in background:
   - Set env vars: `MATLAB_MCP_AUTH_TOKEN=test-token-for-ci`, `MATLAB_MCP_POOL_MIN_ENGINES=0`
   - Command: `python -m matlab_mcp --inspect --transport streamablehttp`
   - Server binds to 127.0.0.1:8765 by default (from ServerConfig defaults)
   - Wait for server readiness by polling `http://127.0.0.1:8765/health` (bypasses auth per middleware) with retries (up to 15 seconds, 0.5s interval)

2. **Connect an MCP client via streamable HTTP**:
   - Use `httpx` (already available as transitive dep) to POST to `http://127.0.0.1:8765/mcp` with JSON-RPC `initialize` request and `Authorization: Bearer test-token-for-ci` header
   - Then send `tools/list` JSON-RPC request
   - Alternatively, if FastMCP Client supports streamable-http URL with headers, use `from fastmcp import Client` with `Client("http://127.0.0.1:8765/mcp")` — check if it supports auth headers. If not, fall back to raw httpx JSON-RPC calls.
   
   **Preferred approach (simpler, more reliable):** Use raw `httpx.AsyncClient` to send MCP JSON-RPC messages directly:
   - POST `{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1.0"}}}` to `/mcp` with bearer auth header
   - POST `{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}` to `/mcp`

3. **Assert** the response contains tool names. Verify at least these known tools appear: `execute_code`, `get_workspace`, `list_toolboxes`, `get_pool_status`.

4. **Teardown**: Send SIGTERM to server subprocess, wait up to 5 seconds, then SIGKILL if needed. Use pytest fixture or try/finally.

5. **Mark the test** with `@pytest.mark.integration` so it can be run/excluded separately. Also mark `@pytest.mark.asyncio`.

Important implementation notes:
- Use `subprocess.Popen` (not asyncio.create_subprocess) for the server — it's simpler and avoids event loop conflicts
- The `--inspect` flag sets `config.pool.min_engines = 0` and `config._inspect_mode = True`, which skips MATLAB engine pool startup entirely
- Also set env `MATLAB_MCP_POOL_MIN_ENGINES=0` as a safety net (env override applies before --inspect flag)
- The server logs to stderr, so capture stderr for debug output on failure
- Use `httpx` for the client side — it's a transitive dependency of FastMCP/Starlette
- Note: streamable HTTP MCP uses Server-Sent Events in the response body. The initialize request returns `Content-Type: text/event-stream`. Parse SSE events from the response to extract JSON-RPC results. Each event has format `event: message\ndata: {json}\n\n`.
- If httpx SSE parsing is complex, consider using the `mcp` library's `streamablehttp` client transport directly: `from mcp.client.streamable_http import streamablehttp_client` — this handles the SSE framing. Check if it accepts custom headers for auth.
  </action>
  <verify>
    <automated>cd /Users/hannessuhr/matlab-mcp-server-python && python -c "import ast; ast.parse(open('tests/test_mcp_integration.py').read()); print('Syntax OK')"</automated>
  </verify>
  <done>
    - tests/test_mcp_integration.py exists with pytest integration test
    - Test starts server subprocess with --inspect --transport streamablehttp
    - Test connects client with bearer auth to /mcp endpoint
    - Test asserts known tool names in tools/list response
    - Test cleans up server process in teardown
  </done>
</task>

<task type="auto">
  <name>Task 2: Add integration-test job to CI workflow</name>
  <files>.github/workflows/ci.yml</files>
  <action>
Add a new `integration-test` job to `.github/workflows/ci.yml`:

```yaml
  integration-test:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev,monitoring]"
      - run: pytest tests/test_mcp_integration.py -v -m integration --timeout=60
```

Place this job after the `test-macos` job block (before `docker`).

Key details:
- `needs: lint` — same dependency as other test jobs, runs in parallel with `test`, `security`, etc.
- Uses Python 3.12 only (single version, this is an integration smoke test not a matrix)
- Installs with `[dev,monitoring]` extras (same as the main `test` job)
- Uses `-m integration` marker to select only integration tests
- Adds `--timeout=60` to prevent hangs if server doesn't start (requires pytest-timeout; if not in dev deps, use `-x --tb=short` instead and rely on the test's own 15-second startup timeout)
- No MATLAB needed — `--inspect` mode in the test handles that

Also add `pytest-timeout` to dev dependencies in pyproject.toml if it's not already there. Check first:
```bash
grep pytest-timeout pyproject.toml
```
If missing, do NOT add it — instead remove `--timeout=60` from the pytest command and rely on the test's internal timeouts. Keep CI changes minimal.

Register the `integration` marker in `pyproject.toml` under `[tool.pytest.ini_options]` to avoid warnings:
```
markers = ["integration: end-to-end MCP server integration tests"]
```
Check if markers config already exists; if so, append to it.
  </action>
  <verify>
    <automated>cd /Users/hannessuhr/matlab-mcp-server-python && python -c "import yaml; y=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'integration-test' in y['jobs'], 'job missing'; print('CI job exists')"</automated>
  </verify>
  <done>
    - .github/workflows/ci.yml has integration-test job
    - Job installs deps, runs pytest with -m integration marker
    - Job runs on ubuntu-latest with Python 3.12
    - integration marker registered in pyproject.toml (no pytest warning)
  </done>
</task>

</tasks>

<verification>
1. `python -c "import ast; ast.parse(open('tests/test_mcp_integration.py').read())"` — test file is valid Python
2. `python -c "import yaml; y=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'integration-test' in y['jobs']"` — CI job exists
3. `pytest tests/test_mcp_integration.py -v -m integration` — integration test passes locally (server starts in inspect mode, client connects, tools listed, server shuts down)
</verification>

<success_criteria>
- Integration test passes: server starts, client connects via streamable HTTP with bearer auth, tools/list returns known tool names, server shuts down cleanly
- CI workflow has integration-test job that will run on every push/PR
- No MATLAB installation required (--inspect mode)
</success_criteria>

<output>
After completion, create `.planning/quick/260403-lxg-add-ci-integration-test-for-mcp-server-c/260403-lxg-SUMMARY.md`
</output>
