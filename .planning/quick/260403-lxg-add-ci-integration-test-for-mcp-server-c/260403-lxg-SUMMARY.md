---
phase: quick
plan: 260403-lxg
subsystem: testing/ci
tags: [integration-test, mcp, streamable-http, bearer-auth, ci]
dependency_graph:
  requires: []
  provides: [mcp-integration-test, ci-integration-job]
  affects: [tests/, .github/workflows/ci.yml]
tech_stack:
  added: []
  patterns: [subprocess-server-fixture, mcp-streamable-http-client, pytest-module-scoped-fixture]
key_files:
  created:
    - tests/test_mcp_integration.py
  modified:
    - .github/workflows/ci.yml
    - pyproject.toml
decisions:
  - Use python -c "from matlab_mcp.server import main; main()" instead of python -m matlab_mcp (no __main__.py exists)
  - Use streamable_http_client (new name) with http_client=httpx.AsyncClient(headers=...) for auth
  - Omit --timeout=60 from CI pytest command (pytest-timeout not in dev deps)
  - integration marker registered in pyproject.toml to suppress PytestUnknownMarkWarning
metrics:
  duration: 12m
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_changed: 3
---

# Quick 260403-lxg: Add CI Integration Test for MCP Server Summary

**One-liner:** End-to-end MCP integration test connecting a real client via streamable HTTP with bearer auth, plus CI job that runs it without MATLAB.

## What Was Built

A pytest integration test (`tests/test_mcp_integration.py`) that starts the MCP server as a subprocess in `--inspect` mode (no MATLAB required), waits for server readiness by polling `/health`, then connects a real MCP client using the official `mcp.client.streamable_http.streamable_http_client` transport with bearer auth, calls `tools/list`, and asserts that known tools (`execute_code`, `get_workspace`, `list_toolboxes`, `get_pool_status`) appear in the response.

A new `integration-test` job was added to `.github/workflows/ci.yml` that runs this test on every push/PR using Python 3.12 on Ubuntu.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Create MCP integration test script | 6c45d64 |
| 2 | Add integration-test job to CI workflow | 4740c11 |

## Verification Results

1. `python -c "import ast; ast.parse(...)"` — Syntax OK
2. `python -c "import yaml; ..."` — CI job exists
3. `pytest tests/test_mcp_integration.py -v -m integration` — 1 passed in 1.44s

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] No `__main__.py` for `python -m matlab_mcp`**
- **Found during:** Task 1 test run
- **Issue:** `python -m matlab_mcp` failed with "No module named matlab_mcp.__main__; 'matlab_mcp' is a package and cannot be directly executed"
- **Fix:** Used `python -c "from matlab_mcp.server import main; main()"` instead — avoids needing a `__main__.py` and is portable
- **Files modified:** `tests/test_mcp_integration.py`
- **Commit:** 6c45d64

**2. [Rule 1 - Bug] `streamablehttp_client` deprecated, replaced by `streamable_http_client` with different signature**
- **Found during:** Task 1 test run
- **Issue:** Old `streamablehttp_client` accepted `headers=` kwarg; new `streamable_http_client` uses `http_client=httpx.AsyncClient(...)` instead
- **Fix:** Updated import to `streamable_http_client` and passed `httpx.AsyncClient(headers=headers)` as `http_client` parameter
- **Files modified:** `tests/test_mcp_integration.py`
- **Commit:** 6c45d64

**3. [Rule 2 - Missing] `integration` marker not registered in `pyproject.toml`**
- **Found during:** Task 1 test run (PytestUnknownMarkWarning)
- **Fix:** Added `"integration: end-to-end MCP server integration tests"` to `[tool.pytest.ini_options].markers`
- **Files modified:** `pyproject.toml`
- **Commit:** 6c45d64

## Known Stubs

None.

## Self-Check: PASSED

- `tests/test_mcp_integration.py` — FOUND
- `.github/workflows/ci.yml` — FOUND (integration-test job present)
- Commit 6c45d64 — FOUND
- Commit 4740c11 — FOUND
