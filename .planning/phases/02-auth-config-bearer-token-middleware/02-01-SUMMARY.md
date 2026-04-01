---
phase: 02-auth-config-bearer-token-middleware
plan: 01
subsystem: auth
tags: [auth, middleware, bearer-token, asgi, security]
dependency_graph:
  requires: []
  provides: [BearerAuthMiddleware, matlab_mcp.auth package]
  affects: [src/matlab_mcp/auth/middleware.py, src/matlab_mcp/auth/__init__.py]
tech_stack:
  added: []
  patterns: [pure-ASGI-middleware, hmac-compare-digest, env-var-auth-token]
key_files:
  created:
    - src/matlab_mcp/auth/__init__.py
    - src/matlab_mcp/auth/middleware.py
    - tests/test_auth_middleware.py
  modified: []
decisions:
  - "Pure ASGI class (not BaseHTTPMiddleware) to avoid Starlette streaming double-send bug"
  - "Token read at __init__ time from MATLAB_MCP_AUTH_TOKEN env var, not at import or request time"
  - "hmac.compare_digest used for constant-time token comparison"
metrics:
  duration_seconds: 133
  completed_date: "2026-04-01"
  tasks_completed: 1
  files_created: 3
  files_modified: 0
requirements: [AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05]
---

# Phase 02 Plan 01: BearerAuthMiddleware Summary

**One-liner:** Pure ASGI bearer token auth middleware using hmac.compare_digest with /health and OPTIONS bypass, reading token exclusively from MATLAB_MCP_AUTH_TOKEN env var.

## What Was Built

### src/matlab_mcp/auth/middleware.py
`BearerAuthMiddleware` — a pure ASGI middleware class that enforces bearer token authentication on HTTP requests. Key behaviors:

- Reads `MATLAB_MCP_AUTH_TOKEN` from `os.environ` at `__init__` time (not module level, not per-request)
- Non-HTTP scopes (WebSocket, lifespan) pass through unconditionally
- `/health` path bypasses auth for load balancer health checks
- `OPTIONS` requests bypass auth for CORS pre-flight support
- When no token is configured (`MATLAB_MCP_AUTH_TOKEN` not set), auth is disabled and all requests pass through
- Uses `hmac.compare_digest(provided, configured)` for constant-time comparison
- 401 responses include `WWW-Authenticate: Bearer` header and JSON body `{"error": "unauthorized", "message": "Valid Bearer token required"}` with `Content-Type: application/json`

### src/matlab_mcp/auth/__init__.py
Package init that re-exports `BearerAuthMiddleware` for clean imports: `from matlab_mcp.auth import BearerAuthMiddleware`.

### tests/test_auth_middleware.py
14 unit tests covering all specified behaviors using minimal ASGI helper infrastructure (`CapturedResponse`, `dummy_app`, `make_http_scope`).

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Pure ASGI class over BaseHTTPMiddleware | Avoids Starlette's known streaming response double-send bug; matches FastMCP's own auth middleware pattern |
| Token read at `__init__` time | Module-level reads miss env vars set after import (e.g., in test fixtures using monkeypatch) |
| `hmac.compare_digest` | Prevents timing oracle attacks; Python-idiomatic constant-time comparator for static tokens |
| `_BYPASS_PATHS` as frozenset | O(1) lookup; immutable; communicates intent that the bypass list is a fixed configuration |

## TDD Flow

- **RED:** Wrote 14 failing tests covering all behaviors — `ModuleNotFoundError: No module named 'matlab_mcp.auth'`
- **GREEN:** Created `middleware.py` and `__init__.py` — all 14 tests passed on first run
- **REFACTOR:** Not needed — implementation was clean

## Deviations from Plan

None — plan executed exactly as written. The implementation follows the reference pattern in 02-RESEARCH.md Pattern 1 verbatim.

## Known Stubs

None. The middleware is fully functional with no placeholder behavior.

## Verification Results

```
14 passed in 0.03s
python -c "from matlab_mcp.auth import BearerAuthMiddleware; print('import ok')" -> "import ok"
grep -r "BaseHTTPMiddleware" src/matlab_mcp/auth/*.py -> docstring mention only (not an import)
```

## Commits

| Hash | Description |
|------|-------------|
| 9bb8246 | test(02-01): add failing tests for BearerAuthMiddleware |
| f5dc4c5 | feat(02-01): implement BearerAuthMiddleware as pure ASGI class |

## Self-Check: PASSED
