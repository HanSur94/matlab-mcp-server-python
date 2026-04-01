# Architecture

**Analysis Date:** 2026-04-01

## Pattern Overview

**Overall:** Multi-layered MCP server with elastic resource pooling, async job orchestration, and session isolation.

**Key Characteristics:**
- **FastMCP framework** — Exposes tools via the Model Context Protocol
- **Async-first design** — Hybrid sync/async execution with background job promotion
- **Resource pooling** — Elastic pool of MATLAB engines (scales 2-10+ on demand)
- **Session isolation** — Per-session workspaces and temporary directories
- **Event-driven monitoring** — Real-time metrics collection with retention-based cleanup

## Layers

**Server Layer:**
- Purpose: Top-level FastMCP server initialization, lifespan management, tool registration
- Location: `src/matlab_mcp/server.py`
- Contains: `MatlabMCPServer` state container, `create_server()` factory, tool decorators
- Depends on: All subsystems (pool, executor, sessions, security, monitoring)
- Used by: CLI entry point (`main()`)

**Engine Pool Layer:**
- Purpose: Manage lifecycle of MATLAB engine instances with auto-scaling and health checks
- Location: `src/matlab_mcp/pool/`
- Contains: 
  - `EnginePoolManager` — pool state, acquire/release, scale-up/down
  - `MatlabEngineWrapper` — individual engine lifecycle (STOPPED → STARTING → IDLE ↔ BUSY)
- Depends on: MATLAB Engine API (via lazy import)
- Used by: `JobExecutor`

**Job Execution Layer:**
- Purpose: Orchestrate job lifecycle from creation through completion
- Location: `src/matlab_mcp/jobs/`
- Contains:
  - `JobExecutor` — coordinates pool acquisition, code execution, result building
  - `JobTracker` — thread-safe registry of all jobs with retention-based cleanup
  - `Job` model — state machine with terminal states (COMPLETED, FAILED, CANCELLED)
- Depends on: Engine Pool, Security Validator
- Used by: Core tools (`execute_code`, `check_code`)

**Session Layer:**
- Purpose: Manage user sessions with workspace isolation and idle timeout cleanup
- Location: `src/matlab_mcp/session/manager.py`
- Contains: `SessionManager` managing `Session` objects (temp_dir, created_at, last_active)
- Depends on: Config
- Used by: Server layer for temp_dir routing

**Security Layer:**
- Purpose: Validate MATLAB code against blocked functions and sanitize filenames
- Location: `src/matlab_mcp/security/validator.py`
- Contains: `SecurityValidator` with precompiled regex patterns, string-literal stripping
- Depends on: Config
- Used by: Core execution tools

**Tools Layer:**
- Purpose: Implement MCP tool handlers (execute, check, discover, files, jobs, monitoring)
- Location: `src/matlab_mcp/tools/`
- Contains:
  - `core.py` — execute_code, check_code, get_workspace
  - `discovery.py` — list_toolboxes, list_functions, get_help
  - `files.py` — upload_data, delete_file, list_files, read_script, read_data, read_image
  - `jobs.py` — job lifecycle tools (get_status, get_result, cancel, list)
  - `admin.py` — get_pool_status
  - `custom.py` — load and expose user-defined MATLAB functions
  - `monitoring.py` — server metrics, health, error logs
- Depends on: Executor, Tracker, Security, Sessions, Pool, Output Formatter
- Used by: Server layer (tool registration)

**Output Formatting Layer:**
- Purpose: Format MATLAB execution results for MCP responses
- Location: `src/matlab_mcp/output/`
- Contains:
  - `formatter.py` — text truncation/saving, variable summarization, file listings
  - `plotly_convert.py` — MATLAB figure → Plotly JSON conversion
  - `plotly_style_mapper.py` — line styles, colors, markers, legends
  - `thumbnail.py` — static PNG thumbnails for figures
- Depends on: Config
- Used by: `JobExecutor` for result formatting

**Monitoring Layer:**
- Purpose: Collect metrics and provide health/diagnostic views
- Location: `src/matlab_mcp/monitoring/`
- Contains:
  - `collector.py` — in-memory counters, ring buffer for execution times, event recording
  - `store.py` — SQLite persistence with periodic pruning
  - `health.py` — health status detection (healthy/degraded/unhealthy)
  - `dashboard.py` — HTTP/SSE UI with Starlette
  - `routes.py` — monitoring HTTP endpoints
- Depends on: Config, Pool, Tracker, Sessions
- Used by: Server layer (background sampling task), dashboard UI

**Configuration Layer:**
- Purpose: Load, validate, and apply environment overrides
- Location: `src/matlab_mcp/config.py`
- Contains: Pydantic models (ServerConfig, PoolConfig, ExecutionConfig, SecurityConfig, etc.), `load_config()`, environment variable override logic
- Depends on: None (external: yaml, pydantic)
- Used by: Server factory, all subsystems

## Data Flow

**Code Execution Flow:**

1. **Tool invocation** → `execute_code()` tool handler in server layer
2. **Session routing** → Determine session_id (from context or defaults to "default")
3. **Temp dir setup** → Get or create session temp directory
4. **Security check** → `SecurityValidator.check_code()` blocks malicious patterns
5. **Job creation** → `JobTracker.create_job()` registers PENDING job
6. **Engine acquisition** → `EnginePoolManager.acquire()` (blocks if at max and all busy)
7. **Job context injection** → Set `_mcp_job_info` in MATLAB workspace with job_id, session_id
8. **Background execution** → `engine.execute(code, background=True)` returns Future
9. **Sync/async decision** → Wait up to `sync_timeout` seconds
   - **Sync path:** Future completes quickly → return result inline, job marked COMPLETED
   - **Async path:** Timeout → job stays PENDING, background task tracks it
10. **Background task monitoring** → Polls future, catches errors, collects output
11. **Result building** → Format stdout/stderr, extract variables, convert figures to Plotly
12. **Engine release** → Return to available pool
13. **Response delivery** → Return job_id and optional inline results

**Session Cleanup Flow:**

1. **Background loop** (every 60s) → `SessionManager.cleanup_expired()`
2. **Idle detection** → Sessions with idle_seconds > session_timeout marked for removal
3. **Active job check** → Skip cleanup if session has running jobs
4. **Temp directory deletion** → Remove session temp dir recursively
5. **Job pruning** → `JobTracker.prune()` removes jobs older than retention_seconds

**Health Check Flow:**

1. **Background loop** (every health_check_interval) → `EnginePoolManager.run_health_checks()`
2. **Liveness check** → Call `engine.is_alive` property
3. **Dead engine replacement** → If not alive, stop and replace with new engine
4. **Status update** → Metrics collector records state

**State Management:**

- **Pool state:** In-memory asyncio.Queue for available engines, list of all engines
- **Job state:** Thread-safe dict keyed by job_id, retained for 24 hours after terminal state
- **Session state:** Thread-safe dict keyed by session_id, idle timeout of 1 hour default
- **Monitoring state:** In-memory counters + SQLite for historical metrics (7 days default)

## Key Abstractions

**MatlabEngineWrapper:**
- Purpose: Single MATLAB engine instance with lifecycle state machine
- Examples: `src/matlab_mcp/pool/engine.py`
- Pattern: State enum (STOPPED → STARTING → IDLE ↔ BUSY), lazy MATLAB Engine API import, health check via `is_alive` property

**Job:**
- Purpose: Represents one MATLAB code execution with full lifecycle tracking
- Examples: `src/matlab_mcp/jobs/models.py`
- Pattern: Dataclass with state transition methods (mark_running, mark_completed, mark_failed, mark_cancelled), Optional result/error fields

**Session:**
- Purpose: User session context with workspace isolation
- Examples: `src/matlab_mcp/session/manager.py`
- Pattern: Dataclass with session_id → temp_dir mapping, last_active timestamp for idle detection

**SecurityValidator:**
- Purpose: Code validation before execution
- Examples: `src/matlab_mcp/security/validator.py`
- Pattern: Precompiled regex patterns for blocked functions, string-literal stripping to avoid false positives, configurable blocklist

**ResultFormatter:**
- Purpose: Transform raw execution results into MCP response format
- Examples: `src/matlab_mcp/output/formatter.py`
- Pattern: Text truncation with optional file save, variable summarization, figure attachment handling

**MetricsCollector:**
- Purpose: Record events and sample system metrics
- Examples: `src/matlab_mcp/monitoring/collector.py`
- Pattern: Event queue for async store writes, ring buffer for execution times, periodic sampling task

## Entry Points

**CLI Entry Point:**
- Location: `src/matlab_mcp/server.py::main()`
- Triggers: `python -m matlab_mcp` or installed script
- Responsibilities: Parse CLI args (--config, --transport, --inspect), load config, set up logging, create server, run FastMCP in selected transport mode

**Tool Entry Points (via FastMCP decorators):**
- Location: `src/matlab_mcp/server.py::create_server()` — all tools registered at lines 391-679
- Triggers: MCP client calls (e.g., `execute_code`, `get_workspace`, `upload_data`)
- Responsibilities: Deserialize request, route to implementation function, serialize response

**Background Tasks (in lifespan):**
- Location: `src/matlab_mcp/server.py::lifespan()` at lines 158-363
- Triggers: Server startup
- Responsibilities: 
  - Health check loop (line 267) — every health_check_interval
  - Cleanup loop (line 284) — every 60 seconds
  - Metrics sampling (line 237) — every sample_interval
  - HTTP monitoring server (line 257, stdio transport only)

## Error Handling

**Strategy:** Try-catch at multiple layers with event recording and graceful degradation.

**Patterns:**

1. **Code Security Violations** → `BlockedFunctionError` caught in `execute_code_impl()` → return status="failed" with error dict
2. **MATLAB Execution Errors** → Caught in background task, stored in Job.error dict → retriable via `get_job_result`
3. **Engine Startup Failures** → Logged and tracked as metrics event → continue with reduced pool capacity
4. **Health Check Failures** → Dead engines replaced with new ones, tracked in metrics
5. **Session/Job Cleanup** → Exceptions logged but don't stop loop (asyncio.gather with return_exceptions=True)
6. **Configuration Validation** → Pydantic model validators raise on invalid pool constraints
7. **File Operations** → Path traversal blocked via `SecurityValidator.sanitize_filename()`

## Cross-Cutting Concerns

**Logging:** 
- Framework: Python logging module (stdlib)
- Pattern: Logger per module with `logger = logging.getLogger(__name__)`, configured via `--log-level` (debug/info/warning/error)
- Files: Dual output to stderr + file (`config.server.log_file` defaults to `./logs/server.log`)

**Validation:**
- Code validation: `SecurityValidator.check_code()` with precompiled regex patterns
- File validation: `SecurityValidator.sanitize_filename()` prevents path traversal
- Config validation: Pydantic validators in `AppConfig.validate_pool()` (min_engines ≤ max_engines)
- MATLAB functions: Blocked function list in config (system, eval, perl, python, etc.)

**Authentication:**
- Transport-specific:
  - **stdio** — No auth (assumes single trusted user)
  - **SSE** — Optional proxy auth via reverse proxy (config.security.require_proxy_auth)
- No built-in token/API key auth (relying on deployment layer)

**Monitoring & Telemetry:**
- Event recording: Fire-and-forget to async store writes (MetricsCollector.record_event)
- Metrics types: Counters (completed_total, failed_total), ring buffer (execution_times), system stats (memory_mb, cpu_percent)
- Dashboard: Real-time HTML UI with Plotly charts (stdio transport on http://127.0.0.1:8766/dashboard by default)
- Persistence: SQLite at config.monitoring.db_path (./monitoring/metrics.db), pruned after retention_days (7 default)

---

*Architecture analysis: 2026-04-01*
