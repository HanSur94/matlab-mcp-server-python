# Architecture

## System Overview

```
AI Agent (Claude, Cursor, Copilot, etc.)
       │
       │ MCP Protocol (stdio or SSE)
       ▼
┌─────────────────────────────────┐
│   MCP Server (FastMCP)           │
│   ├─ 20 built-in tools           │
│   ├─ Custom tools (from YAML)    │
│   ├─ Session manager             │
│   ├─ Security validator          │
│   └─ Result formatter            │
└──────────┬──────────────────────┘
           │
┌──────────▼──────────────────────┐
│   Job Executor                    │
│   ├─ Hybrid sync/async execution  │
│   ├─ Timeout-based promotion      │
│   └─ Progress injection           │
└──────────┬──────────────────────┘
           │
┌──────────▼──────────────────────┐
│   Engine Pool Manager             │
│   ├─ Elastic scaling (min→max)    │
│   ├─ Health checks                │
│   ├─ Proactive warmup             │
│   └─ Idle scale-down              │
└──────────┬──────────────────────┘
           │
┌──────────▼──────────────────────┐
│   MATLAB Engines (2020b+)         │
│   Engine 1 │ Engine 2 │ ... │ N   │
└───────────────────────────────────┘
```

## Component Details

### MCP Server (`server.py`)

The entry point. Uses [FastMCP](https://github.com/jlowin/fastmcp) to handle MCP protocol details. Responsibilities:

- Register all 20 tools + custom tools
- Manage server lifecycle (startup, shutdown, drain)
- Route tool calls to implementation modules
- Run background tasks (health checks, cleanup)

### Engine Pool Manager (`pool/manager.py`)

Manages a pool of MATLAB engine instances:

- **Elastic scaling:** Starts with `min_engines`, scales up to `max_engines` under load
- **Proactive warmup:** When utilization exceeds `proactive_warmup_threshold` (80%), starts a new engine before it's needed
- **Scale-down:** Engines idle longer than `scale_down_idle_timeout` (15 min) are stopped, down to `min_engines`
- **Health checks:** Periodic `1+1` eval to verify engines are responsive. Unhealthy engines are replaced
- **Queue:** Requests wait in an async queue when all engines are busy

### Engine Wrapper (`pool/engine.py`)

Wraps a single `matlab.engine` instance:

- Start/stop lifecycle
- Execute code (sync or background)
- Workspace reset between sessions
- Health check ping
- State tracking (idle, busy, error)

### Job Executor (`jobs/executor.py`)

Hybrid sync/async execution:

1. Code is security-checked (blocked functions scan)
2. Job context is injected (`__mcp_job_id__`, `__mcp_temp_dir__`)
3. Execution starts synchronously
4. If `sync_timeout` exceeded → auto-promote to async, return `job_id`
5. Background task monitors completion, stores result

### Job Tracker (`jobs/tracker.py`)

In-memory store for job metadata:

- Create/get/list/cancel jobs
- Prune completed jobs older than `job_retention_seconds`
- Thread-safe with asyncio locks

### Session Manager (`session/manager.py`)

Per-user session isolation:

- Each session gets a unique temp directory
- Workspace cleared between sessions (when `workspace_isolation=true`)
- Expired sessions cleaned up after `session_timeout`
- stdio transport uses a single "default" session

### Security Validator (`security/validator.py`)

Pre-execution security checks:

- **Function blocklist:** Scans code for blocked functions (`system`, `unix`, `dos`, `!`, `eval`, `feval`, `evalc`, `evalin`, `assignin`, `perl`, `python`). Smart enough to strip string literals and comments first to avoid false positives
- **Filename sanitization:** Prevents path traversal in upload filenames
- **Upload size limits:** Enforces `max_upload_size_mb`

### Result Formatter (`output/formatter.py`)

Structures tool responses:

- Text output formatting with length limits
- Variable formatting from workspace queries
- Success/error response builders
- Delegates to Plotly converter and thumbnail generator

### Plotly Converter (`output/plotly_convert.py`, `output/plotly_style_mapper.py` + `matlab_helpers/mcp_extract_props.m`)

Converts MATLAB figures to interactive Plotly JSON:

1. MATLAB-side: `mcp_extract_props.m` extracts raw figure properties (line, scatter, bar, histogram, surface, image)
2. Python-side: `plotly_style_mapper.py` converts MATLAB styles (line styles, markers, colormaps, fonts, colors) to Plotly equivalents, with WebGL support for large datasets (10,000+ points)
3. Python-side: `plotly_convert.py` / `load_plotly_json()` reads the saved JSON file
4. Result includes: Plotly JSON + static PNG + optional thumbnail

## Data Flow

### Sync Execution

```
Agent → execute_code("x = magic(3)")
  → Security check (OK)
  → Acquire engine from pool
  → Inject job context
  → Engine.eval("x = magic(3)")
  → Complete in <30s
  → Format result
  → Release engine
  → Return result to agent
```

### Async Promotion

```
Agent → execute_code("long_simulation()")
  → Security check (OK)
  → Acquire engine
  → Engine.eval (background=True)
  → 30s timeout exceeded
  → Return {job_id: "abc123", status: "running"}
  → Agent polls get_job_status("abc123") → progress: 45%
  → Agent polls get_job_status("abc123") → progress: 90%
  → Agent calls get_job_result("abc123") → full result
  → Engine released
```

## Transport Modes

### stdio (Default)

- One agent, one session
- Communication via stdin/stdout
- Simplest setup, no network

### SSE (Server-Sent Events)

- Multiple agents, multiple sessions
- HTTP-based, supports remote connections
- Session isolation via session IDs
- **Production:** Put behind a reverse proxy with auth (`require_proxy_auth: true`)
