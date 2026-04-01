# Codebase Concerns

**Analysis Date:** 2026-04-01

## Tech Debt

**Heuristic-based code sanitization in security validator:**
- Issue: The security blocking mechanism uses regex-based string literal stripping (`_strip_string_literals()`) rather than a full MATLAB parser. This is a best-effort heuristic that may miss edge cases.
- Files: `src/matlab_mcp/security/validator.py` (lines 52-73, 75-115)
- Impact: A determined user could potentially bypass function blocking by embedding blocked calls in string literals or using complex syntax not covered by the regex patterns. The codebase acknowledges this is "best-effort" with "common cases tested."
- Fix approach: Consider integrating a MATLAB syntax parser or use MATLAB's built-in code checking API (`mlint`/`checkcode`) for more robust validation. Alternatively, document the limitations and recommend the `auto_check_before_execute` feature be enabled for critical deployments.

**Workspace variable injection failures are silently ignored:**
- Issue: When injecting `__mcp_job_id__` and `__mcp_temp_dir__` into the MATLAB workspace, exceptions are caught and only logged at DEBUG level (`src/matlab_mcp/jobs/executor.py` lines 177-186).
- Files: `src/matlab_mcp/jobs/executor.py` (lines 165-186)
- Impact: If injection fails (e.g., workspace access issues), jobs continue execution without these critical context variables. MATLAB helper functions that depend on `__mcp_temp_dir__` will fail silently.
- Fix approach: Escalate failures to at least WARNING level. Consider whether job execution should be aborted if context injection fails, or make helper functions more resilient to missing variables.

**Broad exception catching in executor and tools:**
- Issue: Multiple locations catch generic `Exception` rather than specific exceptions, making it harder to distinguish between operational errors and programming bugs.
- Files: `src/matlab_mcp/jobs/executor.py` (lines 91-105, 139-153, 223-235, 239-240, 269-270, 278-279), `src/matlab_mcp/tools/files.py` (multiple locations)
- Impact: Swallows unexpected errors that should be surfaced. Makes debugging harder; exceptions are logged but may not reach the appropriate handlers.
- Fix approach: Audit exception types and catch specific exceptions (e.g., `OSError`, `IOError`, `TimeoutError`) rather than `Exception`. Reserve `Exception` catches only for truly unexpected cases.

**Reverse path traversal check insufficient:**
- Issue: Filename validation in `sanitize_filename()` checks for `".."` in the filename, but the safe filename regex `[a-zA-Z0-9._-]` would reject `..` anyway.
- Files: `src/matlab_mcp/security/validator.py` (lines 123-154)
- Impact: The `".."` check is redundant but defensive. Current implementation is adequate, but the redundancy suggests belt-and-suspenders thinking that should be clarified.
- Fix approach: Keep the explicit check for clarity; it documents the intent. Consider adding a test case for path traversal attempts.

**Metrics collector pending events may be lost:**
- Issue: The metrics collector maintains a `_pending_events` queue when no event loop is running, but there's no flush mechanism to write these to the store when the loop becomes available.
- Files: `src/matlab_mcp/monitoring/collector.py` (lines 73-74, 144-146)
- Impact: If events are recorded before the async loop starts, they stay in the queue and are never persisted unless explicitly flushed.
- Fix approach: Add an explicit flush method in `start_sampling()` or the server lifespan to drain pending events. Document when events may be lost.

## Known Bugs

**Memory leak in failed engine startup:**
- Issue: In `EnginePoolManager.acquire()`, if scale-up fails to start an engine, the exception from `_start_engine_async()` is caught but the engine is still added to `_all_engines` before startup completes.
- Files: `src/matlab_mcp/pool/manager.py` (lines 95-105)
- Impact: If engine startup raises an exception in `_start_engine_async()`, the partially-initialized engine remains in `_all_engines` with `_engine = None`, potentially leading to state inconsistencies or memory leaks.
- Trigger: Concurrent scale-up attempts with MATLAB engine startup failures.
- Workaround: The health check loop may detect and replace failed engines, but this is not guaranteed on the first occurrence.

**Engine health check may block pool acquisition indefinitely:**
- Issue: In `EnginePoolManager.run_health_checks()`, all idle engines are drained from the queue synchronously (lines 153-159). If an engine's health check hangs, the entire pool becomes temporarily unavailable.
- Files: `src/matlab_mcp/pool/manager.py` (lines 143-216)
- Impact: A hanging MATLAB process can freeze the pool health check, blocking new work acquisitions temporarily.
- Trigger: MATLAB engine process deadlock or unresponsive state during health check interval.
- Workaround: Health checks run in a background task with a default 60-second interval; worst case is a 60-second freeze.

**Figure extraction code injection vulnerability (low risk):**
- Issue: Figure extraction in `_build_result()` uses string formatting to construct MATLAB code with the job_id and escaped directory path, but the escaping may be incomplete.
- Files: `src/matlab_mcp/jobs/executor.py` (lines 283-307)
- Impact: A job_id containing special MATLAB characters could potentially inject code. Job IDs are UUIDs generated by the server, not user-controlled, so risk is very low.
- Trigger: Would require compromising the server's job ID generation or UUID library.
- Workaround: Job IDs are server-generated UUIDs; user input cannot influence this.

## Security Considerations

**SSE transport without proxy authentication:**
- Risk: When using SSE (Server-Sent Events) transport without `require_proxy_auth=true`, the server is exposed directly to the network without authentication. Anyone with network access can execute MATLAB code.
- Files: `src/matlab_mcp/server.py` (lines 171-178)
- Current mitigation: A warning is logged at startup if this misconfiguration is detected.
- Recommendations:
  1. Make `require_proxy_auth` default to `true` when `transport="sse"`.
  2. Add validation in `config.py` to raise an error on startup if SSE + no proxy auth is detected.
  3. Document the security implications prominently in README and config examples.

**Blocked functions list includes `eval` but not `evalc`/`evalin` variants clearly:**
- Risk: The security blocking list includes `eval`, `feval`, `evalc`, `evalin`, and `assignin`, but malicious code could use undocumented or alternative evaluation functions.
- Files: `src/matlab_mcp/config.py` (lines 82-88), `src/matlab_mcp/security/validator.py`
- Current mitigation: The list covers the most common evaluation functions. The regex is applied both as function call and command syntax.
- Recommendations:
  1. Maintain a living document of tested bypass attempts and ensure the blocked list is updated.
  2. Consider adding `getenv`, `setenv` if external tool execution through environment variables is a concern.
  3. Enable `code_checker.auto_check_before_execute` by default for SSE deployments.

**File upload filename validation is strict but not bulletproof:**
- Risk: While filename validation is good, symbolic links or mounted filesystems could still lead to unintended file access.
- Files: `src/matlab_mcp/tools/files.py` (lines 26-100)
- Current mitigation: Filenames are restricted to `[a-zA-Z0-9._-]` and path traversal is blocked. All file operations use `Path` from `pathlib` which is safer than string concatenation.
- Recommendations:
  1. Add a check to ensure the resolved path stays within `session_temp_dir` after all symlink resolution.
  2. Consider using `Path.resolve()` and verifying the path is still under the temp directory.

**Missing authentication/authorization in stdio mode:**
- Risk: When running in stdio mode (default), any process with access to stdin/stdout can control the server. For shared systems or container environments, this could be a security issue.
- Files: `src/matlab_mcp/server.py` (lines 688-799)
- Current mitigation: The `--inspect` mode prevents MATLAB startup, limiting impact in development.
- Recommendations:
  1. Document that stdio mode should only be used in trusted environments or with process-level isolation.
  2. Add a command-line flag to require a token/secret for stdio transport.

## Performance Bottlenecks

**String literal stripping for every code check:**
- Problem: Every time `check_code()` is called, the entire code string is processed line-by-line through three regex operations.
- Files: `src/matlab_mcp/security/validator.py` (lines 52-73)
- Cause: The regex operations are precompiled (good optimization), but the string processing is not cached or optimized for large files.
- Improvement path: Cache the results of sanitization for identical code strings. Use a bounded LRU cache with a timeout. Alternatively, push the sanitization into MATLAB's native code checker.

**Workspace variable serialization can be expensive:**
- Problem: After execution, all workspace variables are serialized with `_safe_serialize()`, which recursively traverses large data structures.
- Files: `src/matlab_mcp/jobs/executor.py` (lines 272-279, 341-372)
- Cause: No size limits or depth limits on the recursive serialization; large matrices or nested structures could cause memory spikes.
- Improvement path: 
  1. Add a size threshold and truncate large variables to a summary (e.g., "array of shape [1000, 1000]").
  2. Add recursion depth limits.
  3. Consider a streaming JSON writer for large results.

**Health check blocks the entire pool queue:**
- Problem: During `run_health_checks()`, all idle engines are removed from the queue synchronously, making the pool unavailable during health checks.
- Files: `src/matlab_mcp/pool/manager.py` (lines 143-216)
- Cause: The implementation drains the queue, checks engines, then re-adds them. This is a simple algorithm but blocks on I/O.
- Improvement path: 
  1. Use a separate background task for health checks that doesn't block acquisitions.
  2. Check engines in parallel with a timeout.
  3. Return engines to the queue incrementally as they pass health checks.

**Figure conversion runs synchronously in the executor:**
- Problem: Extracting and converting figures happens synchronously in `_build_result()`, blocking the job completion path.
- Files: `src/matlab_mcp/jobs/executor.py` (lines 283-320)
- Cause: `engine.execute(extract_code, background=False)` is blocking.
- Improvement path: 
  1. Move figure extraction to a background task after the job completes.
  2. Add a configurable timeout for figure extraction to prevent hangs.
  3. Return results without figures first, then update them asynchronously.

## Fragile Areas

**Job tracker with no lock on job access:**
- Files: `src/matlab_mcp/jobs/tracker.py`
- Why fragile: The job tracker stores jobs in a dict but doesn't use locks for concurrent access. Multiple threads/tasks could modify job state simultaneously.
- Safe modification: Always access jobs through a single-threaded executor or add explicit locks around job state mutations. Verify all job state transitions are atomic.
- Test coverage: Check for race conditions in `prune()` and `list_jobs()` when jobs are modified concurrently.

**Engine state transitions are not atomic:**
- Files: `src/matlab_mcp/pool/engine.py` (lines 208-215)
- Why fragile: `mark_busy()` and `mark_idle()` simply set `_state` without synchronization. If the pool is multi-threaded, state could become inconsistent.
- Safe modification: Use locks or atomic operations. Consider moving to `EnginePoolManager` to control all state transitions.
- Test coverage: Test concurrent state transitions with multiple threads acquiring/releasing engines.

**Session cleanup and job checking race condition:**
- Files: `src/matlab_mcp/session/manager.py` (lines 158-200)
- Why fragile: `cleanup_expired()` collects candidates under lock, then checks `has_active_jobs_fn` without the lock. A job could transition between the check and destruction.
- Safe modification: Pass the entire job check inside the lock, or use versioned job lists.
- Test coverage: Test cleanup while jobs are being created/completed.

**Monitoring store WAL mode may leave orphaned WAL files:**
- Files: `src/matlab_mcp/monitoring/store.py` (lines 73-83)
- Why fragile: SQLite WAL mode creates additional files (`.wal`, `.shm`) that aren't cleaned up if the process is killed abruptly.
- Safe modification: Document the requirement to keep WAL files together. Consider periodic checkpoints or using regular journal mode if simpler cleanup is needed.
- Test coverage: Test ungraceful shutdown and verify WAL files don't accumulate.

## Scaling Limits

**Pool max_engines hard-coded to 10 by default:**
- Current capacity: 10 engines max
- Limit: For workloads with >10 concurrent jobs, the pool is at max capacity and requests queue.
- Scaling path: Make `max_engines` easily configurable via environment variable (already supported via `MATLAB_MCP_POOL_MAX_ENGINES`). Document that MATLAB license concurrency limits may apply.

**Session storage uses filesystem-based temp directories:**
- Current capacity: Limited by disk space and filesystem inode count.
- Limit: If sessions are not cleaned up (e.g., if cleanup is disabled), disk usage grows linearly with session count.
- Scaling path: 
  1. Implement automatic cleanup on session timeout.
  2. Monitor disk usage and warn when threshold is exceeded.
  3. Consider in-memory session storage for small deployments or cloud environments.

**Metrics store SQLite database may become I/O-bound:**
- Current capacity: Default retention of 7 days with 10-second sampling = ~60,480 metric snapshots.
- Limit: SQLite can handle millions of rows but write concurrency is limited. At high load (many jobs), the store could fall behind.
- Scaling path: 
  1. Use batching (already done) but increase batch size.
  2. Consider time-series database alternatives (e.g., InfluxDB, Prometheus) for production.
  3. Add async queue with backpressure for metric writes.

**Job tracker retention with unlimited job count:**
- Current capacity: `job_retention_seconds` defaults to 86400 (1 day). Without a max_jobs limit, memory grows with job count.
- Limit: If the server runs 1000s of jobs per day, the tracker accumulates job objects indefinitely.
- Scaling path: 
  1. Add a `max_jobs` retention limit in addition to time-based pruning.
  2. Periodically compress old job records to summaries.

## Dependencies at Risk

**fastmcp >= 2.0.0, < 3.0.0 may break at major version:**
- Risk: Pinned to `>=2.0.0,<3.0.0`. Future `3.0.0` release could have breaking changes.
- Impact: The server cannot update to major versions of fastmcp without code changes.
- Migration plan: 
  1. Add tests that exercise fastmcp API surface.
  2. Monitor fastmcp releases and test with RC versions before they're released.
  3. Keep codebase compatible with at least the last two minor versions of fastmcp.

**Pillow >= 9.0.0 without upper bound:**
- Risk: No upper bound on Pillow version. Future versions could deprecate image format handling.
- Impact: Large jumps in Pillow versions might require thumbnail/image processing code updates.
- Migration plan: Periodically test with newer Pillow versions. Set a reasonable upper bound (e.g., `<14.0.0`) once stable.

**plotly >= 5.9.0 version compatibility:**
- Risk: Plotly is a large, frequently-updated library. No upper bound specified.
- Impact: The figure conversion pipeline (`plotly_style_mapper.py`, `plotly_convert.py`) could break with new Plotly versions.
- Migration plan: 
  1. Test plotly updates before pushing to production.
  2. Monitor plotly changelog for breaking API changes.
  3. Add integration tests for figure rendering with a locked plotly version.

**pyyaml >= 6.0 potential security issue with unsafe_load:**
- Risk: If code ever uses `yaml.unsafe_load()` instead of `yaml.safe_load()`, arbitrary code execution is possible.
- Impact: Configuration files could be exploited to run malicious Python code.
- Migration plan: 
  1. Ensure `yaml.safe_load()` is always used (confirmed in `config.py` line 240).
  2. Add a linter rule or pre-commit hook to catch uses of `unsafe_load()`.

## Test Coverage Gaps

**Pool health check race conditions not tested:**
- What's not tested: Concurrent `acquire()` and `run_health_checks()` operations.
- Files: `src/matlab_mcp/pool/manager.py`
- Risk: The queue draining and repopulating could have race conditions under concurrent load.
- Priority: HIGH

**Security validator edge cases:**
- What's not tested: Strings containing MATLAB comments, quotes in string literals, nested quotes, or Unicode characters.
- Files: `src/matlab_mcp/security/validator.py`
- Risk: Malicious code could bypass the heuristic string stripping.
- Priority: HIGH

**Session cleanup with active jobs:**
- What's not tested: Cleanup behavior when jobs complete between the idle check and destruction.
- Files: `src/matlab_mcp/session/manager.py`
- Risk: Sessions could be destroyed while jobs are transitioning, causing orphaned data.
- Priority: MEDIUM

**Executor result building with large workspaces:**
- What's not tested: Serialization of very large arrays (1GB+) or deeply nested structures (100+ levels).
- Files: `src/matlab_mcp/jobs/executor.py`
- Risk: Memory exhaustion or stack overflow during serialization.
- Priority: MEDIUM

**File upload with special characters:**
- What's not tested: Filenames with Unicode characters, spaces, or other edge cases that pass the regex but might fail on certain filesystems.
- Files: `src/matlab_mcp/tools/files.py`
- Risk: File operations could fail silently or create unexpected behavior.
- Priority: LOW

**Monitoring store with many concurrent writes:**
- What's not tested: Multiple jobs recording metrics simultaneously under load.
- Files: `src/matlab_mcp/monitoring/store.py`
- Risk: SQLite contention could cause metric loss or slow performance.
- Priority: MEDIUM

## Missing Critical Features

**No rate limiting or request throttling:**
- Problem: Any authenticated client can submit unlimited jobs, potentially DOS-ing the server.
- Blocks: Deploying in production without external rate limiting.
- Solution approach: Add per-session rate limiting (jobs per minute), configurable via config. Consider token-bucket or sliding-window algorithms.

**No request timeout enforcement:**
- Problem: Clients that submit code and disconnect could leave jobs hanging.
- Blocks: Server resource exhaustion in multi-client scenarios.
- Solution approach: Add configurable request timeout and automatically cancel jobs if client disconnects.

**No audit logging of executed code:**
- Problem: For compliance/security audits, there's no record of what code was executed by whom.
- Blocks: Meeting security audit requirements in regulated industries.
- Solution approach: Add optional `audit_log` feature to record executed code, user, timestamp to a separate log file or database.

**No graceful degradation when MATLAB is unavailable:**
- Problem: If MATLAB fails to start (e.g., license issue), the entire server fails.
- Blocks: Some operations that don't require MATLAB (file upload, discovery) still fail.
- Solution approach: Decouple MATLAB availability from server startup. Allow non-MATLAB tools to work even if pool startup fails. Current `--inspect` mode partially addresses this.

---

*Concerns audit: 2026-04-01*
