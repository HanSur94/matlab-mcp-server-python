# External Integrations

**Analysis Date:** 2026-04-01

## APIs & External Services

**MATLAB Engine API:**
- MATLAB R2022b+ - Executes MATLAB code via embedded Python engine
  - Module: `matlab.engine` (lazy-imported at `src/matlab_mcp/pool/engine.py` line 87)
  - Usage: Core execution via `MatlabEngineWrapper.execute()` method
  - Authentication: MATLAB license activation (system-level, not API-based)

**Model Context Protocol (MCP):**
- Protocol 1.26.0 - MCP server implementation
  - SDK: `fastmcp` 2.14.5 (wrapper around `mcp` 1.26.0)
  - Auth: Transport-dependent (stdio = trusted parent, SSE = proxy header-based)

## Data Storage

**Databases:**
- SQLite3 - Metrics and events persistence (local file-based)
  - Client: `aiosqlite` 0.22.1 (async wrapper)
  - Connection: Local file at `config.monitoring.db_path` (default: `./monitoring/metrics.db`)
  - Usage: Historical metrics, events, performance data
  - Schema: Two tables (`metrics`, `events`) with indexes on timestamp and category

**File Storage:**
- Local filesystem only - No cloud storage integration
  - Results directory: `config.server.result_dir` (default: `./results`)
  - Temp directory: `config.execution.temp_dir` (default: `./temp`)
  - Log files: `config.server.log_file` (default: `./logs/server.log`)
  - Monitoring DB: `config.monitoring.db_path` (default: `./monitoring/metrics.db`)

**Caching:**
- In-memory collections - Session and job tracking
  - Session manager: `src/matlab_mcp/session/manager.py` - Dict-based session storage
  - Job tracker: `src/matlab_mcp/jobs/tracker.py` - Dict-based job metadata with TTL cleanup
  - No Redis or external cache integration

## Authentication & Identity

**Auth Provider:**
- Custom (header-based for SSE, none for stdio)
  - SSE transport: Expects authentication proxy to set headers
  - Configuration: `config.security.require_proxy_auth` (default: false)
  - Validator: `src/matlab_mcp/security/validator.py`
  - Usage: Session isolation per user (SSE mode); no built-in auth system

**Session Management:**
- Session manager at `src/matlab_mcp/session/manager.py`
  - Per-session temp directories (isolation)
  - Session timeouts configurable via `config.sessions.session_timeout`
  - Default sessions for stdio transport

## Monitoring & Observability

**Error Tracking:**
- None (custom error log only)
- Error collection: `src/matlab_mcp/monitoring/collector.py` (in-memory deque, ~50 events)
- Error endpoint: Tool `get_error_log_impl()` at `src/matlab_mcp/tools/monitoring.py`

**Logs:**
- Dual output (stderr + file)
  - Framework: Python `logging` module
  - File handler: `config.server.log_file` with rotation (standard Python FileHandler)
  - Format: `"%(asctime)s %(levelname)s %(name)s — %(message)s"`
  - Level: Configurable via `config.server.log_level`
  - Setup: `src/matlab_mcp/server.py` lines 725-742

**Metrics & Health:**
- Custom metrics collector
  - Component: `MetricsCollector` at `src/matlab_mcp/monitoring/collector.py`
  - Storage: SQLite via `MetricsStore` at `src/matlab_mcp/monitoring/store.py`
  - Sampling interval: `config.monitoring.sample_interval` (default: 10s)
  - Metrics: Pool utilization, job throughput, session count, engine health, system CPU/memory
  - Retention: `config.monitoring.retention_days` (default: 7 days)
  - Health evaluation: `src/matlab_mcp/monitoring/health.py`

## Monitoring Dashboard

**HTTP API (Starlette):**
- Transport: SSE → dashboard integrated at `/dashboard` (via Starlette)
- Transport: Stdio → separate HTTP server on `config.monitoring.http_port` (default: 8766, Uvicorn)
- Endpoints:
  - `GET /health` - Health status (200 or 503)
  - `GET /metrics` - Live metrics snapshot
  - `GET /dashboard` - Dashboard HTML
  - `GET /dashboard/api/current` - Current metrics JSON
  - `GET /dashboard/api/history` - Historical time-series (configurable metric and hours)
  - `GET /dashboard/api/events` - Recent event log
  - `GET /dashboard/static/*` - Static assets (CSS, JS)
- Implementation: `src/matlab_mcp/monitoring/dashboard.py`

## CI/CD & Deployment

**Hosting:**
- Self-hosted (no cloud provider integration)
- Docker support provided: `docker-compose.yml`
- Deployment modes:
  - Single-user: stdio transport (default)
  - Multi-user: SSE transport with reverse proxy (production)

**CI Pipeline:**
- GitHub Actions (repository has CI workflow)
- No direct cloud API integrations (standard GitHub build/test/lint)

## Environment Configuration

**Required env vars:**
None strictly required (all have defaults). Optional overrides via `MATLAB_MCP_*` prefix:
- `MATLAB_MCP_POOL_MAX_ENGINES` - Override pool sizing
- `MATLAB_MCP_SERVER_TRANSPORT` - stdio or sse
- `MATLAB_MCP_POOL_MATLAB_ROOT` - Explicit MATLAB installation path
- (Full list via convention: `MATLAB_MCP_{SECTION}_{KEY}` in snake_case)

**Secrets location:**
- No secrets management system integrated
- Recommendations: Use environment variable prefix for sensitive config in production
- Note: `.env` files not used; config is YAML + environment overrides only

**Configuration Files:**
- `config.yaml` - Optional YAML configuration (read from cwd or via `--config` CLI arg)
- `custom_tools.yaml` - User-defined MATLAB function exposures (path from config)
- Relative paths resolved to absolute via config directory at startup

## Webhooks & Callbacks

**Incoming:**
- None defined - MCP is request-response only

**Outgoing:**
- None - No external API calls from the server

## Transport Modes

**Standard IO (stdio):**
- Default, single-user, no authentication
- Monitoring dashboard runs on separate HTTP port (8766)
- Used with Claude Desktop, Cursor, Copilot

**Server-Sent Events (SSE):**
- Multi-user support via `--transport sse`
- HTTP-based (host/port: `config.server.host/port`)
- Session isolation per client
- Security: Requires reverse proxy with authentication (warn if `require_proxy_auth=false`)
- Monitoring integrated directly in server (no separate HTTP port)
- Implementation: `sse-starlette` 3.3.3 library

## MATLAB-Specific Integrations

**MATLAB Engine Lifecycle:**
- Pool management: `src/matlab_mcp/pool/manager.py`
- Individual engines: `src/matlab_mcp/pool/engine.py`
- Execution: Lazy import of `matlab.engine` module (supports mocking for tests)
- Workspace isolation: Per-engine or per-session depending on `config.execution.workspace_isolation`

**MATLAB Code Checking:**
- Integration: `checkcode` / `mlint` MATLAB function
- Tool: `check_code_impl()` at `src/matlab_mcp/tools/core.py`
- Configuration: `config.code_checker` (enable/disable, severity levels)

**MATLAB Figure Conversion:**
- MATLAB helper script: `mcp_extract_props.m` (in `src/matlab_mcp/matlab_helpers/`)
- Plotly conversion: `src/matlab_mcp/output/plotly_convert.py`
- Image generation: via Plotly JSON (static PNG fallback via Pillow)
- Supported types: Line, scatter, bar, area, subplots, log/linear scales

---

*Integration audit: 2026-04-01*
