---
phase: 02-auth-config-bearer-token-middleware
plan: 02
subsystem: auth
tags: [auth, middleware, bearer-token, cors, cli, config, server]
dependency_graph:
  requires: [BearerAuthMiddleware from plan 02-01]
  provides: [--generate-token CLI flag, middleware wiring in SSE transport, token-in-config warning]
  affects:
    - src/matlab_mcp/server.py
    - src/matlab_mcp/config.py
    - tests/test_server.py
    - tests/test_config.py
tech_stack:
  added: []
  patterns: [starlette-middleware-list, cors-middleware, generate-token-cli, config-leak-detection]
key_files:
  created:
    - .planning/phases/02-auth-config-bearer-token-middleware/02-02-SUMMARY.md
  modified:
    - src/matlab_mcp/server.py
    - src/matlab_mcp/config.py
    - tests/test_server.py
    - tests/test_config.py
decisions:
  - "Middleware list order: BearerAuthMiddleware outermost (first), CORSMiddleware inner — ensures auth is checked before CORS headers are added"
  - "Auth status logged after banner so token presence is visible at startup"
  - "CORS allow_origins=['*'] for maximum agent compatibility in development; production should restrict via reverse proxy"
  - "_warn_if_token_in_config fires on raw YAML data before env overrides to detect original config file leaks"
metrics:
  duration_seconds: 600
  completed_date: "2026-04-01"
  tasks_completed: 2
  files_created: 1
  files_modified: 4
requirements: [AUTH-02, AUTH-04, AUTH-05, AUTH-06]
---

# Phase 02 Plan 02: Middleware Wiring and Config Warning Summary

**One-liner:** SSE transport wired with BearerAuthMiddleware + CORSMiddleware via Starlette Middleware list, plus --generate-token CLI flag and _warn_if_token_in_config() to prevent token leakage in YAML.

## What Was Built

### src/matlab_mcp/server.py

**--generate-token flag:**
New argparse argument that calls `secrets.token_hex(32)` to produce a 64-char hex token and prints env var snippets for Linux/macOS (export), Windows cmd (set), and PowerShell ($env:), then exits with code 0. Does not require MATLAB or config loading.

**Middleware wiring for SSE:**
When `transport == "sse"`, a two-element `list[Middleware]` is built:
1. `Middleware(BearerAuthMiddleware)` — outermost, enforces auth before anything else
2. `Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET","POST","OPTIONS"], allow_headers=["Authorization","Content-Type","Accept"])`

Passed as `middleware=` kwarg to `server.run()`. The stdio path is unchanged — no middleware, no auth.

**Auth status at startup:**
After the closing banner line, if transport is SSE, logs either "Bearer token enabled" (when token is set) or a WARNING that requests will be accepted without authentication.

**Lifespan warning update:**
The old proxy-auth-only warning in `lifespan()` was updated to also check `MATLAB_MCP_AUTH_TOKEN` — only warns when neither proxy auth nor bearer token is configured.

### src/matlab_mcp/config.py

**_warn_if_token_in_config(data: dict):**
Iterates all sections in the raw YAML data dict. For any section that is a dict, checks each key name against `_SENSITIVE_KEY_PATTERNS = {"token", "secret", "api_key", "password", "bearer"}`. If a key name contains any pattern, emits a `logger.warning()` pointing users to `MATLAB_MCP_AUTH_TOKEN` env var. Called inside `load_config()` on the raw data before `_apply_env_overrides()`.

### tests/test_config.py — TestTokenWarning class

7 test cases: `test_token_key_in_config_logs_warning`, `test_bearer_key_in_config_logs_warning`, `test_api_key_in_config_logs_warning`, `test_normal_config_no_warning`, `test_nested_non_dict_section_no_error`, `test_secret_key_triggers_warning`, `test_password_key_triggers_warning`. All use `caplog.at_level(logging.WARNING)`.

### tests/test_server.py — TestGenerateToken class + updated SSE tests

5 new tests in `TestGenerateToken`: verifies 64-char hex token output, POSIX/Windows/PowerShell snippet presence, and stdio-no-middleware invariant. Updated 4 existing SSE tests in `TestMain` and `TestMainAdditionalBranches` to assert `middleware` kwarg is present in `server.run()` calls for SSE transport.

## TDD Flow

- **RED:** Added `TestTokenWarning` (importing not-yet-existing `_warn_if_token_in_config`) and `TestGenerateToken` — failed with ImportError and test failures
- **GREEN:** Added `_warn_if_token_in_config()` + call in `load_config()` — all 12 new tests passed, 781 total
- **REFACTOR:** Not needed — implementation was clean on first pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing SSE test assertions to include middleware kwarg**
- **Found during:** Task 1 execution
- **Issue:** `test_main_transport_override_sse`, `test_main_sse_passes_host_and_port`, `test_main_monitoring_enabled_sse`, `test_main_sse_without_transport_override` were asserting `server.run()` is called without `middleware=`, which broke after SSE middleware wiring was added
- **Fix:** Replaced `assert_called_once_with(transport="sse", host=..., port=...)` with kwarg-based assertions that also verify `"middleware" in call_kwargs`
- **Files modified:** tests/test_server.py
- **Commits:** 800791b, 9082dd0

## Known Stubs

None. All middleware wiring is functional. `allow_origins=["*"]` is intentional for development — production restriction is documented.

## Verification Results

```
781 passed, 2 skipped in tests/
python -c "from matlab_mcp.auth import BearerAuthMiddleware; print('ok')" -> "ok"
grep -r "BaseHTTPMiddleware" src/matlab_mcp/auth/*.py -> docstring only (not an import)
grep -c "generate.token" src/matlab_mcp/server.py -> 2 (argument + handler)
grep -c "BearerAuthMiddleware" src/matlab_mcp/server.py -> 2
grep -c "CORSMiddleware" src/matlab_mcp/server.py -> 2
grep "allow_origins" src/matlab_mcp/server.py -> allow_origins=["*"]
grep -c "_warn_if_token_in_config" src/matlab_mcp/config.py -> 2 (definition + call)
```

## Commits

| Hash | Description |
|------|-------------|
| 800791b | feat(02-02): add --generate-token flag and wire middleware into SSE transport |
| 85ba8c7 | test(02-02): add failing tests for token-in-config warning and --generate-token |
| 9082dd0 | feat(02-02): add _warn_if_token_in_config to load_config() and fix SSE test assertions |

## Self-Check: PASSED
