---
phase: 03-streamable-http-transport-session-routing
plan: 02
subsystem: server
tags: [transport, streamable-http, session-routing, sse-deprecation, tdd]
dependency_graph:
  requires: ["03-01"]
  provides: ["streamable-http transport branch", "per-session workspace isolation for HTTP", "SSE deprecation warning"]
  affects: ["src/matlab_mcp/server.py", "tests/test_server.py"]
tech_stack:
  added: []
  patterns:
    - "Transport check: `if transport in ('sse', 'streamablehttp'):`"
    - "ctx.session_id with ctx.client_id fallback chain (issue #956)"
    - "server.run(transport='streamable-http', stateless_http=...) for streamablehttp config"
key_files:
  created: []
  modified:
    - src/matlab_mcp/server.py
    - tests/test_server.py
decisions:
  - "client_id fallback applies to both SSE and streamablehttp (symmetry: both are HTTP transports)"
  - "SSE deprecation warning placed in startup banner (before server.run()) for visibility"
  - "config value 'streamablehttp' maps to FastMCP 'streamable-http' (hyphen) in server.run()"
  - "stateless_http only forwarded for streamablehttp; NOT passed to SSE (FastMCP raises ValueError)"
metrics:
  duration_minutes: 6
  completed_date: "2026-04-01"
  tasks_completed: 2
  files_changed: 2
---

# Phase 03 Plan 02: Streamable HTTP Transport and Session Routing Summary

Wire streamable HTTP transport into server.py: transport branch in main(), session routing in _get_session_id(), workspace isolation in _get_temp_dir(), SSE deprecation warning, startup banner updates, and CLI --transport choice.

## What Was Built

**`src/matlab_mcp/server.py`** — Six targeted changes:

1. `_get_session_id()`: Extended from SSE-only to `("sse", "streamablehttp")` with a `ctx.client_id` fallback when `ctx.session_id` is unavailable (issue #956 mitigation).

2. `_get_temp_dir()`: Extended from `transport == "sse"` to `transport in ("sse", "streamablehttp")` so streamablehttp clients get per-session workspace directories.

3. CLI `--transport`: Added `"streamablehttp"` to `choices=["stdio", "sse", "streamablehttp"]`.

4. Startup banner: Added SSE deprecation warning (`logger.warning("SSE transport is deprecated...")`) and streamablehttp HTTP endpoint logging.

5. Auth status block: Extended to `if transport in ("sse", "streamablehttp"):` with `%s` format for the warning message.

6. `main()` transport branch: Replaced `if transport == "sse": ... else:` with `if transport in ("sse", "streamablehttp"):` plus inner `if transport == "streamablehttp": server.run(transport="streamable-http", ..., stateless_http=config.server.stateless_http)` branch.

**`tests/test_server.py`** — 172 lines added/modified:

- `streamablehttp_config` and `streamablehttp_server_state` fixtures
- `TestStreamableHTTPTransport` class: 9 tests covering session_id/client_id fallback, temp dir isolation, main() transport branch, stateless_http forwarding, auth warning, dashboard URL
- `TestSSEDeprecationWarning` class: 1 test confirming deprecation warning fires for SSE transport
- `TestGenerateToken` class (from master merge): 5 tests for `--generate-token` CLI flag
- Fixed `test_sse_*_falls_back_to_default`: updated to set `client_id=falsy` (consistent with new client_id fallback)
- Fixed `test_expected_core_tools_registered` and related: used `await mcp.get_tools()` (async API, not `list_tools()`)

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 (RED) | Add failing tests for streamable HTTP transport | a3cc415 | tests/test_server.py |
| 2 (GREEN) | Implement streamable HTTP transport in server.py | 44d1b8c | src/matlab_mcp/server.py, tests/test_server.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SSE fallback tests broken by client_id addition**
- **Found during:** Task 2
- **Issue:** `test_sse_empty_session_id_falls_back_to_default` and `test_sse_none_session_id_falls_back_to_default` failed because MagicMock's `.client_id` is truthy by default, so the new fallback returned `client_id` instead of "default"
- **Fix:** Set `ctx.client_id = ""` / `ctx.client_id = None` in those tests to make the full fallback chain reach "default"
- **Files modified:** tests/test_server.py
- **Commit:** 44d1b8c

**2. [Rule 1 - Bug] Fixed test_expected_core_tools_registered broken by master merge**
- **Found during:** Task 2 (full suite run)
- **Issue:** Master branch changed tool listing tests from `await mcp._tool_manager.get_tools()` to `await mcp.list_tools()`, but `FastMCP.list_tools()` does not exist; the correct method is `await mcp.get_tools()`
- **Fix:** Updated 3 tests in TestCreateServer to use `await mcp.get_tools()` and `set(tools_dict.keys())`
- **Files modified:** tests/test_server.py
- **Commit:** 44d1b8c

### Merge Required

Worktree was behind master by 5 commits (Phase 03-01 and Phase 02-02 work). Ran `git merge master` to pick up the `streamablehttp` config value and auth middleware code before implementing transport branch changes.

## Verification

```
python -m pytest tests/ -q  # 798 passed, 2 skipped
grep -c 'in ("sse", "streamablehttp")' src/matlab_mcp/server.py  # 4
grep 'transport="streamable-http"' src/matlab_mcp/server.py  # found
grep 'deprecated' src/matlab_mcp/server.py  # SSE deprecation warning found
python -c "from matlab_mcp.config import ServerConfig; c = ServerConfig(transport='streamablehttp'); print(c.transport)"  # streamablehttp
```

## Known Stubs

None — all transport routing is fully wired. The streamablehttp branch calls `server.run(transport="streamable-http", ...)` with all required parameters.

## Self-Check: PASSED

- `src/matlab_mcp/server.py` modified: found
- `tests/test_server.py` modified: found
- Commits a3cc415 and 44d1b8c: found in git log
- Full test suite: 798 passed, 2 skipped
