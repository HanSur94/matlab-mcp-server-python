---
phase: 01-fastmcp-3-0-upgrade
plan: 02
subsystem: infra
tags: [fastmcp, starlette, custom_route, monitoring, dashboard]

# Dependency graph
requires:
  - phase: 01-fastmcp-3-0-upgrade/01-01
    provides: FastMCP 3.2.0 installed with public API surface available
provides:
  - Monitoring dashboard routes registered via @mcp.custom_route() public API
  - register_monitoring_routes() function in dashboard.py for clean route registration
  - No private _additional_http_routes usage in production code
affects: [02-auth, 03-streamable-http, monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Use @mcp.custom_route() decorator to register HTTP endpoints on FastMCP instances"
    - "Static file path-traversal protection via .. check before FileResponse serving"

key-files:
  created: []
  modified:
    - src/matlab_mcp/monitoring/dashboard.py
    - src/matlab_mcp/server.py

key-decisions:
  - "Keep create_monitoring_app() intact alongside new register_monitoring_routes() for test compatibility"
  - "Static file handler uses FileResponse with path-traversal guard (reject paths containing ..)"

patterns-established:
  - "register_monitoring_routes(mcp, state) pattern: closures over state, programmatic custom_route registration"

requirements-completed: [FMCP-03]

# Metrics
duration: 8min
completed: 2026-04-01
---

# Phase 01 Plan 02: FMCP-03 Gap Closure Summary

**Monitoring dashboard routes migrated from private mcp._additional_http_routes to @mcp.custom_route() public API, closing the FMCP-03 verification gap with 755 tests passing.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-01T19:45:00Z
- **Completed:** 2026-04-01T19:53:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `register_monitoring_routes(mcp, state)` to dashboard.py registering all 7 routes via `@mcp.custom_route()` public API
- Replaced `mcp._additional_http_routes.append(Mount(...))` in server.py with the new clean registration function
- Static file handler includes path-traversal protection (rejects `..` in paths)
- Full 755-test regression suite passes with zero failures
- Ruff linter reports zero style violations

## Task Commits

1. **Task 1: Refactor dashboard.py to export register function using @mcp.custom_route()** - `47e9034` (feat)
2. **Task 2: Full regression suite and cleanup verification** - verification only, no code changes

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `src/matlab_mcp/monitoring/dashboard.py` - Added `register_monitoring_routes()` function with 7 `@mcp.custom_route()` registrations; preserved `create_monitoring_app()` for backward compatibility
- `src/matlab_mcp/server.py` - Replaced private `_additional_http_routes` block with `register_monitoring_routes(mcp, state)` call

## Decisions Made
- Kept `create_monitoring_app()` function intact alongside the new `register_monitoring_routes()` — 17 existing tests in test_monitoring_dashboard.py use `create_monitoring_app()` via Starlette TestClient and would break if removed
- Static file serving uses `FileResponse` with a `..` path-traversal guard (403 response) rather than mounting `StaticFiles` ASGI app, because `custom_route()` registers individual request handlers, not ASGI mounts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None - implementation was straightforward. The `.gitignore` pattern `/monitoring/` initially caused `git add` to fail for the `src/matlab_mcp/monitoring/` path, but the file was already tracked so it staged correctly without the `-f` flag.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- FMCP-03 gap is closed: all monitoring routes use `@mcp.custom_route()` public API
- No private FastMCP API usage remains in production code
- Phase 01 verification can now confirm FMCP-03 as complete

---
*Phase: 01-fastmcp-3-0-upgrade*
*Completed: 2026-04-01*
