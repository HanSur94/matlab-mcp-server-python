# MATLAB MCP Server — Design Specification

**Date:** 2026-03-12
**Repo:** HanSur94/matlab-mcp-server-python
**Status:** Approved

## Overview

A Python-based MCP (Model Context Protocol) server that exposes MATLAB capabilities to any AI agent. Runs on a shared MATLAB server, supports multiple concurrent users with long-running jobs, and works with MATLAB 2020b+.

## Goals

- Expose MATLAB toolboxes and custom libraries to any MCP-compatible AI agent
- Support multiple concurrent users on a shared MATLAB server
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

## MATLAB Engine Pool

### Elastic Scaling

- **min_engines** (default: 2) — pre-started at server launch, always warm
- **max_engines** (default: 10) — hard ceiling, never exceeded
- **Scale-up:** when all engines are busy and a new request arrives, spawn a new engine
- **Scale-down:** idle engines beyond min_engines shut down after configurable timeout (default: 15 min)
- **Health checks:** periodic ping to detect crashed engines, auto-replace

### Engine Assignment

- Short sync jobs: engine returned to pool immediately after execution
- Long async jobs: engine stays assigned until job completes
- Pool exhausted at max: request queued, estimated wait time returned to agent

### Workspace Isolation

- `clear all` before assigning engine to new user/job
- Each user session gets a unique temp directory
- Temp directories cleaned up on session end

### Crash Recovery

- Engine crash mid-job: job marked `failed` with error message
- Dead engine removed from pool, fresh one spawned if below max

## Async Job System

### Job Lifecycle

```
PENDING → RUNNING → COMPLETED
                  → FAILED
         → CANCELLED
```

### Hybrid Sync/Async Execution

1. `execute_code` called → job created as PENDING
2. Engine assigned → job moves to RUNNING
3. If completes within `sync_timeout` (default: 30s) → result returned inline
4. If exceeds timeout → auto-promoted to async, returns job ID immediately
5. Agent polls via `get_job_status` / retrieves via `get_job_result`

### Job Storage

- In-memory dict (no external dependencies)
- Configurable retention period, old jobs pruned automatically
- Job result files persist in `result_dir` until session cleanup

### Progress Reporting

- MATLAB code can write progress to a progress file
- `get_job_status` returns progress percentage if available

## MCP Tools

### Core Tools (always available)

| Tool | Description |
|------|-------------|
| `execute_code` | Run arbitrary MATLAB code. Sync with auto-promote to async |
| `get_job_status` | Check status of an async job |
| `get_job_result` | Retrieve result of a completed async job |
| `cancel_job` | Cancel a running async job |
| `list_jobs` | List all jobs for the current session |
| `check_code` | Run MATLAB's checkcode/mlint on code or .m file |
| `list_toolboxes` | List installed and exposed toolboxes |
| `list_functions` | List functions in a given toolbox |
| `get_help` | Get MATLAB help text for any function |
| `get_workspace` | Show current variables in session workspace |
| `upload_data` | Upload data (CSV, MAT) to session temp directory |
| `list_files` | List files in session temp directory |
| `get_pool_status` | Show engine pool status |

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

Each entry becomes a first-class MCP tool with proper schema.

### Toolbox Exposure

Configurable via whitelist/blacklist/all mode in `config.yaml`. Only listed toolboxes have functions discoverable via `list_functions`.

## Result Formatting

### Result Structure

```json
{
  "status": "completed",
  "output": {
    "text": "ans = 42\n",
    "variables": {"ans": {"type": "double", "size": [1, 1], "value": 42}},
    "figures": [
      {
        "plotly_json": { "data": [], "layout": {} },
        "thumbnail_base64": "iVBOR...",
        "file_path": "/results/j-abc123/figure_1.png"
      }
    ],
    "files": [
      {"path": "/results/j-abc123/output.mat", "size_bytes": 104200}
    ],
    "warnings": [],
    "errors": []
  },
  "execution_time_seconds": 1.23
}
```

### Plotly Conversion (2020b compatible)

Bundled MATLAB helper `mcp_fig2plotly.m` that:
1. Extracts figure data via `get(gca)`, `get(findobj(...))`
2. Builds Plotly-compatible JSON struct in MATLAB
3. Returns to Python as dict via matlab.engine

Supported plot types: line, scatter, bar, histogram, surface/mesh, contour, images, heatmaps.

Fallback: static PNG if conversion fails for unsupported plot types.

### Output Strategy

- Small text results → inline in MCP response
- Figures → Plotly JSON + static PNG + base64 thumbnail
- Large data (above threshold) → saved to file, path returned with summary

## Configuration

Single `config.yaml` with all settings. Every setting has a sensible default. Environment variables can override any setting (e.g., `MATLAB_MCP_POOL_MAX_ENGINES=20`). Config validated on startup with clear error messages.

```yaml
server:
  name: "matlab-mcp-server"
  transport: "stdio"           # stdio | sse
  host: "0.0.0.0"
  port: 8765
  log_level: "info"
  log_file: "./logs/server.log"
  result_dir: "./results"

pool:
  min_engines: 2
  max_engines: 10
  scale_down_idle_timeout: 900
  engine_start_timeout: 120
  health_check_interval: 60
  queue_max_size: 50
  matlab_root: null

execution:
  sync_timeout: 30
  max_execution_time: 86400
  workspace_isolation: true
  temp_dir: "./temp"
  temp_cleanup_on_disconnect: true

workspace:
  default_paths:
    - "/shared/custom_libs"
    - "/shared/data"
  startup_commands:
    - "format long"
    - "warning('off','all')"

toolboxes:
  mode: "whitelist"
  list:
    - "Signal Processing Toolbox"
    - "Optimization Toolbox"
    - "Statistics and Machine Learning Toolbox"
    - "Image Processing Toolbox"

custom_tools:
  config_file: "./custom_tools.yaml"

code_checker:
  enabled: true
  auto_check_before_execute: false
  severity_levels: ["error", "warning"]

output:
  plotly_conversion: true
  static_image_format: "png"
  static_image_dpi: 150
  thumbnail_enabled: true
  thumbnail_max_width: 400
  large_result_threshold: 10000
  max_inline_text_length: 50000

sessions:
  namespace_isolation: true
  max_sessions: 50
  session_timeout: 3600
```

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
│       ├── server.py
│       ├── config.py
│       ├── pool/
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   ├── engine.py
│       │   └── scheduler.py
│       ├── jobs/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── tracker.py
│       │   └── executor.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── core.py
│       │   ├── discovery.py
│       │   ├── jobs.py
│       │   ├── files.py
│       │   ├── custom.py
│       │   └── admin.py
│       ├── output/
│       │   ├── __init__.py
│       │   ├── formatter.py
│       │   ├── plotly_convert.py
│       │   └── thumbnail.py
│       ├── session/
│       │   ├── __init__.py
│       │   └── manager.py
│       └── matlab_helpers/
│           ├── mcp_fig2plotly.m
│           ├── mcp_checkcode.m
│           └── mcp_progress.m
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_pool.py
│   ├── test_jobs.py
│   ├── test_tools.py
│   ├── test_output.py
│   └── mocks/
│       └── matlab_engine_mock.py
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
- **matlab.engine** — MATLAB Engine API (installed from MATLAB)

## Cross-Platform Notes

- File paths use `pathlib.Path` throughout (Windows/Mac compatible)
- MATLAB root auto-detection handles both OS default install locations
- Temp directories use Python's `tempfile` module for OS-appropriate paths
