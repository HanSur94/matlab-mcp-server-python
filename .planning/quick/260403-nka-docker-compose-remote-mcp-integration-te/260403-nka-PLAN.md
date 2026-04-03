---
phase: quick
plan: 260403-nka
type: execute
wave: 1
depends_on: []
files_modified:
  - docker-compose.test.yml
  - tests/remote_client.py
  - .github/workflows/ci.yml
autonomous: true
must_haves:
  truths:
    - "docker compose -f docker-compose.test.yml up --exit-code-from client exits 0 when server is healthy"
    - "Client container connects to server container over Docker network using bearer auth"
    - "Client validates expected MCP tools are present in tools/list response"
    - "CI job runs the remote integration test on every push/PR"
  artifacts:
    - path: "docker-compose.test.yml"
      provides: "Two-service compose file simulating PC A (client) and PC B (server)"
    - path: "tests/remote_client.py"
      provides: "Standalone MCP client script that exits 0/1"
    - path: ".github/workflows/ci.yml"
      provides: "remote-integration-test job"
  key_links:
    - from: "tests/remote_client.py"
      to: "server:8765/mcp"
      via: "streamable HTTP MCP client with bearer token"
      pattern: "streamable_http_client.*server.*8765"
    - from: "docker-compose.test.yml"
      to: "Dockerfile"
      via: "build context for server service"
      pattern: "build:"
---

<objective>
Add a Docker Compose-based remote MCP integration test that simulates a client (PC A) connecting to a server (PC B) over a Docker network. This validates that the MCP server is accessible over HTTP with bearer auth from a separate container, proving the server works in a networked deployment scenario.

Purpose: Catch networking, auth, and transport issues that the single-process integration test cannot detect.
Output: docker-compose.test.yml, tests/remote_client.py, updated CI workflow.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@Dockerfile
@docker-compose.yml
@.github/workflows/ci.yml
@tests/test_mcp_integration.py

<interfaces>
<!-- The existing integration test (tests/test_mcp_integration.py) shows the exact MCP client pattern to follow -->

From tests/test_mcp_integration.py:
```python
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

_AUTH_TOKEN = "test-token-for-ci"
_EXPECTED_TOOLS = {"execute_code", "get_workspace", "list_toolboxes", "get_pool_status"}

# Client connection pattern:
async with streamable_http_client(url, http_client=http_client) as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.list_tools()
```

From Dockerfile:
```dockerfile
FROM python:3.12-slim
ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "sse"]
```

Server CLI supports: `--inspect` (no MATLAB needed), `--transport streamablehttp`
Auth via env var: `MATLAB_MCP_AUTH_TOKEN=<token>`
Pool skip via: `MATLAB_MCP_POOL_MIN_ENGINES=0`
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create docker-compose.test.yml and tests/remote_client.py</name>
  <files>docker-compose.test.yml, tests/remote_client.py</files>
  <action>
1. Create `docker-compose.test.yml` at repo root with two services on a shared Docker network:

   **server** service:
   - `build: .` (uses existing Dockerfile)
   - Override command: `["--inspect", "--transport", "streamablehttp"]`
   - Set environment: `MATLAB_MCP_AUTH_TOKEN=test-token-for-ci`, `MATLAB_MCP_POOL_MIN_ENGINES=0`
   - Expose port 8765 internally (no host mapping needed, containers share network)
   - Add healthcheck: poll `http://localhost:8765/mcp` with a JSON-RPC initialize POST (same pattern as test_mcp_integration.py readiness check). Use `curl` with `--fail` and the bearer token header. Interval 2s, timeout 3s, retries 10, start_period 5s.

   **client** service:
   - `build: .` (same Dockerfile base — it already has Python 3.12)
   - Override entrypoint to run the client script: `["python", "/app/tests/remote_client.py"]`
   - Mount `tests/remote_client.py` into the container at `/app/tests/remote_client.py:ro`
   - Set environment: `MCP_SERVER_URL=http://server:8765/mcp`, `MCP_AUTH_TOKEN=test-token-for-ci`
   - `depends_on: server` with `condition: service_healthy`

   Define a custom network `mcp-test-net` (bridge driver).

2. Create `tests/remote_client.py` as a standalone script (no pytest dependency):
   - Read `MCP_SERVER_URL` and `MCP_AUTH_TOKEN` from environment variables.
   - Install `mcp` and `httpx` at runtime is NOT needed — they are already in the server image's pip packages. However, `mcp` SDK may not be installed in the server image (it installs `fastmcp` not `mcp`). To handle this: the client service should run a pip install of `mcp httpx` before running the script, OR better, use a multi-stage approach. Simplest approach: override the client entrypoint to `["sh", "-c", "pip install mcp httpx && python /app/tests/remote_client.py"]`.
   - Use the same MCP client pattern from test_mcp_integration.py: `streamable_http_client` with `httpx.AsyncClient` carrying bearer auth header.
   - Add a retry loop (up to 30s, polling every 2s) for the MCP connection in case the healthcheck passes but the server needs a moment more.
   - Call `session.list_tools()` and verify `_EXPECTED_TOOLS = {"execute_code", "get_workspace", "list_toolboxes", "get_pool_status"}` are all present.
   - Print clear success/failure messages to stdout.
   - `sys.exit(0)` on success, `sys.exit(1)` on failure (any missing tool or connection error).
   - Use `asyncio.run()` as the entry point (standalone script, not pytest).
   - Include a module docstring explaining purpose and usage.
  </action>
  <verify>
    <automated>docker compose -f docker-compose.test.yml build 2>&1 | tail -5</automated>
  </verify>
  <done>docker-compose.test.yml defines server and client services; tests/remote_client.py is a standalone MCP client script that connects, lists tools, and exits 0/1.</done>
</task>

<task type="auto">
  <name>Task 2: Add remote-integration-test job to CI workflow</name>
  <files>.github/workflows/ci.yml</files>
  <action>
Add a new job `remote-integration-test` to `.github/workflows/ci.yml`:

- `needs: lint` (same dependency as the existing docker and integration-test jobs)
- `runs-on: ubuntu-latest`
- Steps:
  1. `actions/checkout@v4`
  2. Run: `docker compose -f docker-compose.test.yml up --build --exit-code-from client`
  3. Cleanup step (always run): `docker compose -f docker-compose.test.yml down -v`

Place the job after the existing `docker` job in the file for logical grouping.

Do NOT modify any existing jobs. Only add the new job.
  </action>
  <verify>
    <automated>python -c "import yaml; y=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'remote-integration-test' in y['jobs'], 'Job missing'; j=y['jobs']['remote-integration-test']; assert j['needs']=='lint', f'Wrong needs: {j[\"needs\"]}'; print('CI job validated OK')"</automated>
  </verify>
  <done>CI workflow contains remote-integration-test job that runs docker compose -f docker-compose.test.yml up --exit-code-from client on every push/PR.</done>
</task>

</tasks>

<verification>
1. `docker compose -f docker-compose.test.yml config` validates compose syntax
2. `python -c "import ast; ast.parse(open('tests/remote_client.py').read()); print('Syntax OK')"` validates Python syntax
3. CI workflow YAML parses and contains the new job
4. (Optional, requires Docker) `docker compose -f docker-compose.test.yml up --build --exit-code-from client` exits 0
</verification>

<success_criteria>
- docker-compose.test.yml exists with server (streamablehttp + inspect + bearer auth) and client services on a shared network
- tests/remote_client.py connects to server via MCP SDK, lists tools, asserts expected tools, exits 0/1
- .github/workflows/ci.yml has remote-integration-test job that runs the compose test
- All files pass lint (ruff) and syntax validation
</success_criteria>

<output>
After completion, create `.planning/quick/260403-nka-docker-compose-remote-mcp-integration-te/260403-nka-SUMMARY.md`
</output>
