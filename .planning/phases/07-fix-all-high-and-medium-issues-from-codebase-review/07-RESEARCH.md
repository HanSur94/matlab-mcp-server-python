# Phase 7: Fix all HIGH and MEDIUM issues from codebase review - Research

**Researched:** 2026-04-03
**Domain:** Python async server — security, concurrency, resource management, test quality
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — pure infrastructure phase. All implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use codebase review findings (with specific file:line references), ROADMAP phase goal, and codebase conventions to guide decisions.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

## Summary

This phase fixes 39 HIGH and MEDIUM severity issues discovered in a full codebase review. The issues fall into six areas: security (validation gaps and injection vectors), pool/engine (resource leaks, timeout enforcement, race conditions), jobs/session (TOCTOU, state machine gaps, background task tracking), server/config (deprecated API usage, Pydantic compat, YAML error handling), monitoring (unbounded queries, SQL limits, route duplication), and test quality (flaky sleeps, duplicated fixtures, coverage gaps). The current test suite (843 tests, 841 passing, 2 skipped) is green and must remain green after every wave.

The fixes must be wave-ordered carefully: security fixes in Wave 1 (they are the most isolated), pool/engine resource-safety in Wave 2 (depend on engine API surface), jobs/session state machine guards in Wave 3 (depend on pool being correct), server/config + monitoring in Wave 4, and test improvements in Wave 5.

**Primary recommendation:** Fix security and resource-leak issues first; they are the most isolated and carry the highest real-world risk. Use try/finally blocks for all resource release paths. Centralize security.check_code() in JobExecutor.execute() rather than in individual tool handlers so it is impossible to bypass.

---

## Standard Stack

### Core (no new dependencies — all fixes are code changes only)
| File | Version | Purpose |
|------|---------|---------|
| `src/matlab_mcp/security/validator.py` | current | SecurityValidator.check_code() — centralize callers here |
| `src/matlab_mcp/pool/manager.py` | current | EnginePoolManager — release(), acquire(), health check |
| `src/matlab_mcp/jobs/executor.py` | current | JobExecutor — engine leak on _inject_job_context, task tracking |
| `src/matlab_mcp/jobs/models.py` | current | Job state machine — add transition guards |
| `src/matlab_mcp/session/manager.py` | current | SessionManager — TOCTOU in get_or_create_default, session_id sanitization |
| `src/matlab_mcp/server.py` | current | Lifespan, asyncio.get_event_loop() → get_running_loop(), CORS, Pydantic compat |
| `src/matlab_mcp/config.py` | current | YAML parse error handling, dead attributes, env override security |
| `src/matlab_mcp/monitoring/dashboard.py` | current | Route dedup, static path traversal fix |
| `src/matlab_mcp/monitoring/store.py` | current | SQL LIMIT enforcement |
| `src/matlab_mcp/monitoring/collector.py` | current | psutil cpu_percent fix |
| `src/matlab_mcp/auth/middleware.py` | current | Empty string auth bypass |
| `tests/conftest.py` | current | Shared _make_mock_pool fixture |

**No new pip packages required for any fix.**

---

## Architecture Patterns

### Pattern 1: Centralize security validation in JobExecutor.execute()
**What:** Move the `security.check_code(code)` call from individual tool handlers into `JobExecutor.execute()` so it runs unconditionally for all code paths (core tools, custom tools, check_code_impl indirect path).
**When to use:** Any time code flows to executor.execute() — which is all paths except check_code_impl's mlint invocation, which does not run arbitrary user code.
**Current callers to update:**
- `tools/core.py:execute_code_impl` — currently calls security.check_code() before executor.execute(); this call becomes redundant but harmless as defense-in-depth (keep it).
- `jobs/executor.py:execute()` — add security.check_code(code) as the first operation; requires injecting security validator into JobExecutor.
- `tools/custom.py:_handler()` — currently calls executor.execute() with no security check; centralization fixes this automatically.
- `tools/discovery.py` — calls executor.execute() for `help` and `ver` commands with validated MATLAB names, not arbitrary code; still benefits from executor-level check.

**Implementation:** Add `security: Optional[Any] = None` parameter to `JobExecutor.__init__()` and store as `self._security`. In `execute()`, if `self._security is not None`, call `self._security.check_code(code)` and raise/return error on `BlockedFunctionError`. Wire it in `server.py:create_server()` where JobExecutor is constructed.

### Pattern 2: try/finally for all engine release paths
**What:** Wrap every acquire→work→release sequence so release happens even if the work block raises.
**Current issue in pool/manager.py:release():** `engine.reset_workspace()` can raise; if it does, `engine.mark_idle()` and `self._available.put(engine)` are never called, leaking the engine.
**Fix:** Wrap in try/finally:
```python
async def release(self, engine: MatlabEngineWrapper) -> None:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, engine.reset_workspace)
    except Exception as exc:
        logger.warning("[%s] reset_workspace failed: %s — returning engine anyway", engine.engine_id, exc)
    finally:
        engine.mark_idle()
        await self._available.put(engine)
```

**Current issue in jobs/executor.py:execute():** `_inject_job_context()` is called between acquire and start of try block (line 82). If it raises (it won't because it already swallows exceptions internally, but that is the issue — it swallows instead of failing safely), the engine is not released.
**Actual issue:** `_inject_job_context()` at lines 77-79 accesses `engine._engine.workspace` directly, bypassing the MatlabEngineWrapper API. This works because MatlabEngineWrapper exposes `_engine` as a semi-private attribute, but it creates coupling. The fix is to add a `set_workspace_var(key, value)` method to MatlabEngineWrapper, and use that in `_inject_job_context`.

### Pattern 3: Job state machine transition guards
**What:** `Job.mark_running()`, `mark_completed()`, `mark_failed()`, `mark_cancelled()` have no guards — they allow illegal transitions (e.g. COMPLETED → RUNNING). This enables the cancel/complete race in `cancel_job_impl` (issue #10).
**Fix:** Add a `_VALID_TRANSITIONS` dict and raise `RuntimeError` (or silently ignore) on invalid transitions:
```python
_VALID_TRANSITIONS = {
    JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}
```
For cancel_job_impl: the race is that cancel_job_impl reads `status` without holding a lock, then calls `mark_cancelled()` which may run after `mark_completed()` has already fired. With transition guards in mark_cancelled, the guard makes the second mutation a no-op.

### Pattern 4: TOCTOU fix in get_or_create_default()
**What:** `get_or_create_default()` in session/manager.py releases the lock between the check and the create. Between releasing and re-acquiring in `create_session()`, another coroutine can also pass the `sessions.get()` check and both will try to create the session.
**Current code (lines 122-128):**
```python
def get_or_create_default(self) -> Session:
    with self._lock:
        session = self._sessions.get(_DEFAULT_SESSION_ID)
        if session is not None:
            return session
    return self.create_session(session_id=_DEFAULT_SESSION_ID)  # lock released!
```
**Fix:** Hold the lock for the full check-and-create operation. Extract a `_create_session_locked()` internal helper that assumes the lock is already held, then have `get_or_create_default()` call it while holding `self._lock`.

### Pattern 5: Session ID sanitization for filesystem paths
**What:** `session_id` from HTTP context (ctx.session_id or ctx.client_id) is used directly in `session/manager.py:create_session()` at line 106 as a directory name component: `temp_dir = self._base_temp / session_id`. A crafted session_id like `../../etc/` escapes the base temp directory.
**Fix:** Sanitize session_id before using it as a path component:
```python
import re
_SAFE_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-\.]{1,128}$')

def _sanitize_session_id(session_id: str) -> str:
    if not _SAFE_SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return session_id
```
Call this in `create_session()` before forming `temp_dir`. UUID4 values (which are the normal case) pass this regex. Also call `Path.resolve()` on the resulting temp_dir and verify it is a sub-path of `self._base_temp.resolve()` as defense-in-depth.

### Pattern 6: engine_start_timeout enforcement
**What:** `pool_config.engine_start_timeout` (default 120s) exists in config but is never passed to the thread executor call in `_start_engine_async()`. A hanging MATLAB startup blocks a pool thread indefinitely.
**Fix:** Wrap `engine.start` with `asyncio.wait_for()`:
```python
async def _start_engine_async(self) -> MatlabEngineWrapper:
    loop = asyncio.get_running_loop()
    engine = self._make_engine()
    self._all_engines.append(engine)
    timeout = self._pool_config.engine_start_timeout
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, engine.start),
            timeout=float(timeout),
        )
    except asyncio.TimeoutError:
        self._all_engines.remove(engine)
        raise RuntimeError(f"Engine {engine.engine_id} failed to start within {timeout}s")
    return engine
```

### Pattern 7: acquire() re-poll after _scale_lock
**What:** After releasing `_scale_lock` at max capacity, code falls through to `await self._available.get()` which blocks indefinitely. The issue: between releasing `_scale_lock` and calling `_available.get()`, an engine may have become available but nobody notified the waiter. This is actually correct asyncio behavior (get() will return when an engine becomes available), but the issue is that a second acquire() call at max capacity that finds an engine added to `_available` in the brief gap between the scale_lock check and the await will both queue. The real issue is that code after the `_scale_lock` block doesn't re-try `get_nowait()` first:
```python
# After scale_lock block, try immediate get before blocking
try:
    engine = self._available.get_nowait()
    engine.mark_busy()
    return engine
except asyncio.QueueEmpty:
    pass
# Now block
engine = await self._available.get()
```

### Pattern 8: Background task tracking
**What:** `asyncio.create_task(self._wait_for_completion(...))` in executor.py at lines 135-137 creates fire-and-forget tasks. If the event loop closes before these complete, tasks are cancelled without warning and the engine may not be released.
**Fix:** Track created tasks in a set and add a done callback that removes them:
```python
self._background_tasks: set[asyncio.Task] = set()

# When creating:
task = asyncio.create_task(self._wait_for_completion(...))
self._background_tasks.add(task)
task.add_done_callback(self._background_tasks.discard)
```
Add a `shutdown()` method that cancels and awaits all tracked tasks. Call it from the lifespan shutdown sequence.

### Pattern 9: asyncio.get_event_loop() → get_running_loop()
**What:** `asyncio.get_event_loop()` at server.py lines 357-366 (inside the `finally` block of lifespan) is deprecated in Python 3.10+ and emits DeprecationWarning in Python 3.12. When called from inside an async context, use `asyncio.get_running_loop()`.
**Fix:** Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()` at lines 357 and 358.

### Pattern 10: _inspect_mode dynamic attribute on AppConfig
**What:** `config._inspect_mode = True` at server.py line 851 sets a dynamic attribute on a frozen Pydantic v2 model. Pydantic v2 raises `ValidationError` or silently ignores dynamic attributes depending on model config. The current code adds `# type: ignore[attr-defined]` to suppress the type error, but the runtime behavior is undefined.
**Fix:** Add `_inspect_mode: bool = False` as a proper field to `AppConfig` with `model_config = ConfigDict(extra="allow")` already in place, or use a separate boolean flag not attached to the Pydantic model. The simplest approach is to add it as a proper optional field:
```python
class AppConfig(BaseModel):
    ...
    inspect_mode: bool = False  # set by --inspect CLI flag; not in YAML
```
Remove the `_config_dir` private attribute (issue #34) at the same time — it is declared as `_config_dir: Optional[Path] = None` which is a Pydantic v2 private attribute syntax but is never actually used (the value is passed directly to `resolve_paths()`).

### Pattern 11: Auth bypass when token is empty string
**What:** In `auth/middleware.py`, `self._token = os.environ.get("MATLAB_MCP_AUTH_TOKEN")`. If the env var is set but empty (`MATLAB_MCP_AUTH_TOKEN=""`), `self._token` becomes `""`. Then `hmac.compare_digest("", "")` returns True for any request that provides an empty Bearer token. The guard `if self._token is None` does not catch this.
**Fix:**
```python
raw = os.environ.get("MATLAB_MCP_AUTH_TOKEN", "").strip()
self._token: str | None = raw if raw else None
```

### Pattern 12: SQL LIMIT in get_history / get_aggregates
**What:** `store.get_history()` and `store.get_aggregates()` have no SQL LIMIT clause. A large `hours` value or a long-running server could return millions of rows.
**Fix:** Add a configurable `max_rows` limit (default 10000) to `get_history()` and `get_aggregates()`:
```sql
SELECT timestamp, value FROM metrics
WHERE category = ? AND metric_name = ? AND timestamp >= ?
ORDER BY timestamp ASC
LIMIT ?;
```

### Pattern 13: Unbounded query params in dashboard routes
**What:** `api_history` accepts `hours` as a float with no upper bound. A caller passing `hours=876000` (100 years) triggers a full table scan. `api_events` accepts `limit` as an int with no upper bound.
**Fix:** Clamp values:
```python
hours = min(max(float(hours), 0.01), 720.0)  # 1 minute to 30 days
limit = min(max(int(limit), 1), 10000)
```

### Pattern 14: Static file Path.resolve() traversal check
**What:** `dashboard.py:209-215` checks `".." in path_str`. A crafted URL using URL-encoded `%2e%2e` or other forms could bypass this check depending on the routing layer's URL decoding behavior.
**Fix:** Use `Path.resolve()` to get the canonical path and verify it is under `STATIC_DIR`:
```python
file_path = (STATIC_DIR / path_str).resolve()
if not str(file_path).startswith(str(STATIC_DIR.resolve())):
    return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
```

### Pattern 15: psutil.cpu_percent() always returns 0.0 on first call
**What:** `psutil.Process().cpu_percent()` always returns 0.0 on the very first call (psutil docs: "the first call will always return 0.0"). The collector calls it once per sample, so every sample shows 0% CPU.
**Fix:** Call `cpu_percent()` with an interval, or call it once at collector startup to prime it, then use subsequent calls. The simplest fix is to call it once at `MetricsCollector.__init__()`:
```python
try:
    import psutil
    psutil.Process().cpu_percent()  # prime the counter; first call always returns 0.0
except Exception:
    pass
```

### Pattern 16: total_errors_24h roundabout computation
**What:** `tools/monitoring.py:87-89` computes `total_errors_24h` by fetching `error_rate_per_minute` from `get_aggregates(hours=24)` then multiplying by `60 * 24`. This round-trips through rate → count → rate in a lossy float conversion. The store already has a direct count query.
**Fix:** Add a `count_errors(hours: float) -> int` method to MetricsStore that does a direct COUNT(*) query with the ERROR_EVENT_TYPES filter, and use that in `get_error_log_impl`.

### Pattern 17: Route duplication in dashboard.py
**What:** `register_monitoring_routes()` (for SSE/streamablehttp transport) and `create_monitoring_app()` (for stdio transport) define identical handler logic in two separate functions. Any change to one must be duplicated in the other.
**Fix:** Extract the handler logic into shared functions in a new `monitoring/handlers.py` module that both `register_monitoring_routes()` and `create_monitoring_app()` import. The handler function bodies become thin wrappers.

### Pattern 18: Env var can silently disable all security
**What:** `MATLAB_MCP_SECURITY_BLOCKED_FUNCTIONS_ENABLED=false` disables the entire blocklist via the env override mechanism in `config.py:221-251`. There is no warning emitted when this happens.
**Fix:** In `load_config()`, after applying env overrides, if `config.security.blocked_functions_enabled is False`, emit a `logger.warning("Security: blocked_functions_enabled=False — ALL code execution is unrestricted")`. This makes the dangerous configuration visible in logs without preventing it.

### Pattern 19: YAML parse error gives raw traceback
**What:** `load_config()` at lines 295-296 uses `yaml.safe_load(fh)` without catching `yaml.YAMLError`. A malformed YAML file produces an unhandled exception with a raw traceback.
**Fix:**
```python
try:
    loaded = yaml.safe_load(fh) or {}
except yaml.YAMLError as exc:
    raise ValueError(f"Failed to parse config file {path}: {exc}") from exc
```

### Pattern 20: Duplicate test fixtures
**What:** `_make_mock_pool()` is copy-pasted in 6 test files: `test_tools.py`, `test_monitoring_extra.py`, `test_executor_extra.py`, `test_coverage_gaps.py`, `test_jobs.py`, `test_monitoring_collector.py`. Any change to the mock must be applied 6 times.
**Fix:** Consolidate into `tests/conftest.py` as a `mock_pool` pytest fixture. Each test file that currently defines its own `_make_mock_pool()` imports/uses the fixture instead.

### Pattern 21: asyncio.run() in sync test methods
**What:** `test_auth_middleware.py` uses `asyncio.run(middleware(...))` inside regular (non-async) test methods. This works but is the wrong pattern: pytest-asyncio (configured with `asyncio_mode = "auto"`) handles async tests automatically. Using `asyncio.run()` creates a new event loop per call, incompatible with some async context managers.
**Fix:** Convert all test methods in `test_auth_middleware.py` that use `asyncio.run()` to `async def` methods. Remove the `asyncio.run()` calls. pytest-asyncio will handle the rest.

### Pattern 22: asyncio.sleep(0.5) race conditions in tests
**What:** `test_executor_extra.py` has 6 tests (lines 476, 492, 505, 516, 529, 554) that use `await asyncio.sleep(0.5)` to wait for background tasks. These are timing-dependent and fail on slow CI machines.
**Fix:** Replace `asyncio.sleep()` waits with event-based synchronization. Use `asyncio.Event` to signal completion:
```python
done = asyncio.Event()
# Patch executor._background_tasks callback to set done when task completes
await asyncio.wait_for(done.wait(), timeout=5.0)
```
Alternatively, use `asyncio.gather()` or poll with `asyncio.wait_for()` and a short interval up to a 5s total timeout. The key is removing the hardcoded 0.5s.

### Pattern 23: Test assertions on types only
**What:** Some tests in `test_tools.py` assert only that a value is of a certain type (e.g. `assert isinstance(result, dict)`) without checking content. This misses regressions where the dict has the wrong keys or values.
**Fix:** Add content assertions for key fields: `assert result.get("status") == "completed"`, `assert "job_id" in result`, etc.

### Pattern 24: Scale-down logic zero test coverage
**What:** `pool/manager.py:run_health_checks()` contains scale-down logic (lines 181-189) with zero test coverage per the issue inventory.
**Fix:** Add tests in `test_pool.py` that set `scale_down_idle_timeout=0` and advance `engine._idle_since` to force the scale-down branch.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Constant-time string comparison | Custom loop | `hmac.compare_digest` | Timing oracle resistance |
| Async timeout | Manual flag/loop | `asyncio.wait_for()` | Correct cancellation semantics |
| Path canonicalization | `".." in str` check | `Path.resolve()` + startswith check | URL-encoded and symlink bypasses |
| Session ID validation | Ad-hoc filtering | Compiled `re.Pattern` + allow-list | Consistent, testable |
| SQL injection in event_types | Format-string | parameterized `?` placeholders (already used) | SQL injection prevention |

---

## Common Pitfalls

### Pitfall 1: release() try/finally breaks engine state machine
**What goes wrong:** If `reset_workspace()` raises, skipping `mark_idle()` is intentional in the original code (leave engine as BUSY to signal it's in bad state). The try/finally fix must still call `mark_idle()` because the pool must get the engine back regardless — but should additionally log a warning and optionally replace the engine on next health check.
**How to avoid:** In the `except` block of the try, set a flag on the engine (`engine._needs_replacement = True`) so the next health check replaces it.

### Pitfall 2: Pydantic v2 private attributes vs. model fields
**What goes wrong:** `_config_dir: Optional[Path] = None` is Pydantic v2 private attribute syntax. Pydantic v2 private attrs are declared with `PrivateAttr()`. The current declaration is just a class-level hint; Pydantic ignores it. Removing it is safe. Adding `inspect_mode` as a real field is safe as long as it has a default value.
**How to avoid:** Use `Field(default=False, exclude=True)` to add `inspect_mode` without it appearing in serialization output.

### Pitfall 3: TOCTOU fix changes create_session() semantics
**What goes wrong:** The TOCTOU fix for `get_or_create_default()` requires that `create_session()` can be called while holding `self._lock`. The current `create_session()` acquires `self._lock` internally. Using a reentrant lock (threading.RLock) or extracting a `_create_session_unlocked()` helper are both viable; RLock is simpler but `_create_session_unlocked()` is more explicit and easier to test.
**How to avoid:** Extract `_create_session_unlocked(session_id)` that performs the creation without acquiring the lock. Both `create_session()` and `get_or_create_default()` call it under `with self._lock`.

### Pitfall 4: Centralizing security in executor breaks check_code_impl
**What goes wrong:** `check_code_impl` calls `executor.execute()` with MATLAB code like `mcp_checkcode('/path/to/file.m')`. If executor-level security checks this string, `mcp_checkcode` is not a blocked function so it passes. However, the user's original code is written to a file first — it never goes through `executor.execute()` directly, so the security check on the mlint invocation is not the right place to check the user's code. The existing call to `security.check_code(code)` in `execute_code_impl` covers the user's code before it reaches the executor.
**How to avoid:** The centralized executor-level check is defense-in-depth, not the sole check. Keep the existing pre-executor check in `execute_code_impl`. The executor-level check catches all paths that skip the tool-level check (custom tools, discovery tools).

### Pitfall 5: psutil.cpu_percent() interval vs. blocking
**What goes wrong:** Calling `psutil.Process().cpu_percent(interval=1)` blocks for 1 second on the calling thread. The collector runs in the async event loop; blocking it for 1 second is harmful.
**How to avoid:** Prime the counter at `__init__` time (call with no interval, accept the 0.0 result) and then call with no interval on subsequent calls. Subsequent calls return the CPU percentage since the last call, which will be correct after the first priming call.

### Pitfall 6: Converting test methods to async breaks monkeypatch isolation
**What goes wrong:** `test_auth_middleware.py` uses `monkeypatch.setenv()`. Monkeypatch is sync-safe and works correctly in async test methods under pytest-asyncio. No special handling needed.
**How to avoid:** Just convert the method signature to `async def`; monkeypatch continues to work.

### Pitfall 7: wave ordering — pool fix must precede executor fix
**What goes wrong:** The executor background task fix (add `_background_tasks` set, add `shutdown()` method) and the lifespan shutdown fix are coupled. If the lifespan is changed to call `executor.shutdown()` before adding the method, a NameError occurs at startup.
**How to avoid:** Add `JobExecutor.shutdown()` in the same commit as the lifespan change that calls it.

---

## Code Examples

### Engine release with try/finally
```python
# Source: pool/manager.py — fixed release()
async def release(self, engine: MatlabEngineWrapper) -> None:
    """Return an engine to the pool, resetting workspace even if reset fails."""
    logger.info("Releasing engine %s — resetting workspace", engine.engine_id)
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, engine.reset_workspace)
    except Exception as exc:
        logger.warning(
            "[%s] reset_workspace failed on release: %s — returning engine to pool",
            engine.engine_id, exc,
        )
        engine._needs_replacement = True  # flag for next health check
    finally:
        engine.mark_idle()
        await self._available.put(engine)
        logger.info("Engine %s returned to pool (available=%d)",
                    engine.engine_id, self._available.qsize())
```

### Job state transition guard
```python
# Source: jobs/models.py — fixed mark_cancelled()
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING:   {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING:   {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED:    set(),
    JobStatus.CANCELLED: set(),
}

def mark_cancelled(self) -> None:
    """Transition job to CANCELLED state. No-op if already in terminal state."""
    if self.status not in _VALID_TRANSITIONS:
        return  # already terminal
    allowed = _VALID_TRANSITIONS[self.status]
    if JobStatus.CANCELLED not in allowed:
        logger.debug(
            "[%s] Ignoring cancel: invalid transition %s → CANCELLED",
            self.job_id[:8], self.status.name,
        )
        return
    self.status = JobStatus.CANCELLED
    self.completed_at = time.time()
```

### TOCTOU-safe get_or_create_default()
```python
# Source: session/manager.py — fixed TOCTOU
def _create_session_unlocked(self, *, session_id: Optional[str] = None) -> Session:
    """Create session assuming self._lock is already held."""
    if len(self._sessions) >= self._max_sessions:
        raise RuntimeError(
            f"Maximum number of sessions reached ({self._max_sessions})"
        )
    session_id = session_id or str(uuid.uuid4())
    temp_dir = self._base_temp / self._sanitize_session_id(session_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    session = Session(session_id=session_id, temp_dir=str(temp_dir))
    self._sessions[session_id] = session
    return session

def get_or_create_default(self) -> Session:
    """Return (or create) the default session for single-user stdio mode."""
    with self._lock:
        session = self._sessions.get(_DEFAULT_SESSION_ID)
        if session is not None:
            return session
        return self._create_session_unlocked(session_id=_DEFAULT_SESSION_ID)
```

### Engine start timeout
```python
# Source: pool/manager.py — fixed _start_engine_async()
async def _start_engine_async(self) -> MatlabEngineWrapper:
    """Start a single engine with timeout enforcement."""
    loop = asyncio.get_running_loop()
    engine = self._make_engine()
    self._all_engines.append(engine)
    timeout = float(self._pool_config.engine_start_timeout)
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, engine.start),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.error("[%s] Engine startup timed out after %.0fs", engine.engine_id, timeout)
        try:
            self._all_engines.remove(engine)
        except ValueError:
            pass
        raise RuntimeError(
            f"Engine {engine.engine_id} failed to start within {timeout:.0f}s"
        )
    return engine
```

### Background task tracking in JobExecutor
```python
# Source: jobs/executor.py — fixed task tracking
def __init__(self, pool, tracker, config, security=None, collector=None):
    ...
    self._security = security
    self._background_tasks: set[asyncio.Task] = set()

async def execute(self, session_id, code, temp_dir=None):
    # Security check — first operation, before acquiring any resource
    if self._security is not None:
        from matlab_mcp.security.validator import BlockedFunctionError
        try:
            self._security.check_code(code)
        except BlockedFunctionError as exc:
            return {
                "status": "failed",
                "error": {"type": "ValidationError", "message": f"Blocked: {exc}",
                          "matlab_id": None, "stack_trace": None},
            }
    ...
    # When promoting to async:
    task = asyncio.create_task(self._wait_for_completion(job, engine, future, temp_dir))
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)
    ...

async def shutdown(self) -> None:
    """Cancel and await all background tasks."""
    tasks = list(self._background_tasks)
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
```

---

## Wave Ordering

The 39 issues have the following dependency graph for wave ordering:

**Wave 1 — Security (6 issues, fully isolated)**
- Issue 1: Add `str2func`, `builtin`, `run` to default blocklist in `config.py:84-89`
- Issue 2: Centralize security.check_code() in JobExecutor.execute() (add security param to executor) — requires updating `server.py` wiring
- Issue 3: Discovery tools skip security validation — resolved by executor-level check (Wave 1)
- Issue 4: check_code_impl bypasses security validator — not a bypass of user code (mlint path); add a comment clarifying intentional design; the validator IS called on check_code tool's code param in server.py tool wrapper — actually this is currently NOT called; fix by adding call in check_code tool wrapper or via executor
- Issue 5: Session ID sanitization in filesystem paths (session/manager.py)
- Issue 20: Auth bypass when token is empty string (auth/middleware.py)
- Issue 21: Env var security override warning (config.py)

**Wave 2 — Pool/Engine resource safety (4 issues)**
- Issue 6: Engine leaked on release() if reset_workspace() raises (pool/manager.py:115-123)
- Issue 7: engine_start_timeout never enforced (pool/manager.py:54-59)
- Issue 8: Race in acquire() — re-poll after _scale_lock (pool/manager.py:96-105)
- Issue 22: Health check drains entire available queue (pool/manager.py:153-159) — health check already handles this correctly via drain-and-refill; the issue is that it makes the pool momentarily appear empty to other coroutines; fix with documentation/comment clarifying this is intentional, or add a flag
- Issue 24: Executor accesses engine._engine.workspace directly (executor.py:178,184,275) — add `set_workspace_var()` / `get_workspace_vars()` to MatlabEngineWrapper

**Wave 3 — Jobs/Session state machine (5 issues)**
- Issue 9: TOCTOU in get_or_create_default() (session/manager.py:122-128)
- Issue 10: Cancel/complete race in cancel_job_impl (tools/jobs.py:130-146) — resolved by state guards
- Issue 11: Job state transitions have no guards (jobs/models.py:77-109)
- Issue 12: Engine leaked if _inject_job_context() throws (jobs/executor.py:77-79) — already silently caught; fix by using new set_workspace_var() from Wave 2
- Issue 13: Background asyncio.Task objects fire-and-forget (jobs/executor.py:135-137)

**Wave 4 — Server/Config/Monitoring (12 issues)**
- Issues 14, 16-19, 26, 29-34 (server deprecations, Pydantic, YAML, CORS, monitoring queries, route dedup, psutil, dead config, etc.)

**Wave 5 — Tests (4 issues)**
- Issues 35-39 (asyncio.run() in tests, shared fixtures, scale-down coverage, asyncio.sleep races, type-only assertions)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.get_event_loop()` | `asyncio.get_running_loop()` | Python 3.10 deprecation, error in 3.12 | Must fix before Python 3.12 CI |
| Dynamic attrs on Pydantic models | Proper `Field()` declarations | Pydantic v2 | Silent failures in v2 without explicit extra="allow" |
| `psutil.Process().cpu_percent()` first-call returns 0.0 | Prime at init | psutil design | CPU metric always wrong on first sample |

---

## Open Questions

1. **Issue 3 (discovery tools skip security validation):** `list_toolboxes_impl` runs `ver` (no user input). `list_functions_impl` and `get_help_impl` run `help <validated_name>` where `_validate_matlab_name()` already sanitizes with an allow-list regex. These don't run arbitrary user code. The security review may be flagging that they bypass the validator, but they construct the MATLAB command internally. The correct fix is the executor-level check which will see the constructed command — a `help` or `ver` call will pass the blocklist check because none of those are blocked functions.
   - **Recommendation:** Executor-level check resolves this; no additional fix needed for discovery tools beyond adding a docstring note.

2. **Issue 23 (get_status() busy count uses queue arithmetic):** `busy = total - available` can go negative if `_available.qsize()` includes engines in STARTING state (they are in `_all_engines` but not yet in `_available`). The `max(busy, 0)` guard prevents negative values but hides the inaccuracy.
   - **Recommendation:** Replace with `sum(1 for e in self._all_engines if e.state == EngineState.BUSY)` which counts directly from engine state.

3. **Issue 25 (double-timeout pattern):** `executor.py:110-114` uses both `future.result(timeout=sync_timeout)` inside a `run_in_executor` AND `asyncio.wait_for(..., timeout=sync_timeout + 1)`. The inner timeout fires first (by 1 second), so the outer is unreachable. The outer exists as a safety net for if `future.result()` ignores the timeout parameter.
   - **Recommendation:** Keep both but document why the outer timeout is +1 second. Alternatively, remove the inner timeout and rely solely on `asyncio.wait_for`. The MATLAB Engine API's `future.result(timeout=N)` does honor the timeout, so the inner timeout is sufficient; the outer is genuinely redundant. Remove the outer `wait_for` wrapper and just call `await loop.run_in_executor(None, lambda: future.result(timeout=sync_timeout))` with a note that asyncio cancellation won't interrupt the thread (this is a known asyncio limitation with thread executors).

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — all fixes are code changes to existing Python source files; no new tools or services required).

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Issue # | Behavior Fixed | Test Type | Automated Command | Tests Exist? |
|---------|---------------|-----------|-------------------|-------------|
| 1 | str2func/builtin/run blocked | unit | `pytest tests/test_security.py -x` | Partial (new tests needed) |
| 2 | Custom tools call check_code | unit | `pytest tests/test_tools_custom.py tests/test_tools.py -x` | Partial |
| 3 | Discovery tools run via executor check | unit | `pytest tests/test_tools_discovery.py -x` | Partial |
| 4 | check_code_impl MATLAB call not user-bypassed | unit | `pytest tests/test_tools.py -x` | Partial |
| 5 | Session ID sanitized in path | unit | `pytest tests/test_session.py -x` | Partial |
| 6 | Engine not leaked on reset failure | unit | `pytest tests/test_pool.py -x` | Partial |
| 7 | engine_start_timeout enforced | unit | `pytest tests/test_pool.py -x` | Partial |
| 8 | acquire() re-polls after scale_lock | unit | `pytest tests/test_pool.py -x` | Partial |
| 9 | TOCTOU in get_or_create_default | unit | `pytest tests/test_session.py -x` | Partial |
| 10 | Cancel/complete race guarded | unit | `pytest tests/test_tools_jobs.py -x` | Partial |
| 11 | Job state transition guards | unit | `pytest tests/test_jobs.py -x` | Partial |
| 12 | Engine not leaked on inject failure | unit | `pytest tests/test_executor_extra.py -x` | Partial |
| 13 | Background tasks tracked | unit | `pytest tests/test_executor_extra.py -x` | Partial |
| 14 | Monitoring shutdown has timeout | unit | `pytest tests/test_server.py -x` | Partial |
| 15 | eval in blocked list tested | unit | `pytest tests/test_security.py::TestCheckCodeBlockedFunctions -x` | NO — Wave 0 gap |
| 16 | get_running_loop used | unit | `pytest tests/test_server.py -x` | Partial |
| 17 | _get_session_id exceptions not swallowed | unit | `pytest tests/test_server.py -x` | Partial |
| 18 | _inspect_mode as proper field | unit | `pytest tests/test_config.py -x` | Partial |
| 19 | CORS origins configurable | unit | `pytest tests/test_server.py -x` | Partial |
| 20 | Empty token → 401 | unit | `pytest tests/test_auth_middleware.py -x` | NO — Wave 0 gap |
| 21 | Security disable warning logged | unit | `pytest tests/test_config.py -x` | Partial |
| 22 | Health check pool drain safe | unit | `pytest tests/test_pool.py -x` | Partial |
| 23 | get_status() busy count accurate | unit | `pytest tests/test_pool.py -x` | Partial |
| 24 | Executor uses wrapper API, not _engine | unit | `pytest tests/test_executor_extra.py -x` | Partial |
| 25 | Double-timeout documented/removed | unit | `pytest tests/test_executor_extra.py -x` | Partial |
| 26 | proactive_warmup_threshold removed | unit | `pytest tests/test_config.py -x` | Partial |
| 27 | api_history/events query params clamped | unit | `pytest tests/test_monitoring_dashboard.py -x` | Partial |
| 28 | get_history/get_aggregates have LIMIT | unit | `pytest tests/test_monitoring_store.py -x` | Partial |
| 29 | Static file path uses resolve() | unit | `pytest tests/test_monitoring_dashboard.py -x` | Partial |
| 30 | Duplicate routes removed | unit | `pytest tests/test_monitoring_routes.py -x` | Partial |
| 31 | total_errors_24h uses direct count | unit | `pytest tests/test_monitoring_tools.py -x` | Partial |
| 32 | cpu_percent primed at init | unit | `pytest tests/test_monitoring_collector.py -x` | Partial |
| 33 | YAML parse error → ValueError | unit | `pytest tests/test_config.py -x` | Partial |
| 34 | _config_dir removed | unit | `pytest tests/test_config.py -x` | Partial |
| 35 | asyncio.run() → async def in tests | unit | `pytest tests/test_auth_middleware.py -x` | Fixed by conversion |
| 36 | _make_mock_pool in conftest | unit | `pytest tests/ -x` | Wave 0 gap |
| 37 | Scale-down logic covered | unit | `pytest tests/test_pool.py -x` | NO — Wave 0 gap |
| 38 | asyncio.sleep(0.5) replaced | unit | `pytest tests/test_executor_extra.py -x` | Fixed inline |
| 39 | Tests assert content not just types | unit | `pytest tests/test_tools.py -x` | Fixed inline |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps (tests that must be added before implementing the issues they cover)
- [ ] `tests/test_security.py` — add `test_blocks_eval`, `test_blocks_str2func`, `test_blocks_builtin`, `test_blocks_run` to cover issue 1 and issue 15
- [ ] `tests/test_auth_middleware.py` — add `test_empty_token_configured_rejects_empty_bearer` to cover issue 20
- [ ] `tests/conftest.py` — add shared `mock_pool` fixture to cover issue 36
- [ ] `tests/test_pool.py` — add `TestScaleDown` class to cover issue 37

---

## Sources

### Primary (HIGH confidence)
- Direct source code inspection — all findings are from reading the actual code at the exact line references provided in the CONTEXT.md issue inventory
- Python asyncio docs — `get_running_loop()` deprecation: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.get_event_loop
- psutil docs — `cpu_percent()` first-call behavior: https://psutil.readthedocs.io/en/latest/#psutil.Process.cpu_percent
- Pydantic v2 docs — private attributes: https://docs.pydantic.dev/latest/concepts/models/#private-model-attributes

### Secondary (MEDIUM confidence)
- asyncio task tracking patterns — standard Python async pattern; verified by inspection of existing executor code

---

## Metadata

**Confidence breakdown:**
- Security fixes: HIGH — code is read directly; fixes are straightforward pattern changes
- Pool/engine fixes: HIGH — resource management patterns are standard Python; code is fully inspected
- Jobs/session fixes: HIGH — state machine guard pattern is well-established; TOCTOU fix is standard threading pattern
- Server/config fixes: HIGH — deprecation fixes are mechanical; Pydantic v2 behavior verified
- Monitoring fixes: HIGH — SQL patterns are directly inspectable; dashboard code is fully read
- Test fixes: HIGH — test code is fully read; patterns are standard pytest-asyncio

**Research date:** 2026-04-03
**Valid until:** 2026-05-03 (stable codebase — no fast-moving external dependencies)
