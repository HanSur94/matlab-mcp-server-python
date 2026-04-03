# Phase 7: Fix all HIGH and MEDIUM issues from codebase review - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Fix all HIGH and MEDIUM severity issues identified in the full codebase review — covering security (centralize validation, expand blocklist, fix injection vectors), pool/engine (resource leaks, timeout enforcement, race conditions), jobs/session (TOCTOU fixes, state machine guards, shutdown handling), server/config (deprecation fixes, Pydantic compat, YAML error handling), monitoring (query bounds, SQL limits, route dedup), and test quality (coverage gaps, flaky tests, shared fixtures).

### Issue Inventory (39 items)

**CRITICAL (2):**
1. Blocked function bypass via `str2func`, `builtin`, `run` — not in blocklist (security/validator.py, config.py:84-89)
2. Custom tools bypass `security.check_code()` entirely — numeric param injection (tools/custom.py:203-237)

**HIGH (13):**
3. Discovery tools skip security validation (tools/discovery.py:93-131)
4. `check_code_impl` bypasses security validator (tools/core.py:87-145)
5. Session ID unsanitized in filesystem paths — path traversal (session/manager.py:106)
6. Engine leaked on `release()` if `reset_workspace()` raises (pool/manager.py:115-123)
7. `engine_start_timeout` never enforced — deadlocks pool (pool/manager.py:54-59)
8. Race in `acquire()` — no re-poll after `_scale_lock` (pool/manager.py:96-105)
9. TOCTOU in `get_or_create_default()` (session/manager.py:122-128)
10. Cancel/complete race in `cancel_job_impl` (tools/jobs.py:130-146)
11. Job state transitions have no guards (jobs/models.py:77-109)
12. Engine leaked if `_inject_job_context()` throws (jobs/executor.py:77-79)
13. Background asyncio.Task objects fire-and-forget (jobs/executor.py:135-137)
14. Monitoring HTTP shutdown has no timeout (server.py:338-342)
15. No test verifies `eval` is in blocked function list (tests/test_security.py)

**MEDIUM (24):**
16. `asyncio.get_event_loop()` deprecated — use `get_running_loop()` (server.py:357-366)
17. `_get_session_id` swallows exceptions silently (server.py:103-128)
18. `_inspect_mode` dynamic attr on Pydantic model (server.py:849-851)
19. CORS `allow_origins=["*"]` hardcoded (server.py:862-866)
20. Auth bypass when token is empty string (auth/middleware.py:70-72)
21. Env var can silently disable all security (config.py:221-251)
22. Health check drains entire available queue (pool/manager.py:153-159)
23. `get_status()` busy count uses queue arithmetic (pool/manager.py:218-231)
24. Executor accesses `engine._engine.workspace` directly (executor.py:178,184,275)
25. Double-timeout pattern — inner timeout makes outer unreachable (executor.py:110-114)
26. `proactive_warmup_threshold` dead config (config.py:43)
27. `api_history`/`api_events` unbounded query params (dashboard.py:77-83)
28. `get_history`/`get_aggregates` no SQL LIMIT (store.py:183-193, 272-281)
29. Static file handler `..` check instead of Path.resolve() (dashboard.py:209-215)
30. Duplicate route registration diverges (dashboard.py)
31. `total_errors_24h` roundabout computation (tools/monitoring.py:87-89)
32. `psutil.cpu_percent()` always returns 0.0 (collector.py:41)
33. YAML parse error gives raw traceback (config.py:287-306)
34. `_config_dir` dead Pydantic attribute (config.py:181)
35. `asyncio.run()` in sync test methods (test_auth_middleware.py)
36. `_make_mock_pool()` duplicated in 4+ files (conftest.py)
37. Scale-down logic zero test coverage (tests/test_pool.py)
38. `asyncio.sleep(0.5)` race conditions in tests (test_executor_extra.py)
39. Tests assert only types, not content (test_tools.py)

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use codebase review findings (with specific file:line references), ROADMAP phase goal, and codebase conventions to guide decisions.

</decisions>

<code_context>
## Existing Code Insights

Codebase context will be gathered during plan-phase research.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. All changes are defined by the codebase review findings with exact file:line references.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
