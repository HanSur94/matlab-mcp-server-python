---
phase: 07-fix-all-high-and-medium-issues-from-codebase-review
plan: "06"
subsystem: monitoring
tags: [security, sql, dashboard, psutil, deduplication]
dependency_graph:
  requires: []
  provides: [bounded-sql-queries, path-traversal-protection, accurate-error-count, primed-cpu-metric, deduplicated-handlers]
  affects: [src/matlab_mcp/monitoring/store.py, src/matlab_mcp/monitoring/dashboard.py, src/matlab_mcp/monitoring/collector.py, src/matlab_mcp/tools/monitoring.py]
tech_stack:
  added: []
  patterns: [SQL-LIMIT, Path.resolve-traversal-check, shared-handler-delegation, psutil-priming]
key_files:
  created: []
  modified:
    - src/matlab_mcp/monitoring/store.py
    - src/matlab_mcp/monitoring/dashboard.py
    - src/matlab_mcp/monitoring/collector.py
    - src/matlab_mcp/tools/monitoring.py
    - tests/test_monitoring_store.py
    - tests/test_monitoring_dashboard.py
    - tests/test_monitoring_collector.py
decisions:
  - "count_errors() passthrough on MetricsCollector to keep tool layer from importing store directly"
  - "Shared helpers as module-level private functions in dashboard.py (not a separate file)"
  - "STATIC_DIR_RESOLVED computed once at module level to avoid re-resolve on every request"
metrics:
  duration_minutes: 10
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 7
---

# Phase 07 Plan 06: Monitoring Subsystem Security and Accuracy Fixes Summary

**One-liner:** Bounded SQL queries with LIMIT, Path.resolve path-traversal guard, clamped HTTP params, direct error COUNT, psutil priming, and deduplicated handler logic.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix store SQL limits, dashboard query clamping, and path traversal | d915ae3 | store.py, dashboard.py, test_monitoring_store.py, test_monitoring_dashboard.py |
| 2 | Fix route duplication, error count computation, cpu_percent priming | 1532593 | dashboard.py, collector.py, tools/monitoring.py, test_monitoring_collector.py |

## What Was Built

### Issue 28 — SQL LIMIT in get_history (store.py)
Added `max_rows: int = 10000` parameter to `get_history()` and appended `LIMIT ?` to the SQL query. Previously unbounded queries could return millions of rows on a busy server.

### Issue 28b — count_errors() method (store.py)
Added `count_errors(hours=24.0) -> int` as a direct `SELECT COUNT(*)` query on the events table filtering by `ERROR_EVENT_TYPES`. Avoids the roundabout `error_rate_per_minute * 60 * 24` approximation used before.

### Issue 27 — Query param clamping (dashboard.py)
Both `create_monitoring_app()` and `register_monitoring_routes()` now clamp:
- `hours` to `[0.01, 720.0]` in `api_history`
- `limit` to `[1, 10000]` in `api_events`

Applied in the shared `_handle_api_history` and `_handle_api_events` helpers that both registration paths delegate to.

### Issue 29 — Path traversal via Path.resolve() (dashboard.py)
Replaced the naive `".." in path_str` check with:
```python
file_path = (STATIC_DIR / path_str).resolve()
if not str(file_path).startswith(str(STATIC_DIR_RESOLVED)):
    return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
```
`STATIC_DIR_RESOLVED` is computed once at module level.

### Issue 30 — Deduplicated route handlers (dashboard.py)
Extracted module-level shared helper functions:
- `_make_health_response(state)` — health JSON with correct status code
- `_make_metrics_response(state)` — metrics snapshot JSON
- `_make_dashboard_response(cached_html)` — HTML or 404
- `_handle_api_history(request, state)` — history query with clamping
- `_handle_api_events(request, state)` — events query with clamping
- `_handle_static_file(path_str)` — safe static file serving

Both `create_monitoring_app()` and `register_monitoring_routes()` are now thin wrappers that call these shared functions.

### Issue 31 — total_errors_24h accurate count (tools/monitoring.py)
Replaced `int(error_rate_per_minute * 60 * 24)` with `await state.collector.count_errors(hours=24)`. Added `count_errors()` passthrough on `MetricsCollector` that delegates to `store.count_errors()`.

### Issue 32 — psutil cpu_percent priming (collector.py)
Added at the end of `MetricsCollector.__init__()`:
```python
try:
    import psutil
    psutil.Process().cpu_percent()
except Exception:
    pass
```
Per psutil documentation, the first call always returns 0.0; this priming call ensures the first real sample from `sample_once()` returns an accurate CPU percentage.

## Test Coverage Added

| Test | File | Purpose |
|------|------|---------|
| `test_get_history_respects_max_rows` | test_monitoring_store.py | Inserts 100 rows, asserts max_rows=10 is honored |
| `test_count_errors_returns_int` | test_monitoring_store.py | Asserts count_errors returns int >= error events inserted |
| `test_count_errors_excludes_non_error_events` | test_monitoring_store.py | Asserts non-error events don't inflate count |
| `test_api_history_clamps_hours_max` | test_monitoring_dashboard.py | hours=999999 is clamped to <=720 |
| `test_api_history_clamps_hours_min` | test_monitoring_dashboard.py | hours=-100 is clamped to >=0.01 |
| `test_api_events_clamps_limit_max` | test_monitoring_dashboard.py | limit=99999 is clamped to <=10000 |
| `test_api_events_clamps_limit_min` | test_monitoring_dashboard.py | limit=0 is clamped to >=1 |
| `test_static_path_traversal_blocked` | test_monitoring_dashboard.py | Path traversal returns 403 (FastMCP route, skipped if unavailable) |
| `test_cpu_percent_primed_at_init` | test_monitoring_collector.py | psutil.cpu_percent() called once at init |

## Verification Results

```
tests/test_monitoring_store.py: 13 passed
tests/test_monitoring_dashboard.py: 28 passed, 1 skipped
tests/test_monitoring_collector.py: 8 passed
Full suite: 864 passed, 3 skipped
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- `src/matlab_mcp/monitoring/store.py` — FOUND
- `src/matlab_mcp/monitoring/dashboard.py` — FOUND
- `src/matlab_mcp/monitoring/collector.py` — FOUND
- `src/matlab_mcp/tools/monitoring.py` — FOUND
- `tests/test_monitoring_store.py` — FOUND
- `tests/test_monitoring_dashboard.py` — FOUND
- `tests/test_monitoring_collector.py` — FOUND
- Commit d915ae3 — FOUND
- Commit 1532593 — FOUND
