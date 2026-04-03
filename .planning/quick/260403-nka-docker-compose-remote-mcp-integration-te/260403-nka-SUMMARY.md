---
phase: quick
plan: 260403-nka
subsystem: ci
tags: [docker, integration-test, mcp-client, ci, remote, bearer-auth]
dependency_graph:
  requires: [Dockerfile, tests/test_mcp_integration.py]
  provides: [docker-compose.test.yml, tests/remote_client.py, remote-integration-test CI job]
  affects: [.github/workflows/ci.yml]
tech_stack:
  added: [mcp SDK (runtime install), httpx (runtime install)]
  patterns: [docker-compose healthcheck, streamable_http_client with bearer auth, asyncio retry loop]
key_files:
  created:
    - docker-compose.test.yml
    - tests/remote_client.py
  modified:
    - .github/workflows/ci.yml
decisions:
  - pip install mcp httpx at client container entrypoint — mcp SDK not in server image (only fastmcp installed); avoids Dockerfile changes
  - healthcheck uses curl POST to /mcp with JSON-RPC initialize body matching existing test_mcp_integration.py readiness pattern
  - retry loop in remote_client.py (30s, 2s interval) provides resilience beyond healthcheck for any post-healthy startup lag
  - exit-code-from client makes docker compose reflect client script exit code (0=pass, 1=fail) to CI
metrics:
  duration_minutes: 8
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
---

# Quick 260403-nka: Docker Compose Remote MCP Integration Test Summary

**One-liner:** Two-container Docker Compose test that connects a client container to a server container via streamable HTTP MCP with bearer auth, validating expected tools over a Docker bridge network, wired into CI.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Create docker-compose.test.yml and tests/remote_client.py | bd853ee | docker-compose.test.yml, tests/remote_client.py |
| 2 | Add remote-integration-test job to CI workflow | d0321f4 | .github/workflows/ci.yml |

## What Was Built

**docker-compose.test.yml** defines two services on a shared `mcp-test-net` bridge network:

- `server`: builds from existing Dockerfile, runs with `--inspect --transport streamablehttp`, sets `MATLAB_MCP_AUTH_TOKEN=test-token-for-ci` and `MATLAB_MCP_POOL_MIN_ENGINES=0`. Healthcheck POSTs a JSON-RPC initialize request to `/mcp` with bearer auth every 2s, retries 10 times, start_period 5s.
- `client`: same Dockerfile base, overrides entrypoint to `sh -c "pip install --quiet mcp httpx && python /app/tests/remote_client.py"`. Mounts `tests/remote_client.py` read-only. Depends on `server:service_healthy`.

**tests/remote_client.py** is a standalone async script that:
1. Reads `MCP_SERVER_URL` and `MCP_AUTH_TOKEN` from environment.
2. Connects via `streamable_http_client` with `httpx.AsyncClient` carrying bearer auth header.
3. Calls `session.list_tools()` and verifies `{"execute_code", "get_workspace", "list_toolboxes", "get_pool_status"}` are present.
4. Retries connection for up to 30s at 2s intervals on failure.
5. Exits 0 on success, 1 on failure, with clear stdout messages.

**CI job `remote-integration-test`** in `.github/workflows/ci.yml`:
- `needs: lint`, `runs-on: ubuntu-latest`
- Step 1: `actions/checkout@v4`
- Step 2: `docker compose -f docker-compose.test.yml up --build --exit-code-from client`
- Step 3 (always): `docker compose -f docker-compose.test.yml down -v`

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

**Note on mcp SDK:** The plan correctly anticipated that `mcp` SDK is not in the server image. The chosen approach (pip install at container entrypoint) was explicitly the preferred option in the plan spec.

## Verification Results

- `python -c "import ast; ast.parse(...)"` — Python syntax: PASS
- `yaml.safe_load(docker-compose.test.yml)` — Compose YAML structure: PASS
- CI job exists with `needs: lint` and `--exit-code-from client`: PASS
- `ruff check tests/remote_client.py` — Lint: PASS

## Self-Check: PASSED

Files exist:
- docker-compose.test.yml: FOUND
- tests/remote_client.py: FOUND
- .github/workflows/ci.yml: FOUND (modified)

Commits exist:
- bd853ee: FOUND
- d0321f4: FOUND
