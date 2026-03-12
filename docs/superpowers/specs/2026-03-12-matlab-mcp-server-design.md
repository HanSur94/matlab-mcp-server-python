# MATLAB MCP Server — Design Specification

**Date:** 2026-03-12
**Repo:** HanSur94/matlab-mcp-server-python
**Status:** Draft — pending user review

## Overview

A Python-based MCP (Model Context Protocol) server that exposes MATLAB capabilities to any AI agent. Runs on a shared MATLAB server, supports multiple concurrent users with long-running jobs, and works with MATLAB 2020b+.

## Goals

- Expose MATLAB toolboxes and custom libraries to any MCP-compatible AI agent
- Support multiple concurrent users on a shared MATLAB server (requires SSE transport; stdio supports single user)
- Handle long-running jobs (hours) without blocking
- Cross-platform: Windows and macOS
- MATLAB 2020b minimum compatibility
- Fully configurable via YAML

## Architecture

Two-layer Python process:

1. **MCP Server Layer** (FastMCP) — handles MCP protocol, tool registration, session management, result formatting
2. **MATLAB Pool Manager** — elastic engine pool, job scheduling, toolbox discovery

Communication between layers via in-process async queues. Single deployable process with cleanly separated internals.

```
┌─────────────────────────────────────────────────────┐
│                   MCP Clients                        │
│  (Claude, Cursor, any MCP-compatible AI agent/UI)    │
└──────────────────┬──────────────────────────────────┘
                   │ MCP Protocol (stdio / SSE)
┌──────────────────▼──────────────────────────────────┐
│              MCP Server Layer (FastMCP)               │
│  - Tool Registry                                      │
│  - Session Manager                                    │
│  - Result Formatter (text / Plotly / base64)          │
└──────────────────┬──────────────────────────────────┘
                   │ async queues
┌──────────────────▼──────────────────────────────────┐
│            MATLAB Pool Manager                       │
│  - Engine Pool (elastic, min/max)                     │
│  - Job Scheduler (sync/async)                         │
│  - Toolbox Discovery                                  │
└──────────────────┬──────────────────────────────────┘
                   │ matlab.engine Python API
┌──────────────────▼──────────────────────────────────┐
│           MATLAB Engine Instances (2020b+)           │
│  Engine 1 | Engine 2 | Engine 3 | ... | Engine N     │
└─────────────────────────────────────────────────────┘
```

## Transport & Session Model

### Transport Modes

- **stdio** — single client per process. The parent process that spawns the server is the only client. Session is implicit (one session for the lifetime of the process). Suitable for single-user desktop use.
- **SSE** — multiple clients connect over HTTP. Multi-user mode. Each SSE connection establishes a new session. Requires deployment behind a reverse proxy with authentication (e.g., nginx + API keys) for production use.

### Session Identification

- **stdio:** Single implicit session. No session ID needed.
- **SSE:** Each SSE connection gets a server-generated UUID session ID. All tool calls on that connection are scoped to that session. The session ID is included in MCP response metadata.

### Session Lifecycle

1. Client connects → session created with unique ID and temp directory
2. Session active → engine assigned from pool per request, workspace isolated
3. Inactivity timeout (`session_timeout`) → session marked for cleanup
4. **Long-running job protection:** if a session has active jobs when `session_timeout` fires, the session stays alive until all jobs complete or `max_execution_time` is reached. Then cleanup proceeds.
5. Client disconnects or timeout → temp files cleaned, session data pruned

## MATLAB Engine Pool

### Elastic Scaling

- **min_engines** (default: 2) — pre-started at server launch, always warm
- **max_engines** (default: 10) — hard ceiling, never exceeded
- **Scale-up:** when all engines are busy and a new request arrives, spawn a new engine. The spawn happens in the background — the request is queued and served by the new engine once ready, or by any engine that becomes free first (whichever happens sooner).
- **Proactive warm-up:** when pool utilization exceeds 80%, start warming a new engine preemptively (if below max) to reduce cold-start latency.
- **Scale-down:** idle engines beyond min_engines shut down after configurable timeout (default: 15 min)
- **Health checks:** periodic ping (`eval('1')`) to detect crashed engines, auto-replace

### Engine Assignment

- Each tool call acquires an engine from the pool for the duration of execution
- Short sync jobs: engine returned to pool immediately after execution
- Long async jobs: engine stays assigned until the job completes
- Pool exhausted at max: request queued with estimated wait time returned to agent

### Workspace Isolation

Before assigning an engine to a new session's request, run the following cleanup sequence:

```matlab
clear all; clear global; clear functions;
fclose all;
% Restore default paths, then re-add configured paths
restoredefaultpath;
addpath('/configured/path/1');
addpath('/configured/path/2');
% Re-run startup commands
format long;
```

- Each user session gets a unique temp directory
- Temp directories cleaned up on session end
- **Note:** isolation is best-effort. MATLAB global state (Java objects, MEX-loaded shared libraries) may leak between sessions. For strict isolation, set `max_engines` equal to `max_sessions` and dedicate engines to sessions.

### Crash Recovery

- Engine crash mid-job: job marked `FAILED` with error message
- Dead engine removed from pool, fresh one spawned if below max

### macOS Multi-Engine Limitation

Running multiple `matlab.engine` instances in a single Python process on macOS has known issues with shared libraries and signal handling. Mitigation: on macOS, default `max_engines` is capped at 4. Users can override but should test stability. The config validator emits a warning when `max_engines > 4` on macOS.

## Async Job System

### Job Lifecycle

```
PENDING → RUNNING → COMPLETED
    │         │
    │         └──→ FAILED
    │         │
    │         └──→ CANCELLED
    │
    └────────────→ CANCELLED
```

Jobs can be cancelled from both `PENDING` (removed from queue) and `RUNNING` (engine execution interrupted via `matlab.engine` future cancellation) states.

### Hybrid Sync/Async Execution

1. `execute_code` called → job created as `PENDING`
2. Engine assigned → job moves to `RUNNING`
3. If completes within `sync_timeout` (default: 30s) → result returned inline, job stored as `COMPLETED`
4. If exceeds `sync_timeout` → auto-promoted to async. The `execute_code` response returns:
   ```json
   {
     "status": "async",
     "job_id": "j-abc123",
     "message": "Job promoted to async after 30s. Use get_job_status to check progress."
   }
   ```
   The MATLAB engine continues executing in the background.
5. Agent polls via `get_job_status` / retrieves via `get_job_result`

**Implementation note:** Uses `matlab.engine`'s `background=True` parameter to run MATLAB calls as futures. The sync timeout is implemented by waiting on the future with a timeout — if it doesn't complete, the future continues running and the job is promoted.

### Job Storage

- In-memory dict (fast, no external dependencies)
- **Trade-off acknowledged:** if the server process crashes, all job metadata is lost. For production deployments with critical long-running jobs, a future enhancement could add optional SQLite-backed persistence. For v1, in-memory is acceptable.
- Configurable retention period (`job_retention_seconds`, default: 86400), old completed/failed jobs pruned automatically
- Job result files persist in `result_dir` until session cleanup or retention pruning

### Progress Reporting Protocol

MATLAB code can report progress via the `mcp_progress.m` helper:

**Function signature:**
```matlab
mcp_progress(job_id, percentage, message)
% job_id: string - provided as a MATLAB variable when job starts
% percentage: double - 0.0 to 100.0
% message: string (optional) - e.g., "Iteration 500/1000"
```

**Protocol:**
- `mcp_progress.m` writes a JSON line to `<temp_dir>/<job_id>.progress`:
  ```json
  {"percentage": 50.0, "message": "Iteration 500/1000", "timestamp": "2026-03-12T10:30:00"}
  ```
- Each call overwrites the file (latest progress only, not a log)
- `get_job_status` reads this file if it exists and includes the progress in the response
- Polling interval: server reads the file on demand when `get_job_status` is called (no background polling)
- The `mcp_job_id` variable is automatically injected into the MATLAB workspace before job execution

## Security

### Execute Code Restrictions

`execute_code` runs arbitrary MATLAB code, which is powerful but risky on a shared server. The following mitigations are applied:

**Function blocklist** (configurable in `config.yaml`):
```yaml
security:
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"          # shell escape operator
    - "eval"       # dynamic eval (already in MATLAB, but can be blocked at our layer)
    - "fopen"      # optional — block direct file I/O, force use of upload_data/list_files
  blocked_functions_enabled: true
```

Before executing code, the server scans the code string for blocked function calls. This is a best-effort check (not a full parser) — determined attackers could bypass it. For strict security, deploy with OS-level user isolation (separate MATLAB user per session).

**File upload validation:**
- Filenames sanitized: only alphanumeric, `-`, `_`, `.` allowed. Path separators rejected.
- Files written only to the session's temp directory (path traversal prevented)
- Maximum upload size configurable (`max_upload_size_mb`, default: 100)

**SSE transport security:**
- The server itself does not implement authentication. Production SSE deployments MUST be placed behind a reverse proxy (nginx, Caddy, etc.) that handles authentication (API keys, OAuth, etc.) and TLS termination.
- Config validator emits a warning when `transport: sse` and `security.require_proxy_auth` is not explicitly acknowledged.

## MCP Tools

### Core Tools (always available)

| Tool | Description |
|------|-------------|
| `execute_code` | Run arbitrary MATLAB code. Sync with auto-promote to async |
| `get_job_status` | Check status of an async job (includes progress if available) |
| `get_job_result` | Retrieve result of a completed async job |
| `cancel_job` | Cancel a pending or running async job |
| `list_jobs` | List all jobs for the current session |
| `check_code` | Run MATLAB's checkcode/mlint on code string or .m file |
| `list_toolboxes` | List installed and exposed toolboxes |
| `list_functions` | List functions in a given toolbox |
| `get_help` | Get MATLAB help text for any function |
| `get_workspace` | Show current variables in session workspace |
| `upload_data` | Upload data (CSV, MAT) to session temp directory |
| `delete_file` | Delete a file from the session temp directory |
| `list_files` | List files in session temp directory |
| `get_pool_status` | Show engine pool status (available/busy/queued) |

### check_code Implementation

MATLAB's `checkcode` requires a `.m` file on disk, not a code string. Workflow:

1. If input is a code string: write to a temp `.m` file in the session temp directory
2. Call `checkcode('<temp_file>')` via the engine
3. Parse results into structured output
4. Delete temp file
5. Return structured warnings/errors:
   ```json
   {
     "issues": [
       {"line": 3, "column": 5, "severity": "warning", "id": "NASGU", "message": "Variable 'x' might be unused."}
     ],
     "summary": {"errors": 0, "warnings": 1}
   }
   ```

If input is a `.m` file path (within session temp dir): call `checkcode` directly on it.

### get_workspace Behavior

`get_workspace` returns variables currently in the engine's workspace. Since workspace isolation clears variables between different sessions' requests, this tool is most useful during a sequence of `execute_code` calls within the same session where an engine is retained (i.e., during async jobs or when `workspace_persistence: true` is configured for the session).

**Engine affinity mode** (optional, configurable): when enabled, a session is pinned to a specific engine for its lifetime, preserving workspace state across multiple `execute_code` calls. The trade-off is reduced pool flexibility.

### Custom Lib Tools (config-driven)

Defined in `custom_tools.yaml`:

```yaml
tools:
  - name: run_simulation
    matlab_function: mylib.run_sim
    description: "Run custom physics simulation"
    parameters:
      - name: model_name
        type: string
        required: true
      - name: duration
        type: double
        default: 100.0
    returns: "Struct with fields: time, state, energy"
```

Each entry becomes a first-class MCP tool with proper schema. The server validates parameters and calls the underlying MATLAB function. The `custom_tools.yaml` file must have restricted filesystem permissions (owner read-only recommended) to prevent tampering.

### Toolbox Exposure

Configurable via whitelist/blacklist/all mode in `config.yaml`. Only listed toolboxes have functions discoverable via `list_functions`.

## Result Formatting

### Success Result Structure

```json
{
  "status": "completed",
  "job_id": "j-abc123",
  "output": {
    "text": "ans = 42\n",
    "variables": {"ans": {"type": "double", "size": [1, 1], "value": 42}},
    "figures": [
      {
        "plotly_json": { "data": [], "layout": {} },
        "thumbnail_base64": "iVBOR...",
        "file_path": "/absolute/path/results/j-abc123/figure_1.png"
      }
    ],
    "files": [
      {"path": "/absolute/path/results/j-abc123/output.mat", "size_bytes": 104200}
    ],
    "warnings": ["Warning: Matrix is close to singular."],
    "errors": []
  },
  "execution_time_seconds": 1.23
}
```

### Error Result Structure

```json
{
  "status": "failed",
  "job_id": "j-abc123",
  "error": {
    "type": "MatlabExecutionError",
    "message": "Undefined function 'foo' for input arguments of type 'double'.",
    "matlab_id": "MATLAB:UndefinedFunction",
    "stack_trace": "Error in script (line 5)\n  result = foo(x);"
  },
  "execution_time_seconds": 0.12
}
```

**Error categories:**
- `MatlabExecutionError` — MATLAB runtime error (syntax, undefined function, etc.)
- `EngineError` — engine crashed or is unavailable
- `TimeoutError` — `max_execution_time` exceeded
- `ValidationError` — invalid parameters, blocked function detected
- `PoolExhaustedError` — no engines available and queue is full

### Plotly Conversion (2020b compatible)

Bundled MATLAB helper `mcp_fig2plotly.m` that:
1. Iterates all axes in the figure (supports `subplot`, multiple axes)
2. For each axes, extracts data via `get(findobj(...))` by object type (Line, Bar, Scatter, etc.)
3. Builds Plotly-compatible JSON struct in MATLAB
4. Returns to Python as dict via matlab.engine

Supported plot types: line (`plot`, `plot3`), scatter (`scatter`, `scatter3`), bar (`bar`, `barh`), histogram (`histogram`), surface/mesh (`surf`, `mesh`), contour, images (`imagesc`, `imshow`), heatmaps.

**Unsupported plot types** (2020b limitations): `tiledlayout` (introduced R2019b but buggy in 2020b introspection), `polaraxes`, `geoaxes`, complex annotation objects.

**Fallback behavior:** If Plotly conversion throws an error, the error is logged (not propagated), a static PNG is saved instead, and the figure entry in the result has `plotly_json: null` with a `conversion_error` field explaining why.

### Output Strategy

- **Text results** — inline if under `max_inline_text_length` (default: 50000 chars), otherwise saved to file with path returned and a truncated preview inline
- **Figures** — Plotly JSON + static PNG + base64 thumbnail (all three always generated when possible)
- **Tabular/matrix data** — inline if under `large_result_threshold` (default: 10000 elements), otherwise saved to `.mat`/`.csv` with path + summary (dimensions, dtype, first few rows)

## Configuration

Single `config.yaml` with all settings. Every setting has a sensible default — works out of the box with zero config. Environment variables can override any setting using `MATLAB_MCP_` prefix with underscored path (e.g., `MATLAB_MCP_POOL_MAX_ENGINES=20`). Config validated on startup with clear error messages. All relative paths are resolved to absolute paths at startup time relative to the config file's directory.

```yaml
server:
  name: "matlab-mcp-server"
  transport: "stdio"           # stdio | sse
  host: "0.0.0.0"             # only for SSE transport
  port: 8765                   # only for SSE transport
  log_level: "info"            # debug | info | warning | error
  log_file: "./logs/server.log"
  result_dir: "./results"      # resolved to absolute path at startup

pool:
  min_engines: 2
  max_engines: 10               # capped at 4 on macOS by default
  scale_down_idle_timeout: 900   # seconds (15 min)
  engine_start_timeout: 120      # seconds to wait for MATLAB to start
  health_check_interval: 60      # seconds between health pings
  proactive_warmup_threshold: 0.8  # utilization ratio to trigger warmup
  queue_max_size: 50
  matlab_root: null              # auto-detect, or set explicit path

execution:
  sync_timeout: 30               # seconds before auto-promoting to async
  max_execution_time: 86400      # hard limit per job (24h)
  workspace_isolation: true
  engine_affinity: false         # pin session to engine for workspace persistence
  temp_dir: "./temp"
  temp_cleanup_on_disconnect: true

workspace:
  default_paths:                 # added to MATLAB path on engine start/reset
    - "/shared/custom_libs"
    - "/shared/data"
  startup_commands:              # run on each engine start and after workspace reset
    - "format long"

toolboxes:
  mode: "whitelist"              # whitelist | blacklist | all
  list:
    - "Signal Processing Toolbox"
    - "Optimization Toolbox"
    - "Statistics and Machine Learning Toolbox"
    - "Image Processing Toolbox"

custom_tools:
  config_file: "./custom_tools.yaml"

security:
  blocked_functions_enabled: true
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"
  max_upload_size_mb: 100
  require_proxy_auth: false      # set true to acknowledge SSE is behind auth proxy

code_checker:
  enabled: true
  auto_check_before_execute: false
  severity_levels: ["error", "warning"]

output:
  plotly_conversion: true
  static_image_format: "png"     # png | jpg | svg
  static_image_dpi: 150
  thumbnail_enabled: true
  thumbnail_max_width: 400
  large_result_threshold: 10000  # elements — above this, save tabular/matrix data to file
  max_inline_text_length: 50000  # chars — above this, save text output to file

sessions:
  max_sessions: 50
  session_timeout: 3600          # seconds of inactivity before cleanup
  job_retention_seconds: 86400   # how long to keep completed job metadata

```

## Startup & Shutdown

### Startup Sequence

1. Load and validate `config.yaml` (with env var overrides)
2. Resolve all relative paths to absolute
3. Create `result_dir`, `temp_dir`, `log_dir` if they don't exist
4. Load `custom_tools.yaml` and validate tool definitions
5. Start `min_engines` MATLAB engines in parallel
6. If fewer than `min_engines` start successfully, log error and exit with non-zero code
7. Register all MCP tools (core + custom)
8. Start health check background task
9. Begin accepting MCP connections

### Graceful Shutdown (SIGTERM / SIGINT)

1. Stop accepting new connections
2. Wait for all `RUNNING` jobs to complete (up to a configurable drain timeout, default: 300s)
3. Cancel any remaining `PENDING` jobs
4. If drain timeout exceeded, force-cancel running jobs
5. Clean up all session temp directories
6. Shut down all MATLAB engines
7. Exit

## Project Structure

```
matlab-mcp-server-python/
├── config.yaml
├── custom_tools.yaml
├── pyproject.toml
├── README.md
├── LICENSE (MIT)
├── src/
│   └── matlab_mcp/
│       ├── __init__.py
│       ├── server.py              # MCP server entry point, tool registration
│       ├── config.py              # YAML config loading, validation, env overrides
│       ├── pool/
│       │   ├── __init__.py
│       │   ├── manager.py         # elastic pool manager
│       │   ├── engine.py          # single engine wrapper (start/stop/health/reset)
│       │   └── scheduler.py       # job queue, engine assignment
│       ├── jobs/
│       │   ├── __init__.py
│       │   ├── models.py          # job data model (status, result, progress)
│       │   ├── tracker.py         # job store, lifecycle, pruning
│       │   └── executor.py        # sync/async execution, timeout promotion
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── core.py            # execute_code, check_code, workspace tools
│       │   ├── discovery.py       # list_toolboxes, list_functions, get_help
│       │   ├── jobs.py            # get_job_status, get_job_result, cancel, list
│       │   ├── files.py           # upload_data, delete_file, list_files
│       │   ├── custom.py          # custom tool loader from YAML
│       │   └── admin.py           # get_pool_status
│       ├── output/
│       │   ├── __init__.py
│       │   ├── formatter.py       # result formatting, inline vs file decisions
│       │   ├── plotly_convert.py  # Python-side Plotly JSON handling
│       │   └── thumbnail.py       # image thumbnailing
│       ├── session/
│       │   ├── __init__.py
│       │   └── manager.py         # session lifecycle, namespace isolation, cleanup
│       ├── security/
│       │   ├── __init__.py
│       │   └── validator.py       # function blocklist, filename sanitization
│       └── matlab_helpers/
│           ├── mcp_fig2plotly.m   # MATLAB figure → Plotly JSON converter
│           ├── mcp_checkcode.m    # code checker wrapper (handles temp file creation)
│           └── mcp_progress.m     # progress reporting helper
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_pool.py
│   ├── test_jobs.py
│   ├── test_tools.py
│   ├── test_output.py
│   ├── test_security.py
│   └── mocks/
│       └── matlab_engine_mock.py  # mock matlab.engine for CI without MATLAB
└── docs/
    └── superpowers/
        └── specs/
```

## Tech Stack

- **Python 3.9+** (matches 2020b engine API support)
- **mcp[cli]** — MCP Python SDK (FastMCP)
- **pyyaml** — config parsing
- **pydantic** — config validation, data models
- **Pillow** — thumbnail generation
- **matlab.engine** — MATLAB Engine API (installed from MATLAB, not pip)

## Cross-Platform Notes

- File paths use `pathlib.Path` throughout (Windows/Mac compatible)
- MATLAB root auto-detection handles both OS default install locations:
  - macOS: `/Applications/MATLAB_R*.app`
  - Windows: `C:\Program Files\MATLAB\R*`
- Temp directories use Python's `tempfile` module for OS-appropriate paths
- Engine pool max auto-capped on macOS (see macOS limitation note above)
