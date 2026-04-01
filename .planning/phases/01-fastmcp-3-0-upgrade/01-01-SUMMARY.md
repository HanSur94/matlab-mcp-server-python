---
phase: 01-fastmcp-3-0-upgrade
plan: "01"
subsystem: dependencies
tags: [fastmcp, migration, dependencies, tests]
dependency_graph:
  requires: []
  provides: [fastmcp-3.2.0-base]
  affects: [all-phases]
tech_stack:
  added: [fastmcp==3.2.0, py-key-value-aio==0.4.4, uncalled-for==0.2.0, watchfiles==1.1.1, cyclopts==4.10.0, authlib==1.6.9]
  patterns: [list_tools-public-api, show_banner-false-stdio]
key_files:
  created: []
  modified:
    - pyproject.toml
    - requirements-lock.txt
    - tests/test_server.py
    - src/matlab_mcp/server.py
decisions:
  - "Use await mcp.list_tools() instead of private _tool_manager.get_tools() for tool listing in tests"
  - "Add show_banner=False to stdio transport run() to prevent MCP protocol corruption"
  - "Bump pydantic minimum to >=2.11.7 per FastMCP 3.2.0 hard requirement"
  - "Bump uvicorn minimum to >=0.35.0 in dev and monitoring optional deps"
metrics:
  duration_minutes: 4
  completed_date: "2026-04-01"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 4
---

# Phase 01 Plan 01: FastMCP 3.0 Migration Summary

**One-liner:** FastMCP 2.14.5 → 3.2.0 upgrade with dependency pin updates, lockfile regeneration, 5 test fixes, and stdio banner suppression.

## What Was Built

Migrated the MATLAB MCP server from FastMCP 2.14.5 to FastMCP 3.2.0. The migration was minimal-footprint: update dependency pins, regenerate lockfile, fix tests that used removed private APIs, and suppress the new startup banner on stdio transport.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Update dependency pins and regenerate lockfile | eb4085e | pyproject.toml, requirements-lock.txt |
| 2 | Fix broken tests and suppress stdio banner | 6b4b162 | tests/test_server.py, src/matlab_mcp/server.py |

## Changes Made

### pyproject.toml
- `fastmcp>=2.0.0,<3.0.0` → `fastmcp>=3.2.0,<4.0.0`
- `pydantic>=2.0.0` → `pydantic>=2.11.7` (FastMCP 3.2.0 hard requirement for pydantic[email])
- `uvicorn>=0.20.0` → `uvicorn>=0.35.0` in both `dev` and `monitoring` optional deps

### requirements-lock.txt
- Regenerated for FastMCP 3.2.0 ecosystem
- Updated `fastmcp==2.14.5` → `fastmcp==3.2.0`
- Updated `py-key-value-aio==0.3.0` → `py-key-value-aio==0.4.4`
- Updated `watchfiles` (new transitive dep)
- Updated `sse-starlette==3.3.3` → `3.3.2` (installed version)

### tests/test_server.py
- Replaced `await mcp._tool_manager.get_tools()` with `await mcp.list_tools()` in 3 tests
- Updated 2 `assert_called_once_with(transport="stdio")` assertions to include `show_banner=False`

### src/matlab_mcp/server.py
- Changed `server.run(transport="stdio")` to `server.run(transport="stdio", show_banner=False)`

## Verification Results

```
755 passed, 242 warnings in 11.07s
```

- `python3 -c "import fastmcp; print(fastmcp.__version__)"` → `3.2.0`
- `python3 -c "from matlab_mcp.server import create_server; from matlab_mcp.config import load_config; c = load_config(); s = create_server(c); print('OK')"` → `OK`
- `python3 -c "from fastmcp import FastMCP, Context; print('imports OK')"` → `imports OK`
- `grep -r "_tool_manager" tests/` → no output (clean)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test assertions for stdio run() call**
- **Found during:** Task 2 verification
- **Issue:** Two additional tests (`test_main_stdio_default` and `test_main_monitoring_enabled_stdio`) asserted `mock_mcp.run.assert_called_once_with(transport="stdio")` without `show_banner=False`. After adding `show_banner=False` to the server, these assertions failed.
- **Fix:** Updated both assertions to `assert_called_once_with(transport="stdio", show_banner=False)` to match the new call signature.
- **Files modified:** tests/test_server.py
- **Commit:** 6b4b162 (included in Task 2 commit)

## Known Stubs

None — all functionality is fully wired.

## Self-Check: PASSED

Files exist:
- pyproject.toml: FOUND
- requirements-lock.txt: FOUND
- tests/test_server.py: FOUND
- src/matlab_mcp/server.py: FOUND

Commits exist:
- eb4085e: FOUND
- 6b4b162: FOUND
