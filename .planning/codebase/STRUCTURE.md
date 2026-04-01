# Codebase Structure

**Analysis Date:** 2026-04-01

## Directory Layout

```
matlab-mcp-server-python/
├── src/matlab_mcp/                # Main package source
│   ├── __init__.py                # Version definition
│   ├── server.py                  # FastMCP server factory, lifespan, tool registration
│   ├── config.py                  # Pydantic config models, YAML loading, env overrides
│   ├── pool/                      # Engine pooling subsystem
│   │   ├── engine.py              # MatlabEngineWrapper with state machine
│   │   └── manager.py             # EnginePoolManager (scale-up/down, acquire/release)
│   ├── jobs/                      # Job execution orchestration
│   │   ├── models.py              # Job dataclass and JobStatus enum
│   │   ├── tracker.py             # JobTracker (thread-safe job registry)
│   │   └── executor.py            # JobExecutor (lifecycle orchestration)
│   ├── session/                   # User session management
│   │   └── manager.py             # SessionManager and Session dataclass
│   ├── security/                  # Code/file validation
│   │   └── validator.py           # SecurityValidator (blocked functions, path traversal)
│   ├── tools/                     # MCP tool implementations
│   │   ├── core.py                # execute_code_impl, check_code_impl, get_workspace_impl
│   │   ├── discovery.py           # list_toolboxes_impl, list_functions_impl, get_help_impl
│   │   ├── files.py               # File I/O tools (upload, delete, list, read_script, read_data, read_image)
│   │   ├── jobs.py                # Job lifecycle tools (status, result, cancel, list)
│   │   ├── admin.py               # get_pool_status_impl
│   │   ├── custom.py              # Custom tool loader and handler factory
│   │   └── monitoring.py           # Monitoring tools (metrics, health, error log)
│   ├── output/                    # Result formatting
│   │   ├── formatter.py           # ResultFormatter (text, variables, figures)
│   │   ├── plotly_convert.py      # MATLAB figure → Plotly JSON
│   │   ├── plotly_style_mapper.py # Style mapping (colors, lines, markers)
│   │   └── thumbnail.py           # Static PNG thumbnail generation
│   ├── monitoring/                # Metrics and health subsystem
│   │   ├── collector.py           # MetricsCollector (events, sampling)
│   │   ├── store.py               # MetricsStore (SQLite persistence)
│   │   ├── health.py              # Health status detection
│   │   ├── dashboard.py           # HTTP dashboard app (Starlette)
│   │   ├── routes.py              # HTTP endpoints
│   │   └── static/                # Dashboard UI assets
│   └── matlab_helpers/            # MATLAB helper functions (.m files)
│       └── mcp_*.m                # Helper functions (checkcode, extract props, etc.)
│
├── tests/                         # Test suite
│   ├── conftest.py                # Pytest fixtures
│   ├── mocks/                     # Mock MATLAB engine
│   │   └── matlab_engine_mock.py  # MockMatlabEngine for testing
│   ├── test_*.py                  # Unit/integration tests by module
│   └── test_integration_*.py      # Full integration tests
│
├── examples/                      # Usage examples
├── docs/                          # Documentation
├── monitoring/                    # Monitoring data directory (created at runtime)
├── logs/                          # Log files directory (created at runtime)
├── results/                       # Result files directory (created at runtime)
├── temp/                          # Session temp directories (created at runtime)
│
├── pyproject.toml                 # Python package metadata
├── requirements-lock.txt          # Pinned dependencies
├── config.yaml                    # Default application config
├── custom_tools.yaml              # User-defined custom tools
├── Dockerfile                     # Container image definition
├── docker-compose.yml             # Local dev composition
└── README.md                      # Project documentation
```

## Directory Purposes

**`src/matlab_mcp/`:**
- Purpose: Main application package
- Contains: All server logic, tools, subsystems
- Key files: `server.py` (entry point), `config.py` (configuration)

**`src/matlab_mcp/pool/`:**
- Purpose: MATLAB engine lifecycle and pooling
- Contains: Engine wrapper state machine, pool manager with scale-up/down logic
- Key files: `engine.py` (wrapper), `manager.py` (pool)

**`src/matlab_mcp/jobs/`:**
- Purpose: Async job execution orchestration
- Contains: Job model, tracker (registry), executor (lifecycle orchestration)
- Key files: `executor.py` (main logic), `tracker.py` (storage), `models.py` (data model)

**`src/matlab_mcp/session/`:**
- Purpose: User session and workspace isolation
- Contains: Session manager, session dataclass with temp directory mapping
- Key files: `manager.py` (session lifecycle)

**`src/matlab_mcp/security/`:**
- Purpose: Code and filename validation
- Contains: Blocked function checking, path traversal prevention
- Key files: `validator.py` (validation logic)

**`src/matlab_mcp/tools/`:**
- Purpose: MCP tool implementations
- Contains: Tool handler functions, each file groups related tools
- Key files: `core.py` (execute/check/workspace), `files.py` (I/O), `discovery.py` (browse)

**`src/matlab_mcp/output/`:**
- Purpose: Result formatting for responses
- Contains: Text/variable formatting, Plotly conversion, thumbnails
- Key files: `formatter.py` (main), `plotly_convert.py` (figure conversion)

**`src/matlab_mcp/monitoring/`:**
- Purpose: Metrics collection, storage, and dashboards
- Contains: Event collection, SQLite store, HTTP UI
- Key files: `collector.py` (in-memory), `store.py` (persistence), `dashboard.py` (UI)

**`tests/`:**
- Purpose: Test suite
- Contains: Unit tests by module, integration tests, mocks
- Key files: `conftest.py` (fixtures), `test_*.py` (tests by feature)

**`docs/` and `wiki/`:**
- Purpose: User-facing documentation
- Contains: Examples, architecture diagrams, API references
- Key files: Various .md files and wiki pages

**`monitoring/`, `logs/`, `results/`, `temp/` (Runtime):**
- Purpose: Created at runtime for data, logs, and session temp files
- Contents: Generated during server operation
- Cleanup: Sessions expire after session_timeout (1 hour default), metrics after retention_days (7 default)

## Key File Locations

**Entry Points:**
- `src/matlab_mcp/server.py::main()` — CLI entry point, parses args, loads config, starts server
- `src/matlab_mcp/server.py::create_server()` — FastMCP instance factory, registers tools, sets up lifespan

**Configuration:**
- `config.yaml` — Default application config (can be overridden via `--config`)
- `src/matlab_mcp/config.py` — Pydantic models, validation, environment variable override logic

**Core Logic:**
- `src/matlab_mcp/jobs/executor.py` — Job execution orchestration (acquire → inject → execute → format)
- `src/matlab_mcp/pool/manager.py` — Engine pool scaling and acquisition
- `src/matlab_mcp/session/manager.py` — Session lifecycle and workspace isolation
- `src/matlab_mcp/security/validator.py` — Code validation (blocked functions)

**Testing:**
- `tests/conftest.py` — Pytest fixtures (mock MATLAB engine, config)
- `tests/test_*.py` — Module-specific tests
- `tests/mocks/matlab_engine_mock.py` — Mock MATLAB engine for testing

## Naming Conventions

**Files:**
- Tool implementation: `tools/<domain>.py` (e.g., `tools/core.py`, `tools/files.py`)
- Model/dataclass: `<module>/models.py` (e.g., `jobs/models.py`)
- Manager/registry: `<module>/manager.py` (e.g., `session/manager.py`)
- Subsystem implementation: `<module>/<component>.py` (e.g., `pool/engine.py`, `monitoring/collector.py`)
- Implementations: `*_impl()` suffix for tool handler functions (e.g., `execute_code_impl`)

**Directories:**
- Subsystems: singular noun + plural (e.g., `pool/`, `jobs/`, `session/`, `tools/`)
- Data organization: plural (e.g., `tests/`, `examples/`, `docs/`)

**Functions:**
- Tool implementations: `<noun>_impl()` (e.g., `execute_code_impl`, `get_workspace_impl`)
- Async helpers: `async def` prefix (e.g., `async def execute()`)
- Private helpers: `_<name>()` prefix (e.g., `_inject_job_context()`)
- State transitions: `mark_<state>()` (e.g., `mark_running()`, `mark_completed()`)

**Classes:**
- Managers: `<Noun>Manager` (e.g., `EnginePoolManager`, `SessionManager`)
- Wrappers: `<Noun>Wrapper` (e.g., `MatlabEngineWrapper`)
- Validators: `<Noun>Validator` (e.g., `SecurityValidator`)
- Models: Plain dataclass names (e.g., `Job`, `Session`)
- Enums: `<Noun>Status` or `<Noun>State` (e.g., `JobStatus`, `EngineState`)

**Variables:**
- Private/internal: underscore prefix (e.g., `_pool`, `_config`)
- Configuration: `_config`, `_pool_config`, `_workspace_config`
- Locks/queues: descriptive suffix (e.g., `_scale_lock`, `_available` queue)
- Timing: `<action>_at` for timestamps (e.g., `created_at`, `last_active`)

## Where to Add New Code

**New Execution Feature (e.g., parallel code execution):**
- Primary code: `src/matlab_mcp/jobs/executor.py` — modify execute() method
- Tool handler: `src/matlab_mcp/tools/core.py` — add new tool function
- Tests: `tests/test_executor_*.py` — add executor tests
- Server registration: `src/matlab_mcp/server.py::create_server()` — register @mcp.tool

**New Tool Category (e.g., data analysis tools):**
- Implementation: `src/matlab_mcp/tools/analysis.py` — create new file
- Tool implementations: Define `<noun>_impl()` functions
- Server registration: `src/matlab_mcp/server.py::create_server()` — import and register tools
- Tests: `tests/test_tools_analysis.py` — module-specific tests

**New Subsystem (e.g., caching layer):**
- Directory: `src/matlab_mcp/cache/` — create subsystem dir
- Core component: `src/matlab_mcp/cache/manager.py` — main logic
- Data model: `src/matlab_mcp/cache/models.py` — if needed
- Server integration: `src/matlab_mcp/server.py::MatlabMCPServer.__init__()` — instantiate
- Lifespan: `src/matlab_mcp/server.py::lifespan()` — startup/shutdown hooks if async

**New Monitoring Metric:**
- Collection: `src/matlab_mcp/monitoring/collector.py::record_event()` — call existing pattern or add new event type
- Storage: `src/matlab_mcp/monitoring/store.py` — ensure schema supports new metric
- Dashboard: `src/matlab_mcp/monitoring/dashboard.py` — add chart/display
- Tests: `tests/test_monitoring_*.py` — metric tests

**Utility Functions:**
- Shared helpers: `src/matlab_mcp/output/formatter.py` — formatters and conversions
- Validation helpers: `src/matlab_mcp/security/validator.py` — validation logic
- Don't create top-level `utils.py` — organize by subsystem

**Tests:**
- Unit tests: `tests/test_<module>.py` (e.g., `tests/test_pool.py`)
- Integration tests: `tests/test_integration_<feature>.py` (e.g., `tests/test_integration_figures.py`)
- Fixtures: `tests/conftest.py` — shared pytest fixtures
- Mocks: `tests/mocks/` — mock implementations

## Special Directories

**`src/matlab_mcp/matlab_helpers/`:**
- Purpose: MATLAB helper functions (.m files)
- Generated: No (hand-written)
- Committed: Yes (part of distribution)
- Examples: `mcp_checkcode.m`, `mcp_extract_props.m` — used by Python code for linting and figure extraction

**`monitoring/`, `logs/`, `results/`, `temp/` (Runtime):**
- Purpose: Runtime data directories
- Generated: Yes (created by server on startup via `lifespan()`)
- Committed: No (.gitignore)
- Lifecycle: Cleaned up periodically by background tasks (metrics pruned after retention_days, sessions after session_timeout)

**`tests/`:**
- Purpose: Test suite
- Generated: No (hand-written tests and fixtures)
- Committed: Yes
- Pattern: Pytest fixtures in `conftest.py`, mock MATLAB engine in `mocks/`, tests grouped by module/feature

**`vendor/`:**
- Purpose: Third-party dependencies (if bundled)
- Generated: Possibly (from pip, local builds)
- Committed: Check .gitignore for vendored vs. pulled from pip

---

*Structure analysis: 2026-04-01*
