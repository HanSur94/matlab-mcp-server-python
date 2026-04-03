---
phase: 07-fix-all-high-and-medium-issues-from-codebase-review
plan: "03"
subsystem: pool
tags: [pool, engine, resource-safety, concurrency, bug-fix]
dependency_graph:
  requires: []
  provides:
    - "Leak-free engine release via try/finally in release()"
    - "Enforced engine_start_timeout via asyncio.wait_for"
    - "Acquire race fix via re-poll after scale lock"
    - "Accurate busy count from EngineState in get_status()"
    - "set_workspace_var / get_workspace_vars API on MatlabEngineWrapper"
  affects:
    - src/matlab_mcp/pool/manager.py
    - src/matlab_mcp/pool/engine.py
tech_stack:
  added: []
  patterns:
    - "try/finally for resource safety in async release"
    - "asyncio.wait_for for external process timeout enforcement"
    - "get_nowait() re-poll after holding a lock to avoid missed wakeups"
    - "Sum-from-state rather than queue arithmetic for busy counting"
key_files:
  created: []
  modified:
    - src/matlab_mcp/pool/manager.py
    - src/matlab_mcp/pool/engine.py
    - tests/test_pool.py
decisions:
  - "Set engine._needs_replacement=True on reset failure rather than discarding engine immediately — defers retirement to health check cycle"
  - "Issue 22 (health check drain) documented with comment; no code change — drain-and-refill is correct, just undocumented"
  - "Workspace API methods added to engine.py in plan 03; executor.py migration deferred to plan 04 per plan spec"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 3
---

# Phase 07 Plan 03: Pool Resource Safety and Engine Workspace API Summary

Fix pool and engine resource safety: prevent engine leaks on release failure, enforce engine start timeout, fix acquire() race condition, fix get_status() busy count, and add proper workspace API to MatlabEngineWrapper.

## What Was Built

Six issues fixed across `pool/manager.py` and `pool/engine.py`:

**Issue 6 — Engine leaked on release() failure:**
`release()` now uses try/finally so `engine.mark_idle()` and `_available.put()` always execute even if `reset_workspace()` raises. A failed reset sets `engine._needs_replacement = True` so the health check cycle can retire the engine later.

**Issue 7 — engine_start_timeout never enforced:**
`_start_engine_async()` now wraps `engine.start` with `asyncio.wait_for(timeout=engine_start_timeout)`. On timeout: the engine is removed from `_all_engines` and a descriptive `RuntimeError` is raised.

**Issue 8 — Race in acquire() after _scale_lock:**
After the `_scale_lock` block (when pool is at max capacity), `acquire()` now does a `get_nowait()` re-poll before blocking on `_available.get()`. This picks up engines that were returned while the caller held the scale lock.

**Issue 22 — Health check drain undocumented:**
Added a comment to `run_health_checks()` explaining that the drain-and-refill pattern is intentional and that engines are briefly unavailable during the check window.

**Issue 23 — get_status() busy count wrong:**
Replaced queue-arithmetic `busy = total - available` with `sum(1 for e in self._all_engines if e.state == EngineState.BUSY)`. This gives the correct count even during engine transitions.

**Issue 24 — MatlabEngineWrapper has no workspace API:**
Added `set_workspace_var(name, value)` and `get_workspace_vars()` methods to `MatlabEngineWrapper`. Both raise `RuntimeError` if `self._engine is None`. Also added `self._needs_replacement: bool = False` attribute to `__init__()`.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 3bef462 | fix(07-03): release leak, start timeout, acquire race, status count |
| 2 | d4361f7 | feat(07-03): workspace API and _needs_replacement flag |

## Test Coverage

4 new tests added to `tests/test_pool.py`:

- `test_release_returns_engine_on_reset_failure` — verifies engine back in queue and `_needs_replacement=True`
- `test_start_engine_timeout` — verifies `RuntimeError` raised when start exceeds timeout
- `test_acquire_repoll_after_scale_lock` — verifies re-poll picks up engine without blocking
- `test_get_status_counts_busy_from_state` — verifies busy count reflects `EngineState.BUSY`

All 845 tests pass (2 skipped, 267 warnings).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all changes are complete implementations.

## Self-Check: PASSED

Files created/modified:
- FOUND: src/matlab_mcp/pool/manager.py
- FOUND: src/matlab_mcp/pool/engine.py
- FOUND: tests/test_pool.py

Commits:
- FOUND: 3bef462
- FOUND: d4361f7
