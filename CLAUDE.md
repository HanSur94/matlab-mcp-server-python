<!-- GSD:project-start source:PROJECT.md -->
## Project

**MATLAB MCP Server — v2.0 Milestone**

A Python-based MCP server that lets AI coding agents (Claude Code, Codex CLI, etc.) execute MATLAB code, inspect workspaces, manage files, and monitor server health. It bridges the Model Context Protocol to MATLAB's Engine API with elastic pooling, session isolation, and async job orchestration.

**Core Value:** Any MCP-compatible coding agent can connect to MATLAB and run code securely — with minimal setup, proper authentication, and production-grade reliability.

### Constraints

- **Tech stack**: Python 3.10+, must keep backward compat with existing config.yaml format
- **Platform**: Must work on Windows 10 without admin rights (no service installation, no elevated ports)
- **Dependency**: FastMCP 3.0 migration must not break existing stdio/SSE clients
- **MATLAB**: Requires MATLAB R2022b+ with Engine API — this is an external user dependency
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.10+ - Core application language, enforced via `pyproject.toml`
- MATLAB R2022b+ - Target runtime for code execution (via MATLAB Engine API)
- JavaScript/TypeScript - Dashboard frontend (static HTML/CSS/JS in monitoring UI)
## Runtime
- Python 3.10, 3.11, 3.12 - Supported versions per `pyproject.toml`
- MATLAB Engine API for Python - Bridge to MATLAB execution (imported at `src/matlab_mcp/pool/engine.py`)
- pip - Python dependency management
- Lockfile: `requirements-lock.txt` (pinned versions)
- Build backend: hatchling (via `[build-system]` in `pyproject.toml`)
## Frameworks
- FastMCP 2.14.5 - MCP server framework (`fastmcp>=2.0.0,<3.0.0` in dependencies)
- Starlette 0.52.1 - Web framework for HTTP monitoring dashboard (`src/matlab_mcp/monitoring/dashboard.py`)
- Uvicorn 0.42.0 - ASGI server for HTTP transport and dashboard
- Model Context Protocol (MCP 1.26.0) - Protocol implementation
- Pydantic 2.12.5 - Configuration validation and data models (`src/matlab_mcp/config.py`)
- PyYAML 6.0.3 - Configuration file parsing (YAML format)
- aiosqlite 0.22.1 - Async SQLite for metrics persistence (`src/matlab_mcp/monitoring/store.py`)
- Plotly 6.6.0 - Interactive plot generation and JSON export (`src/matlab_mcp/output/plotly_convert.py`)
- Pillow 12.1.1 - Image processing for thumbnails (`src/matlab_mcp/output/thumbnail.py`)
- sse-starlette 3.3.3 - Server-sent events for multi-user SSE transport
- websockets 16.0 - WebSocket support
- pytest 7.0+ - Test runner
- pytest-asyncio 0.21+ - Async test support
- pytest-cov 4.0+ - Coverage reporting
- ruff 0.1.0+ - Code linting and formatting
- pip-audit 2.6.0+ - Security vulnerability scanning
- build 1.0.0+ - Python package builder
## Key Dependencies
- `fastmcp>=2.0.0,<3.0.0` - MCP server framework enabling tool registration and protocol handling
- `pydantic>=2.0.0` - Configuration validation with type safety (used extensively in `src/matlab_mcp/config.py`)
- `matlab.engine` - Actual MATLAB execution bridge (external, installed from MATLAB installation)
- `pyyaml>=6.0` - Configuration file loading (`load_config` in `src/matlab_mcp/config.py`)
- `aiosqlite>=0.19.0` - Metrics database for monitoring (`src/matlab_mcp/monitoring/store.py`)
- `plotly>=5.9.0` - Interactive visualization and figure conversion
- `Pillow>=9.0.0` - Image processing and thumbnail generation
- `psutil>=5.9.0` - System metrics collection (optional monitoring dependency)
- `uvicorn>=0.20.0` - ASGI server for dashboard HTTP endpoints
## Configuration
- YAML-based via `config.yaml` (optional; defaults used if absent)
- Environment variable overrides via `MATLAB_MCP_*` prefix convention
- Example: `MATLAB_MCP_POOL_MAX_ENGINES=20` overrides `config.pool.max_engines`
- Configuration system: `src/matlab_mcp/config.py` with `load_config()` and `_apply_env_overrides()`
- `pyproject.toml` - Modern Python packaging with PEP 517/518
- Hatchling backend - Build system
- Entry point: `matlab-mcp = "matlab_mcp.server:main"` (CLI command)
- `server` - Transport (stdio/sse), host/port, logging
- `pool` - MATLAB engine pool sizing (min/max engines, timeouts)
- `execution` - Job execution timeouts, workspace isolation
- `security` - Blocked functions, upload size limits, proxy auth
- `monitoring` - Metrics collection, SQLite database path, dashboard settings
- `sessions` - Session limits, idle timeouts
- `workspace` - Default MATLAB paths and startup commands
## Platform Requirements
- Python 3.10+ with pip
- MATLAB R2022b+ with Python Engine API installed (`python setup.py install` from MATLAB's `extern/engines/python`)
- Optional: hatchling, ruff, pytest, coverage tools
- Python 3.10+ runtime
- MATLAB R2022b+ installation (single shared instance or containerized)
- Transports:
- Storage:
- Docker support via `docker-compose.yml` (provided)
- Services: Python environment with mounted MATLAB installation
- Volumes: config files (RO), results, monitoring data
- Ports: 8765 (main), 8766 (dashboard HTTP)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module files use lowercase with underscores: `executor.py`, `security_validator.py`
- Test files use `test_<module_name>.py`: `test_session.py`, `test_security.py`
- Mock files use `<name>_mock.py`: `matlab_engine_mock.py`
- Package directories use lowercase with underscores: `matlab_mcp`, `matlab_mcp/tools`, `matlab_mcp/security`
- Use snake_case for all functions: `execute_code_impl`, `check_code_impl`, `get_workspace_impl`
- Implementation functions commonly end with `_impl` suffix for clarity
- Async functions use `async def` prefix: `async def execute_code_impl(...)`
- Private/internal functions use leading underscore: `_strip_string_literals`, `_make_config`
- Use snake_case for all variables and constants: `session_id`, `max_sessions`, `temp_dir`
- Constants (module-level, typically) use UPPERCASE: `_DEFAULT_SESSION_ID`, `_DEFAULT_MAX_SIZE_MB`
- Abbreviations expand naturally: `temp_dir` not `tmp_dir`, `session_id` not `sess_id`
- Thread locks use `_lock` suffix: `self._lock = threading.Lock()`
- Custom exception classes use PascalCase: `BlockedFunctionError`, `MatlabExecutionError`
- Dataclass and Pydantic model classes use PascalCase: `Session`, `Job`, `CustomToolParam`, `AppConfig`
- Type hints use full paths only when necessary for clarity (avoid noise)
## Code Style
- Line length: 100 characters (configured in `pyproject.toml` via `ruff`)
- Indentation: 4 spaces (Python default)
- Trailing commas in multiline collections encouraged for diffs
- Tool: `ruff` (configured in `pyproject.toml`)
- Target version: Python 3.10+ (`target-version = "py310"`)
- Configuration minimal - only line-length and version specified
- Async functions are marked `async def`
- All test methods that call async code are `async def test_*` (pytest-asyncio handles auto-execution via `asyncio_mode = "auto"`)
- Background operations use `asyncio.create_task()` for fire-and-forget
## Import Organization
- No path aliases configured; all imports use full module paths from package root
- Absolute imports preferred over relative imports
- All modules use `from __future__ import annotations` at the top for forward reference support
- This is a universal practice across the codebase
## Error Handling
- Custom exceptions inherit from standard Python exceptions: `class BlockedFunctionError(Exception):`
- Error handling uses try/except blocks that catch specific exceptions when possible
- Generic `Exception as exc` used only when catching broad categories
- Security violations raise `BlockedFunctionError` with descriptive message
- File operations catch `FileNotFoundError`, `ValueError`, and generic `Exception` for disk issues
- Results return error dicts instead of raising exceptions where appropriate: `{"status": "error", "message": "..."}`
## Logging
- Every module defines `logger = logging.getLogger(__name__)` near the top
- Log levels used appropriately:
- String formatting uses `%s` style with arguments: `logger.info("Starting pool with %d engines", num_engines)`
- Complex objects logged only at debug level
## Comments
- Docstrings required for all public classes and functions
- Inline comments rare; code should be self-explanatory
- Comments explain WHY something is done, not WHAT it does
- Section separators used: `# --------` lines with hyphens
- NumPy-style docstrings used for comprehensive API documentation
- All parameters documented with type and description
- Returns section specifies return type and keys/structure
- Raises section documents exceptions that can be raised
## Function Design
- Maximum 4-5 positional parameters; additional parameters via context objects or config
- Keyword-only arguments used where clarity helps: `async def execute_code_impl(..., temp_dir: Optional[str] = None)`
- Type hints on all parameters and return values (even `Any` when necessary)
- Simple return values (dict, str, bool) preferred
- Complex returns use structured objects (dataclasses, Pydantic models)
- Async functions return coroutines that resolve to above types
- Implementation functions often return dicts: `{"status": "ok", "key": value}`
## Module Design
- No explicit `__all__` lists; public functions/classes are those not starting with underscore
- Module docstrings at the top describe the module's purpose and main exports
- Internal utilities prefixed with underscore: `_strip_string_literals`, `_make_config`
- Minimal use of barrel files; `__init__.py` files mostly empty or import key classes
- `src/matlab_mcp/__init__.py` typically empty (no re-exports)
- Direct imports from submodules preferred
- Related functions/classes grouped by responsibility in single files
- Config models (`config.py`) use Pydantic `BaseModel`
- Dataclass models use `@dataclass` decorator with `from dataclasses import`
- Each tool category has its own module: `tools/core.py`, `tools/files.py`, `tools/admin.py`
## Type Annotations
- All function parameters have type hints
- All return types specified (including `-> dict`, `-> None`)
- Class attributes typed (especially in dataclasses and Pydantic models)
- Optional parameters use `Optional[T]` or `T | None`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **FastMCP framework** — Exposes tools via the Model Context Protocol
- **Async-first design** — Hybrid sync/async execution with background job promotion
- **Resource pooling** — Elastic pool of MATLAB engines (scales 2-10+ on demand)
- **Session isolation** — Per-session workspaces and temporary directories
- **Event-driven monitoring** — Real-time metrics collection with retention-based cleanup
## Layers
- Purpose: Top-level FastMCP server initialization, lifespan management, tool registration
- Location: `src/matlab_mcp/server.py`
- Contains: `MatlabMCPServer` state container, `create_server()` factory, tool decorators
- Depends on: All subsystems (pool, executor, sessions, security, monitoring)
- Used by: CLI entry point (`main()`)
- Purpose: Manage lifecycle of MATLAB engine instances with auto-scaling and health checks
- Location: `src/matlab_mcp/pool/`
- Contains: 
- Depends on: MATLAB Engine API (via lazy import)
- Used by: `JobExecutor`
- Purpose: Orchestrate job lifecycle from creation through completion
- Location: `src/matlab_mcp/jobs/`
- Contains:
- Depends on: Engine Pool, Security Validator
- Used by: Core tools (`execute_code`, `check_code`)
- Purpose: Manage user sessions with workspace isolation and idle timeout cleanup
- Location: `src/matlab_mcp/session/manager.py`
- Contains: `SessionManager` managing `Session` objects (temp_dir, created_at, last_active)
- Depends on: Config
- Used by: Server layer for temp_dir routing
- Purpose: Validate MATLAB code against blocked functions and sanitize filenames
- Location: `src/matlab_mcp/security/validator.py`
- Contains: `SecurityValidator` with precompiled regex patterns, string-literal stripping
- Depends on: Config
- Used by: Core execution tools
- Purpose: Implement MCP tool handlers (execute, check, discover, files, jobs, monitoring)
- Location: `src/matlab_mcp/tools/`
- Contains:
- Depends on: Executor, Tracker, Security, Sessions, Pool, Output Formatter
- Used by: Server layer (tool registration)
- Purpose: Format MATLAB execution results for MCP responses
- Location: `src/matlab_mcp/output/`
- Contains:
- Depends on: Config
- Used by: `JobExecutor` for result formatting
- Purpose: Collect metrics and provide health/diagnostic views
- Location: `src/matlab_mcp/monitoring/`
- Contains:
- Depends on: Config, Pool, Tracker, Sessions
- Used by: Server layer (background sampling task), dashboard UI
- Purpose: Load, validate, and apply environment overrides
- Location: `src/matlab_mcp/config.py`
- Contains: Pydantic models (ServerConfig, PoolConfig, ExecutionConfig, SecurityConfig, etc.), `load_config()`, environment variable override logic
- Depends on: None (external: yaml, pydantic)
- Used by: Server factory, all subsystems
## Data Flow
- **Pool state:** In-memory asyncio.Queue for available engines, list of all engines
- **Job state:** Thread-safe dict keyed by job_id, retained for 24 hours after terminal state
- **Session state:** Thread-safe dict keyed by session_id, idle timeout of 1 hour default
- **Monitoring state:** In-memory counters + SQLite for historical metrics (7 days default)
## Key Abstractions
- Purpose: Single MATLAB engine instance with lifecycle state machine
- Examples: `src/matlab_mcp/pool/engine.py`
- Pattern: State enum (STOPPED → STARTING → IDLE ↔ BUSY), lazy MATLAB Engine API import, health check via `is_alive` property
- Purpose: Represents one MATLAB code execution with full lifecycle tracking
- Examples: `src/matlab_mcp/jobs/models.py`
- Pattern: Dataclass with state transition methods (mark_running, mark_completed, mark_failed, mark_cancelled), Optional result/error fields
- Purpose: User session context with workspace isolation
- Examples: `src/matlab_mcp/session/manager.py`
- Pattern: Dataclass with session_id → temp_dir mapping, last_active timestamp for idle detection
- Purpose: Code validation before execution
- Examples: `src/matlab_mcp/security/validator.py`
- Pattern: Precompiled regex patterns for blocked functions, string-literal stripping to avoid false positives, configurable blocklist
- Purpose: Transform raw execution results into MCP response format
- Examples: `src/matlab_mcp/output/formatter.py`
- Pattern: Text truncation with optional file save, variable summarization, figure attachment handling
- Purpose: Record events and sample system metrics
- Examples: `src/matlab_mcp/monitoring/collector.py`
- Pattern: Event queue for async store writes, ring buffer for execution times, periodic sampling task
## Entry Points
- Location: `src/matlab_mcp/server.py::main()`
- Triggers: `python -m matlab_mcp` or installed script
- Responsibilities: Parse CLI args (--config, --transport, --inspect), load config, set up logging, create server, run FastMCP in selected transport mode
- Location: `src/matlab_mcp/server.py::create_server()` — all tools registered at lines 391-679
- Triggers: MCP client calls (e.g., `execute_code`, `get_workspace`, `upload_data`)
- Responsibilities: Deserialize request, route to implementation function, serialize response
- Location: `src/matlab_mcp/server.py::lifespan()` at lines 158-363
- Triggers: Server startup
- Responsibilities: 
## Error Handling
## Cross-Cutting Concerns
- Framework: Python logging module (stdlib)
- Pattern: Logger per module with `logger = logging.getLogger(__name__)`, configured via `--log-level` (debug/info/warning/error)
- Files: Dual output to stderr + file (`config.server.log_file` defaults to `./logs/server.log`)
- Code validation: `SecurityValidator.check_code()` with precompiled regex patterns
- File validation: `SecurityValidator.sanitize_filename()` prevents path traversal
- Config validation: Pydantic validators in `AppConfig.validate_pool()` (min_engines ≤ max_engines)
- MATLAB functions: Blocked function list in config (system, eval, perl, python, etc.)
- Transport-specific:
- No built-in token/API key auth (relying on deployment layer)
- Event recording: Fire-and-forget to async store writes (MetricsCollector.record_event)
- Metrics types: Counters (completed_total, failed_total), ring buffer (execution_times), system stats (memory_mb, cpu_percent)
- Dashboard: Real-time HTML UI with Plotly charts (stdio transport on http://127.0.0.1:8766/dashboard by default)
- Persistence: SQLite at config.monitoring.db_path (./monitoring/metrics.db), pruned after retention_days (7 default)
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
