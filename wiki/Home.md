# MATLAB MCP Server

A Python [Model Context Protocol](https://modelcontextprotocol.io/) server that lets any MCP-compatible AI coding agent (Claude Code, Cursor, Codex CLI, custom agents) execute MATLAB code, inspect workspaces, manage session files, and monitor server health. It bridges MCP to MATLAB's Engine API with an elastic engine pool, per-session workspace isolation, and async job orchestration.

- **Package:** `matlab-mcp-python` (v2.1.0) · **CLI:** `matlab-mcp` · **License:** MIT · **Repo:** [HanSur94/matlab-mcp-server-python](https://github.com/HanSur94/matlab-mcp-server-python)

## Features

| Feature | What it does |
|---|---|
| Execute MATLAB code | Runs code in a session's engine; auto-promotes to an async job when it exceeds `execution.sync_timeout` |
| Code linting | `check_code` runs `checkcode`/`mlint` and returns issues with line, column, severity |
| Toolbox discovery | List installed toolboxes (`ver`), functions (`help <toolbox>`), and help text (`help <fn>`) |
| Session isolation | Per-session temp directory and workspace; idle sessions cleaned up automatically |
| Elastic engine pool | Scales MATLAB engines between `min_engines` and `max_engines` on demand, with health checks |
| Async jobs | Long jobs tracked by `job_id` — poll status, fetch results, cancel, or list them |
| File management | Upload (base64), read (`.mat`/`.csv`/`.json`/`.txt`/`.xlsx`), read images, list, delete — scoped to the session temp dir |
| Interactive plots | Figures optionally converted to Plotly JSON, with static-image and thumbnail output |
| Custom tools | Expose your own `.m` functions as first-class MCP tools via `custom_tools.yaml` |
| Monitoring | Metrics, health status, error log, and a live HTML dashboard |
| Human-in-the-loop | Optional approval gate (`hitl`) for protected functions, file ops, or all executions |
| Bearer auth | Optional token auth for HTTP transports via `MATLAB_MCP_AUTH_TOKEN` |

There are **20 built-in tools** plus any user-defined custom tools. See [MCP Tools Reference](MCP-Tools-Reference).

## Platform Support

| Platform | Notes |
|---|---|
| Windows 10 | No admin rights required — no service install, no elevated ports |
| macOS | `osx-64`, `osx-arm64`; `pool.max_engines > 4` emits a stability warning |
| Linux | `linux-64` |
| Python | 3.10, 3.11, 3.12 |
| MATLAB | R2022b or newer, with the MATLAB Engine API for Python |
| FastMCP | 3.4.4 |
| Transports | `stdio` (default, local), `streamablehttp` (recommended HTTP), `sse` (legacy, deprecated) |

The MATLAB engine is installed from PyPI (`matlabengine`, matched to your local release) by `scripts/install_matlab_engine.py` — not a static dependency. See [Installation](Installation) for the release map and offline options.

## Quick Start

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
pixi run start            # server comes up; MATLAB tools inert until engine installed
pixi run install-engine   # detect local MATLAB release, install matching matlabengine
pixi run start            # full start
```

Register with Claude Code: `claude mcp add matlab -- matlab-mcp`

## Wiki Navigation

- [Installation](Installation) — Pixi, `install.bat`, pip, and Docker install methods; MATLAB engine setup
- [Configuration](Configuration) — Full `config.yaml` reference, env-var overrides, transports, ports, auth
- [MCP Tools Reference](MCP-Tools-Reference) — All 20 built-in tools with parameters and behavior
- [Custom Tools](Custom-Tools) — Expose your own `.m` functions as AI-callable tools
- [Examples](Examples) — Ready-to-run MATLAB examples for common tasks
- [Architecture](Architecture) — Engine pool, async jobs, session model, monitoring
- [Async Jobs](Async-Jobs) — Long-running jobs, status polling, cancellation, retention
- [Security](Security) — Function blocklist, workspace isolation, upload limits, bearer auth
- [Troubleshooting](Troubleshooting) — Common issues and solutions
- [FAQ](FAQ) — Frequently asked questions

## Getting Help

- [GitHub Issues](https://github.com/HanSur94/matlab-mcp-server-python/issues)
- [README](https://github.com/HanSur94/matlab-mcp-server-python#readme)
