---
phase: 07-fix-all-high-and-medium-issues-from-codebase-review
plan: 02
subsystem: security
tags: [security, executor, defense-in-depth, centralization]
dependency_graph:
  requires: []
  provides: [centralized-security-check-in-executor]
  affects: [src/matlab_mcp/jobs/executor.py, src/matlab_mcp/server.py, src/matlab_mcp/tools/core.py]
tech_stack:
  added: []
  patterns: [defense-in-depth security, executor-level validation]
key_files:
  created:
    - tests/test_executor_extra.py (added TestExecutorSecurityValidation class with 3 tests)
  modified:
    - src/matlab_mcp/jobs/executor.py
    - src/matlab_mcp/server.py
    - src/matlab_mcp/tools/core.py
decisions:
  - "Security validator created before JobExecutor in MatlabMCPServer.__init__() so it can be passed as constructor arg"
  - "check_code() import inside execute() method to avoid circular imports and keep module testable in isolation"
  - "tools/core.py pre-check retained as defense-in-depth with updated comment"
metrics:
  duration: 5 minutes
  completed: 2026-04-03T18:47:32Z
  tasks_completed: 2
  files_modified: 4
---

# Phase 07 Plan 02: Centralize Security Validation in JobExecutor Summary

**One-liner:** Executor-level check_code() added to JobExecutor.execute() so custom tools and discovery tools can no longer bypass the blocked-functions blocklist.

## Objective

Close the security bypass where custom tools and discovery tools could execute arbitrary MATLAB code without passing through `SecurityValidator.check_code()`. Centralize security validation in `JobExecutor.execute()` as the single enforcement point for all code paths.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add security parameter to JobExecutor and centralize check_code | fb1fac8 | executor.py, core.py, test_executor_extra.py |
| 2 | Wire security validator into JobExecutor in server.py | 5c3e27f | server.py |

## What Was Built

### executor.py changes
- Added `security: Any = None` parameter to `JobExecutor.__init__()` (after `config`, before `collector` to avoid breaking existing callers)
- Stored as `self._security`
- Added security check at the very beginning of `execute()` (before engine acquisition or job creation) — returns `{"status": "failed", "error": {...}}` with `"Blocked"` in message if `BlockedFunctionError` is raised
- Import of `BlockedFunctionError` is inside the method to avoid circular imports

### server.py changes
- Moved `self.security = SecurityValidator(...)` creation to BEFORE `self.executor` construction
- Added `security=self.security` to `JobExecutor(...)` constructor call
- Added comment explaining the centralization rationale

### tools/core.py changes
- Updated comment on `execute_code_impl` security check to "Defense-in-depth: executor also checks, but pre-check catches early"

### New tests (TestExecutorSecurityValidation)
- `test_executor_rejects_blocked_code`: `system('whoami')` returns `status=failed` with `"Blocked"` in message
- `test_executor_allows_clean_code`: `disp('hello')` is not blocked at the security layer
- `test_executor_without_security_does_not_block`: Without `security=` kwarg, no code is blocked

## Verification

- `python -m pytest tests/test_executor_extra.py -x -q` → 51 passed
- `python -m pytest tests/test_executor_extra.py tests/test_tools_custom.py tests/test_tools_discovery.py -x -q` → 137 passed
- `python -m pytest tests/ -x -q` → 844 passed, 2 skipped

## Deviations from Plan

None — plan executed exactly as written. The only structural consideration was that `self.security` needed to be created before `self.executor` in `MatlabMCPServer.__init__()`. This was a trivial reordering with no architectural implications.

## Known Stubs

None.

## Self-Check: PASSED

- [x] src/matlab_mcp/jobs/executor.py exists and contains `security: Any = None` in `__init__` and `self._security.check_code(code)` in `execute()`
- [x] src/matlab_mcp/server.py contains `security=self.security` in JobExecutor constructor call
- [x] tests/test_executor_extra.py contains `test_executor_rejects_blocked_code` asserting `status == "failed"` and `"Blocked"` in message
- [x] Commits fb1fac8 and 5c3e27f exist in git log
