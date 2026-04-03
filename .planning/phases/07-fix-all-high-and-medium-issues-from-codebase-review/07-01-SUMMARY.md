---
phase: 07-fix-all-high-and-medium-issues-from-codebase-review
plan: "01"
subsystem: security
tags: [security, session, auth, blocklist, path-traversal]
dependency_graph:
  requires: []
  provides:
    - expanded-default-blocklist-str2func-builtin-run
    - session-id-path-traversal-protection
    - empty-token-auth-fix
    - security-disable-warning
  affects:
    - src/matlab_mcp/config.py
    - src/matlab_mcp/auth/middleware.py
    - src/matlab_mcp/session/manager.py
tech_stack:
  added: []
  patterns:
    - _SAFE_SESSION_ID_RE compiled regex for session ID validation
    - raw.strip() pattern for env var token normalization
    - Path.resolve() defense-in-depth for path traversal
key_files:
  created: []
  modified:
    - src/matlab_mcp/config.py
    - src/matlab_mcp/auth/middleware.py
    - src/matlab_mcp/session/manager.py
    - tests/test_security.py
    - tests/test_auth_middleware.py
    - tests/test_config.py
    - tests/test_session.py
decisions:
  - "Use None vs empty-string distinction in create_session to let explicit empty session IDs be rejected while None still auto-generates a UUID"
  - "Defense-in-depth: regex validation + Path.resolve() startswith check for session path safety"
  - "str2func/builtin/run added to default blocklist because they allow bypassing existing blocked functions dynamically"
metrics:
  duration_minutes: 15
  completed_date: "2026-04-03"
  tasks_completed: 2
  files_modified: 7
---

# Phase 07 Plan 01: Security Hardening — Blocklist, Session ID, Auth, Warning Summary

One-liner: Expanded default blocklist with str2func/builtin/run, session ID regex + resolve path-traversal guard, empty-token auth fix, and security-disable warning with full test coverage.

## What Was Built

Closed 5 security issues (Issues 1, 5, 15, 20, 21) from the codebase review:

1. **Issue 1 — Expanded blocklist**: Added `str2func`, `builtin`, and `run` to `SecurityConfig.blocked_functions` default list. These functions allow bypassing the existing blocklist by dynamically calling other functions.

2. **Issue 5 — Session ID path traversal**: Added `_SAFE_SESSION_ID_RE` regex and `_sanitize_session_id()` function to `session/manager.py`. All explicit `session_id` values are validated against `^[a-zA-Z0-9_\-\.]{1,128}$` before use as filesystem path components. Added defense-in-depth check using `Path.resolve().startswith(base_resolved)`.

3. **Issue 15 — Eval/new blocked function tests**: Added `TestCheckCodeDefaultBlocklistExpanded` class to `test_security.py` with tests for `eval`, `str2func`, `builtin`, and `run` blocking.

4. **Issue 20 — Empty token auth bypass**: Fixed `BearerAuthMiddleware.__init__` to use `.strip()` on the env var value so empty-string and whitespace-only `MATLAB_MCP_AUTH_TOKEN` values are treated as "no token configured" rather than valid empty tokens.

5. **Issue 21 — Security disable warning**: Added `logger.warning(...)` in `load_config()` when `blocked_functions_enabled=False`, making it visible when operators disable security.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 2be3a6e | fix(07-01): expand blocklist, fix empty-token auth, add security-disable warning |
| Task 2 | f82176b | fix(07-01): session ID sanitization against path traversal |

## Test Results

- Targeted: 151 passed (test_security, test_auth_middleware, test_config, test_session)
- Full suite: 856 passed, 2 skipped — no regressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] None vs empty-string distinction in create_session**
- **Found during:** Task 2
- **Issue:** The original `session_id or str(uuid.uuid4())` treats empty string as falsy, generating a UUID for `session_id=""` instead of rejecting it. The test `test_create_session_rejects_empty` expects `ValueError` for explicit empty strings.
- **Fix:** Changed to `str(uuid.uuid4()) if session_id is None else session_id` to preserve the UUID auto-generation for `None` while passing explicit empty/invalid strings to `_sanitize_session_id` for proper rejection.
- **Files modified:** `src/matlab_mcp/session/manager.py`
- **Commit:** f82176b

## Self-Check: PASSED
