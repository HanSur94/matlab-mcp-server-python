---
phase: 07-fix-all-high-and-medium-issues-from-codebase-review
plan: "04"
subsystem: jobs, session, executor, server
tags: [state-machine, concurrency, resource-safety, shutdown]
dependency_graph:
  requires: ["07-03"]
  provides: [job-transition-guards, toctou-safe-session, background-task-tracking, executor-shutdown]
  affects: [jobs/models.py, session/manager.py, jobs/executor.py, server.py]
tech_stack:
  added: []
  patterns: [transition-guard, done-callback-cleanup, unlocked-helper]
key_files:
  created: []
  modified:
    - src/matlab_mcp/jobs/models.py
    - src/matlab_mcp/session/manager.py
    - src/matlab_mcp/jobs/executor.py
    - src/matlab_mcp/server.py
    - tests/test_jobs.py
    - tests/test_session.py
    - tests/test_executor_extra.py
decisions:
  - "_VALID_TRANSITIONS dict drives all mark_* guards — single source of truth for valid state transitions"
  - "get_or_create_default holds lock for entire check-and-create to close TOCTOU window"
  - "_create_session_unlocked extracted so both create_session and get_or_create_default share creation logic"
  - "engine.set_workspace_var/get_workspace_vars used instead of engine._engine.workspace direct access"
  - "executor.shutdown() cancels background tasks before pool.stop() to prevent orphaned tasks"
  - "monitoring_task awaited with asyncio.wait_for(timeout=5.0) to prevent indefinite shutdown hang"
metrics:
  duration: 7
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 7
---

# Phase 07 Plan 04: Job/Session State Machine Fixes Summary

Job state machine guards, TOCTOU-safe session creation, background task tracking with shutdown, executor workspace API migration, and monitoring HTTP shutdown timeout.

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | Job state transition guards and TOCTOU fix | 33b2cfb | Done |
| 2 | Background task tracking, executor workspace API, shutdown | e37b7c9 | Done |

## What Was Built

### Task 1 — Job state transition guards and TOCTOU-safe session creation

**Issue 11 — Job state machine (jobs/models.py):**
- Added `_VALID_TRANSITIONS` dict mapping each `JobStatus` to its allowed successor states
- Added `_transition_to(new_status)` private helper that checks the map and returns False for invalid transitions
- Refactored all four `mark_*` methods to call `_transition_to` first — invalid transitions are silent no-ops
- PENDING → FAILED is now rejected (must go via RUNNING); cancel on COMPLETED is a no-op (Issue 10 resolved)

**Issue 9 — TOCTOU in get_or_create_default (session/manager.py):**
- Extracted `_create_session_unlocked()` with the same logic as the old `create_session()` body but without acquiring `self._lock`
- Refactored `create_session()` to `with self._lock: return self._create_session_unlocked(...)`
- Refactored `get_or_create_default()` to hold `self._lock` for the entire check-and-create, closing the race window

**Tests added:**
- `test_mark_running_from_pending_succeeds` — valid transition works
- `test_mark_cancelled_from_completed_is_noop` — cancel/complete race resolved
- `test_mark_running_from_completed_is_noop` — terminal state not re-entered
- `test_mark_failed_from_pending_is_noop` — PENDING cannot directly transition to FAILED
- `test_get_or_create_default_is_idempotent` — same Session object returned on repeated calls

### Task 2 — Background task tracking, executor workspace API, shutdown

**Issue 13 — Background task tracking (jobs/executor.py):**
- Added `self._background_tasks: set[asyncio.Task] = set()` to `__init__`
- Both promotion paths (`sync_timeout == 0` and sync timeout expiry) now track tasks with `add_done_callback(self._background_tasks.discard)` for automatic cleanup on completion
- Added `shutdown()` async method that cancels all tracked tasks, gathers with `return_exceptions=True`, and clears the set

**Issue 12 — Engine leaked if _inject_job_context() throws (executor.py):**
- Wrapped the `_inject_job_context()` call in its own try/except block
- On exception: marks job FAILED, releases engine, returns error result — no engine leak

**Issue 14 — Monitoring HTTP shutdown timeout (server.py):**
- `await monitoring_task` replaced with `await asyncio.wait_for(monitoring_task, timeout=5.0)` with `TimeoutError` logged as warning
- Added `await state.executor.shutdown()` before `await state.pool.stop()` in lifespan teardown

**Workspace API migration (executor.py):**
- `_inject_job_context` now uses `engine.set_workspace_var()` instead of `engine._engine.workspace[...]`
- `_build_result` now uses `engine.get_workspace_vars().items()` instead of `engine._engine.workspace.items()`

**Tests added:**
- `test_executor_tracks_background_tasks` — tasks present in set immediately after promote-to-async
- `test_executor_shutdown_cancels_tasks` — shutdown() empties the set
- `test_completed_task_removed_from_set` — done_callback cleans up completed tasks

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_error_result_structure to respect new transition guards**
- **Found during:** Task 2 test run
- **Issue:** `test_error_result_structure` called `mark_failed()` directly on a PENDING job — this was a no-op under the new guards, making `job.error` None and the assert fail
- **Fix:** Added `job.mark_running("engine-0")` before `mark_failed()` to reach RUNNING state first (the valid transition path)
- **Files modified:** `tests/test_executor_extra.py`
- **Commit:** e37b7c9

## Issues Resolved

- Issue 9: TOCTOU in get_or_create_default — fixed
- Issue 10: Cancel/complete race on Job — fixed via transition guards
- Issue 11: Missing state machine guards on Job — fixed
- Issue 12: Engine leaked if _inject_job_context() raises — fixed
- Issue 13: Background tasks untracked — fixed
- Issue 14: Monitoring HTTP shutdown no timeout — fixed

## Self-Check: PASSED

- src/matlab_mcp/jobs/models.py — FOUND
- src/matlab_mcp/session/manager.py — FOUND
- src/matlab_mcp/jobs/executor.py — FOUND
- src/matlab_mcp/server.py — FOUND
- Commit 33b2cfb — FOUND
- Commit e37b7c9 — FOUND
