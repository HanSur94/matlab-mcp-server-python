# Technology Stack

**Analysis Date:** 2026-04-01

## Languages

**Primary:**
- Python 3.10+ - Core application language, enforced via `pyproject.toml`
- MATLAB R2022b+ - Target runtime for code execution (via MATLAB Engine API)
- JavaScript/TypeScript - Dashboard frontend (static HTML/CSS/JS in monitoring UI)

## Runtime

**Environment:**
- Python 3.10, 3.11, 3.12 - Supported versions per `pyproject.toml`
- MATLAB Engine API for Python - Bridge to MATLAB execution (imported at `src/matlab_mcp/pool/engine.py`)

**Package Manager:**
- pip - Python dependency management
- Lockfile: `requirements-lock.txt` (pinned versions)
- Build backend: hatchling (via `[build-system]` in `pyproject.toml`)

## Frameworks

**Core:**
- FastMCP 2.14.5 - MCP server framework (`fastmcp>=2.0.0,<3.0.0` in dependencies)
- Starlette 0.52.1 - Web framework for HTTP monitoring dashboard (`src/matlab_mcp/monitoring/dashboard.py`)
- Uvicorn 0.42.0 - ASGI server for HTTP transport and dashboard
- Model Context Protocol (MCP 1.26.0) - Protocol implementation

**Data Handling:**
- Pydantic 2.12.5 - Configuration validation and data models (`src/matlab_mcp/config.py`)
- PyYAML 6.0.3 - Configuration file parsing (YAML format)
- aiosqlite 0.22.1 - Async SQLite for metrics persistence (`src/matlab_mcp/monitoring/store.py`)

**Visualization:**
- Plotly 6.6.0 - Interactive plot generation and JSON export (`src/matlab_mcp/output/plotly_convert.py`)
- Pillow 12.1.1 - Image processing for thumbnails (`src/matlab_mcp/output/thumbnail.py`)

**Transport:**
- sse-starlette 3.3.3 - Server-sent events for multi-user SSE transport
- websockets 16.0 - WebSocket support

**Testing (dev dependencies):**
- pytest 7.0+ - Test runner
- pytest-asyncio 0.21+ - Async test support
- pytest-cov 4.0+ - Coverage reporting
- ruff 0.1.0+ - Code linting and formatting

**Quality/Security:**
- pip-audit 2.6.0+ - Security vulnerability scanning
- build 1.0.0+ - Python package builder

## Key Dependencies

**Critical:**
- `fastmcp>=2.0.0,<3.0.0` - MCP server framework enabling tool registration and protocol handling
- `pydantic>=2.0.0` - Configuration validation with type safety (used extensively in `src/matlab_mcp/config.py`)
- `matlab.engine` - Actual MATLAB execution bridge (external, installed from MATLAB installation)

**Infrastructure:**
- `pyyaml>=6.0` - Configuration file loading (`load_config` in `src/matlab_mcp/config.py`)
- `aiosqlite>=0.19.0` - Metrics database for monitoring (`src/matlab_mcp/monitoring/store.py`)
- `plotly>=5.9.0` - Interactive visualization and figure conversion

**Utilities:**
- `Pillow>=9.0.0` - Image processing and thumbnail generation
- `psutil>=5.9.0` - System metrics collection (optional monitoring dependency)
- `uvicorn>=0.20.0` - ASGI server for dashboard HTTP endpoints

## Configuration

**Environment:**
- YAML-based via `config.yaml` (optional; defaults used if absent)
- Environment variable overrides via `MATLAB_MCP_*` prefix convention
- Example: `MATLAB_MCP_POOL_MAX_ENGINES=20` overrides `config.pool.max_engines`
- Configuration system: `src/matlab_mcp/config.py` with `load_config()` and `_apply_env_overrides()`

**Build:**
- `pyproject.toml` - Modern Python packaging with PEP 517/518
- Hatchling backend - Build system
- Entry point: `matlab-mcp = "matlab_mcp.server:main"` (CLI command)

**Key Configuration Sections:**
- `server` - Transport (stdio/sse), host/port, logging
- `pool` - MATLAB engine pool sizing (min/max engines, timeouts)
- `execution` - Job execution timeouts, workspace isolation
- `security` - Blocked functions, upload size limits, proxy auth
- `monitoring` - Metrics collection, SQLite database path, dashboard settings
- `sessions` - Session limits, idle timeouts
- `workspace` - Default MATLAB paths and startup commands

## Platform Requirements

**Development:**
- Python 3.10+ with pip
- MATLAB R2022b+ with Python Engine API installed (`python setup.py install` from MATLAB's `extern/engines/python`)
- Optional: hatchling, ruff, pytest, coverage tools

**Production:**
- Python 3.10+ runtime
- MATLAB R2022b+ installation (single shared instance or containerized)
- Transports:
  - `stdio` - Single-user synchronous stdio protocol (default, simplest)
  - `sse` - Multi-user SSE with HTTP dashboard (requires reverse proxy for security in production)
- Storage:
  - Filesystem: results directory, temp directory, logs directory, optional YAML configs
  - SQLite database (optional): metrics persistence at `config.monitoring.db_path`

**Containerization:**
- Docker support via `docker-compose.yml` (provided)
- Services: Python environment with mounted MATLAB installation
- Volumes: config files (RO), results, monitoring data
- Ports: 8765 (main), 8766 (dashboard HTTP)

---

*Stack analysis: 2026-04-01*
