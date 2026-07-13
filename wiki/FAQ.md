# FAQ

## MATLAB & platform

### Do I need MATLAB installed?

Yes. The server connects to a real, locally-installed MATLAB via the MATLAB Engine API for Python — it is not a simulator. No MATLAB, no code execution.

You *can* start the server without MATLAB (`pixi run start` or `matlab-mcp --inspect`) to verify it comes up, but the MATLAB-backed tools stay inert until the engine is installed.

### Which MATLAB releases are supported?

MATLAB **R2022b or newer**, with the Engine API for Python. The matching `matlabengine` PyPI package is installed for you by `scripts/install_matlab_engine.py`, which detects your local release and picks the correct version:

| MATLAB release | `matlabengine` spec |
|---|---|
| R2022b | `matlabengine==9.13.*` |
| R2023a | `matlabengine==9.14.*` |
| R2023b | `matlabengine==9.15.*` |
| R2024a | `matlabengine==24.1.*` |
| R2024b | `matlabengine==24.2.*` |
| R2025a | `matlabengine==25.1.*` |
| R2025b | `matlabengine==25.2.*` |
| R2026a | `matlabengine==26.1.*` |

The newest detected release wins. Force a specific one with the `MATLAB_RELEASE` environment variable. See [Installation](Installation).

### Which Python versions are supported?

Python **3.10, 3.11, and 3.12**.

### Can I use MATLAB Online?

No. The Engine API requires a local MATLAB installation. MATLAB Online is not supported.

### Does it run on Windows without admin rights?

Yes — that is a core design goal. No service installation and no elevated ports are required. Use **Pixi** (`pixi run start` then `pixi run install-engine`) or the one-click **`install.bat`**, both no-admin. See [Installation](Installation).

## Setup & offline

### How do I install the MATLAB engine?

You don't build it from the MATLAB tree by hand anymore. The engine is installed from PyPI, matched to your local release:

```bash
pixi run install-engine
# or, without Pixi:
python scripts/install_matlab_engine.py
```

`install.bat` runs the same script under the hood. `matlabengine` is deliberately **not** a static project dependency (its sdist build reads your local MATLAB install and fails on machines without a matching release), so `pip install matlab-mcp-python` alone does not pull it in — install it separately.

### Does it work offline / air-gapped?

Yes. Set `MATLAB_MCP_VENDOR` to install the engine from your local MATLAB tree (`<MATLABROOT>/extern/engines/python`) instead of PyPI. This path is also taken automatically if the online pip install fails. It requires `MATLABROOT` to be available.

- Pixi: `pixi run install-engine-offline`
- `install.bat` bundles the vendored path and offline pip flags (`--no-index --find-links`).

### I get an error about the old package name

If you previously installed `matlab-mcp-server`, uninstall it first:

```bash
pip uninstall matlab-mcp-server
pip install matlab-mcp-python
```

## Agents & transports

### What AI agents work with this?

Any client that speaks the Model Context Protocol (MCP): Claude Code, Claude Desktop, Cursor, and custom agents built on MCP SDKs.

Config-file registration:

```json
{ "mcpServers": { "matlab": { "command": "matlab-mcp" } } }
```

Claude Code CLI:

```bash
claude mcp add matlab -- matlab-mcp
```

### Which transport should I use for which agent?

Three transports are available (`--transport`):

- **`stdio`** (default) — for a single local client that launches the server process directly (Claude Code, Claude Desktop, Cursor). Simplest setup.
- **`streamablehttp`** — the **recommended** HTTP transport for shared / multi-user or remote setups (FastMCP 3.4.4 streamable-http). Endpoint: `http://<host>:<port>/mcp`.
- **`sse`** — legacy, kept only for back-compat with existing SSE clients. Deprecated; it logs a deprecation warning at startup and will be removed in a future release. Prefer `streamablehttp` for anything new.

With Pixi: `pixi run start` (stdio), `pixi run http` (streamablehttp), `pixi run sse` (legacy).

### Can I run the server remotely / for multiple users?

Yes — use `streamablehttp` and start the server on a shared or remote machine. Each session gets an isolated workspace and temp directory. For any network-exposed deployment, enable authentication (below) or front it with an authenticating reverse proxy. See [Configuration](Configuration) and [Security](Security).

### How do I add authentication for HTTP transports?

Set a bearer token via the `MATLAB_MCP_AUTH_TOKEN` environment variable (never in `config.yaml`). It is enforced on `sse`/`streamablehttp` requests via `Authorization: Bearer <token>`.

Generate one with:

```bash
matlab-mcp --generate-token   # or: pixi run generate-token
```

If `MATLAB_MCP_AUTH_TOKEN` is unset, **auth is disabled and all HTTP requests are accepted** (the server logs a warning). The `/health` path and CORS pre-flight `OPTIONS` requests bypass auth.

## Usage

### How does async execution work?

Code that finishes within `execution.sync_timeout` (30s default) returns inline. Longer code is automatically promoted to an async job — the agent gets a `job_id` and polls with `get_job_status` / `get_job_result`. See [Async Jobs](Async-Jobs).

### How do I report progress from long-running jobs?

Use the `mcp_progress` helper in your MATLAB code:

```matlab
mcp_progress(__mcp_job_id__, 50, 'Halfway done');
```

### Can I use my own MATLAB functions?

Two ways:

1. **Custom tools (recommended):** define them in `custom_tools.yaml` and they register as first-class MCP tools. See [Custom Tools](Custom-Tools).
2. **Path configuration:** add your function directories to `workspace.default_paths`, then call them via `execute_code`.

### Can I read files back from a session?

Yes:

- **`read_script`** — read a `.m` script as text
- **`read_data`** — read `.mat` / `.csv` / `.json` / `.txt` / `.xlsx` (`format`: `summary` or `raw`)
- **`read_image`** — read `.png` / `.jpg` / `.gif` as an inline image block

Use `list_files` first to see what's in the session temp directory.

## Plotting (MATLAB → Plotly)

### Are MATLAB plots interactive?

Yes. Every MATLAB figure is automatically converted to interactive Plotly JSON (renderable in any web UI), with a static PNG + thumbnail generated as a fallback for non-interactive clients. No extra code in your MATLAB is needed.

The pipeline: `mcp_extract_props.m` pulls figure properties (axes, line data, labels, colors, markers, legends, subplots), a style mapper converts MATLAB styles to Plotly equivalents (`--` → `dash`, `o` → `circle`, etc.), and the result comes back as Plotly JSON.

### What plot types convert well?

Line, scatter, bar, area, subplots (`subplot` / `tiledlayout`), multiple axes, and log/linear scales. Line styles, marker shapes, RGB colors, line widths, font sizes, axis labels/limits, titles, legends, grid lines, and background colors are preserved. Complex custom graphics may fall back to the static PNG.

Plotly conversion is controlled by the `output` config section (`plotly_conversion`, `static_image_format`, `thumbnail_enabled`, …).

## Security & sandboxing

### Is my code sandboxed?

There is code-level protection, not OS-level sandboxing. A security validator blocks dangerous MATLAB functions before execution — by default: `system`, `unix`, `dos`, `!`, `eval`, `feval`, `evalc`, `evalin`, `assignin`, `perl`, `python`, `str2func`, `builtin`, `run`. The blocklist is configurable under `security.blocked_functions`.

Beyond that: filenames are sanitized against path traversal, uploads are size-limited (`security.max_upload_size_mb`, 100 MB default), and file tools operate only inside the per-session temp directory. For approval gating on specific functions or all executions, see the `hitl` (human-in-the-loop) config section. See [Security](Security).

### Are user sessions isolated?

Yes. With `execution.workspace_isolation: true` (default), the MATLAB workspace is fully cleared between sessions (`clear all; clear global; clear functions; fclose all; restoredefaultpath`), and each session has its own temp directory.

### Can agents run arbitrary system commands?

Not by default — `system()`, `unix()`, `dos()`, and `!` are on the blocklist. This is a code filter, so treat network-exposed deployments with the usual care: enable auth and/or a reverse proxy.

## Docker & licensing

### Can I run it in Docker?

Yes, but Docker is intended for **network-license** deployments, not home/individual-license Windows 10 laptops (use Pixi or `install.bat` for those).

The image builds `FROM mathworks/matlab:<release>` and installs the matching `matlabengine` — MATLAB is inside the image, so you must supply a **network license**:

```bash
docker build -t matlab-mcp .
docker run -p 8765:8765 -p 8766:8766 \
  -e MLM_LICENSE_FILE=port@host \
  matlab-mcp
# or: docker compose up
```

`docker-compose.yml` fails fast if `MLM_LICENSE_FILE` is unset, defaults the transport to `streamablehttp`, and caps `MATLAB_MCP_POOL_MAX_ENGINES=2` (each engine consumes one license seat). The container's `HEALTHCHECK` hits `http://localhost:8765/health`.

## Performance

### How many engines should I run?

Configured via `pool.min_engines` / `pool.max_engines` (defaults 2 / 10). Personal use is fine with 1–2; scale up for concurrent users, bounded by your MATLAB license seats. On **macOS**, running more than 4 `matlab.engine` instances in one process is unstable — the server emits a warning above `pool.max_engines > 4` (it warns; it does not hard-cap).

### What happens when all engines are busy?

Requests queue (`pool.queue_max_size`, default 50) and are served FIFO. If the pool hasn't hit `max_engines`, a new engine is started on demand.

## Development

### How do I run tests?

```bash
pip install -e ".[dev]"
pytest tests/ -v          # or: pixi run test
```

Tests use a mock MATLAB engine — no MATLAB installation needed.

### Can I contribute?

Yes. Open an issue or PR on [GitHub](https://github.com/HanSur94/matlab-mcp-server-python).

---

See also: [Installation](Installation) · [Configuration](Configuration) · [Security](Security) · [Custom Tools](Custom-Tools) · [Async Jobs](Async-Jobs)
