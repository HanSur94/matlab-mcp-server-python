---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 03
subsystem: monitoring
tags: [fastmcp, middleware, metrics, timing, monitoring]

# Dependency graph
requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4 (plan 02)
    provides: "fastmcp>=3.4.4,<4.0.0 pin (Middleware/MiddlewareContext API available since 3.0, exercised here on installed 3.2.0)"
provides:
  - "src/matlab_mcp/middleware/ package with TimingMiddleware(Middleware)"
  - "on_call_tool records a distinct \"tool_call\" event (tool, duration_ms, success) into MetricsCollector"
  - "TimingMiddleware registered in create_server via mcp.add_middleware(...) when monitoring is enabled"
affects: [08-monitoring-follow-ups, future-executor-timing-migration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastMCP Middleware subclass with async on_call_tool(context, call_next) timing wrapper"
    - "Collector event recording guarded against None collector (safe to register unconditionally)"

key-files:
  created:
    - src/matlab_mcp/middleware/__init__.py
    - src/matlab_mcp/middleware/timing.py
    - tests/test_middleware_timing.py
  modified:
    - src/matlab_mcp/server.py

key-decisions:
  - "Used a distinct \"tool_call\" event type (not job_completed/job_failed) so the middleware's per-call metrics are additive to, not double-counting, the executor's existing job counters — event type is intentionally absent from collector._COUNTER_MAP"
  - "Followed the PLAN's corrected record_event(event_type: str, details: dict) signature, not the RESEARCH.md F5 kwargs sketch"
  - "Left the executor's imperative job_completed/job_failed timing in place (incremental migration per CONTEXT.md §7 default — no big-bang executor rewrite this pass)"
  - "Registered the middleware only when config.monitoring.enabled and state.collector are truthy, mirroring the existing pattern used for the metrics store/sampling wiring in create_server"
  - "Did not touch the Starlette BearerAuth/CORS middleware list used for SSE/streamable-http transports — that is a separate, transport-layer auth concern (per plan's read_first note on lines 862-899)"

patterns-established:
  - "New middleware/ package as the home for future FastMCP Middleware subclasses (F5 is the first; F6/F12 land in later 08-xx plans)"

requirements-completed: [D-04]

coverage:
  - id: D1
    description: "TimingMiddleware(Middleware).on_call_tool times every tool call and records a \"tool_call\" event (tool name, duration_ms, success) into MetricsCollector; failure path re-raises the original exception unchanged"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "tests/test_middleware_timing.py::TestTimingMiddlewareSuccess::test_records_tool_call_event_with_duration_and_success"
        status: pass
      - kind: unit
        ref: "tests/test_middleware_timing.py::TestTimingMiddlewareFailure::test_records_failure_event_and_reraises"
        status: pass
      - kind: unit
        ref: "tests/test_middleware_timing.py::TestTimingMiddlewareSuccess::test_never_emits_job_completed_or_job_failed"
        status: pass
      - kind: unit
        ref: "tests/test_middleware_timing.py::TestTimingMiddlewareFailure::test_failure_never_emits_job_completed_or_job_failed"
        status: pass
      - kind: unit
        ref: "tests/test_middleware_timing.py::TestTimingMiddlewareNoCollector::test_none_collector_is_a_no_op"
        status: pass
    human_judgment: false
  - id: D2
    description: "create_server registers TimingMiddleware via mcp.add_middleware(...) when monitoring is enabled, without disturbing the Starlette BearerAuth/CORS middleware chain used for HTTP transports"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "tests/test_server.py (full suite, 84 tests, all pass with the new registration in place)"
        status: pass
      - kind: other
        ref: "grep -F 'add_middleware(TimingMiddleware' src/matlab_mcp/server.py — pattern present"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-07-12
status: complete
---

# Phase 08 Plan 03: TimingMiddleware for per-tool-call metrics Summary

**New `TimingMiddleware(Middleware)` records per-tool-call duration and success/failure as a distinct `"tool_call"` event into `MetricsCollector`, registered in `create_server` behind the monitoring flag, without double-counting the executor's existing job totals.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-07-12T22:00:00Z (approx.)
- **Completed:** 2026-07-12T22:21:47Z
- **Tasks:** 2
- **Files modified:** 4 (3 created, 1 modified)

## Accomplishments
- `src/matlab_mcp/middleware/timing.py` — `TimingMiddleware(Middleware)` with async `on_call_tool(context, call_next)`: times the call with `time.perf_counter()`, records a `"tool_call"` event (`tool`, `duration_ms`, `success`) via `MetricsCollector.record_event`, and re-raises exceptions unchanged after recording `success=False`.
- Guards a `None` collector as a no-op, so the middleware is safe to construct/register even when monitoring is disabled (defensive; actual registration is monitoring-gated in `create_server`).
- `create_server` registers `TimingMiddleware(state.collector)` via `mcp.add_middleware(...)` right after the `FastMCP(...)` construction, only when `config.monitoring.enabled and state.collector`.
- 6 unit tests against a fake collector cover: success path (event shape + result passthrough), failure path (event shape + re-raise), no-double-count on both paths, and the `None`-collector no-op on both paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: TimingMiddleware + unit tests** - `d53cdba` (feat)
2. **Task 2: Register TimingMiddleware in create_server** - `2583a4c` (feat)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `src/matlab_mcp/middleware/__init__.py` - New package, exports `TimingMiddleware`
- `src/matlab_mcp/middleware/timing.py` - `TimingMiddleware(Middleware)` implementation
- `tests/test_middleware_timing.py` - Unit tests against a fake collector
- `src/matlab_mcp/server.py` - Registers `TimingMiddleware` in `create_server` behind `config.monitoring.enabled`

## Decisions Made
- Followed the PLAN's corrected `record_event(event_type: str, details: dict)` signature (not the RESEARCH.md F5 kwargs sketch), per the plan's explicit CRITICAL API NOTES.
- Chose the `"tool_call"` event type specifically because it is absent from `collector._COUNTER_MAP` and `_ERROR_EVENTS` — a clean additive store write that does not increment `completed_total`/`failed_total`/`error_total`.
- Resolved the tool name defensively via `getattr(context, "message", None)` / `getattr(message, "name", None)`, falling back to `"unknown"`, to tolerate shape differences across FastMCP 3.x point releases (the installed 3.2.0 exposes `context.message.name` for `CallToolRequestParams`, matching `mcp.types.CallToolRequestParams.name`).
- Left the Starlette `BearerAuthMiddleware`/`CORSMiddleware` list (used only for `sse`/`streamablehttp` transports at server.py's `run()` call site) completely untouched — it is a transport-layer ASGI concern, orthogonal to FastMCP's own `add_middleware` mechanism.

## Deviations from Plan

None — plan executed as written. Both tasks matched the plan's `<action>` and `<verify>` steps exactly; no Rule 1-4 auto-fixes were needed.

## TDD Gate Compliance

Task 1 was marked `tdd="true"`. Per the plan's `<behavior>`, I wrote `tests/test_middleware_timing.py` and `src/matlab_mcp/middleware/timing.py` together and verified all 6 tests passed before committing, but I did **not** commit them as a separate failing `test(...)` (RED) commit followed by a `feat(...)` (GREEN) commit — both landed in a single `feat(08-03): add TimingMiddleware for per-tool-call metrics` commit (`d53cdba`).

- RED gate commit: **missing** (no standalone `test(...)` commit exists for this task).
- GREEN gate commit: present in spirit (`d53cdba` contains both the passing tests and the implementation), but not preceded by a genuinely-failing test commit.

This is a process deviation from the strict RED→GREEN commit sequence; the tests themselves are behaviorally sound (verified failing-path/passing-path assertions, run and confirmed green post-hoc) and the full test suite (923 passed) is green. No functional risk, but flagging per the TDD Gate Compliance protocol.

## Issues Encountered

A global user-level `~/.gitignore` rule (`**/src/`) matches this project's `src/` tree and silently ignores any *newly created* file under `src/`, even though pre-existing files in the same tree (e.g. `src/matlab_mcp/server.py`) are already tracked. `git add src/matlab_mcp/middleware/__init__.py src/matlab_mcp/middleware/timing.py` was refused by git with "The following paths are ignored by one of your .gitignore files." Verified both files were plain, non-secret Python source explicitly required by the plan's `files_modified` list, then staged with `git add -f` for those two files only (not a blanket `-f`). This is unrelated to the `.planning/`-gitignore skip path in the final-commit step (that path is a deliberate per-project choice); this is an accidental match from an unrelated global ignore pattern.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- F5 (TimingMiddleware) is complete and registered; subsequent 08-xx plans (F6 structured output, F12 streamable-http default) are unaffected by this change and can proceed independently.
- Executor's imperative `job_completed`/`job_failed` timing is untouched — a future phase can migrate it onto the middleware layer incrementally, as noted in CONTEXT.md §7.
- No blockers.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-12*

## Self-Check: PASSED

All created/modified files and both task commit hashes (`d53cdba`, `2583a4c`) verified present on disk / in `git log`.
