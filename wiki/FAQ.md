# FAQ

## General

### What MATLAB versions are supported?

MATLAB 2020b and later. The MATLAB Engine API for Python must be installed separately from your MATLAB installation.

### Does it work without MATLAB installed?

No. The server requires a local MATLAB installation with the Engine API. It connects to real MATLAB engines, not a simulator.

### Can I use it with MATLAB Online?

Not currently. The server connects to locally-installed MATLAB via the Engine API, which requires a local installation.

### What AI agents work with this?

Any agent that supports the Model Context Protocol (MCP): Claude Desktop, Claude Code, Cursor, GitHub Copilot (with MCP support), and custom agents built with MCP SDKs.

### Can I install it from PyPI?

Yes:
```bash
pip install matlab-mcp-python
```

You still need to install the MATLAB Engine API separately from your MATLAB installation. See [[Installation]].

### Can I run it in Docker?

Yes. The project includes a `Dockerfile` and `docker-compose.yml`. The Docker image does **not** include MATLAB — you must mount your own MATLAB installation as a volume. See [[Installation]] for Docker setup instructions.

## Setup

### How do I install the MATLAB Engine API?

```bash
cd /Applications/MATLAB_R2024a.app/extern/engines/python  # macOS
pip install .
```

Adjust the path for your MATLAB version and OS. See [[Installation]] for details.

### stdio vs SSE — which should I use?

- **stdio:** Single user, simple setup. The AI agent launches the server process directly.
- **SSE:** Multiple users, shared server. Users connect over HTTP. Requires more setup but supports concurrent access.

### Can I run the server remotely?

Yes, with SSE transport. Start the server on a remote machine and connect via HTTP. **Always** put it behind a reverse proxy with authentication for production use.

## Usage

### How does async execution work?

Code that finishes within `sync_timeout` (30s default) returns immediately. Longer code is automatically promoted to an async job — the agent gets a `job_id` and can poll for progress. See [[Async Jobs]].

### How do I report progress from long-running jobs?

Use the `mcp_progress()` helper in your MATLAB code:

```matlab
mcp_progress(__mcp_job_id__, 50, 'Halfway done');
```

### Can I use my own MATLAB functions?

Yes, two ways:

1. **Custom tools (recommended):** Define them in `custom_tools.yaml` and they become first-class MCP tools. See [[Custom Tools]].
2. **Path configuration:** Add your function directories to `workspace.default_paths` in config, then call them via `execute_code`.

### Are MATLAB plots interactive?

Yes! MATLAB figures are automatically converted to Plotly JSON, which renders as interactive charts in web-based clients. A static PNG is also generated as a fallback.

### What plot types are supported for Plotly conversion?

Line, scatter, bar, histogram, surface, and image plots. Complex custom graphics may fall back to static PNG.

### Can I read files back from the session?

Yes, three tools are available:
- **`read_script`** — read `.m` script files as text
- **`read_data`** — read data files (`.mat`, `.csv`, `.json`, `.txt`, `.xlsx`) with summary or raw mode
- **`read_image`** — read image files (`.png`, `.jpg`, `.gif`) as inline images that render in agent UIs

Use `list_files` first to see what files are available in your session.

## Performance

### How many engines should I run?

- **Personal use:** 1-2 engines
- **Small team (2-5 users):** 2-4 engines
- **Larger team:** Scale based on concurrent usage, up to your MATLAB license limit

On macOS, MATLAB limits you to ~4 concurrent engines.

### Will it slow down my MATLAB?

Each engine is an independent MATLAB process. Running multiple engines uses memory proportional to the number of engines (typically 500MB-2GB per engine depending on loaded toolboxes).

### What happens when all engines are busy?

Requests queue up (configurable `queue_max_size`, default 50). If the pool hasn't reached `max_engines`, a new engine is started proactively. Requests are served FIFO as engines become available.

## Security

### Is it safe to expose over the network?

For SSE transport:
- **Always** put it behind an authenticating reverse proxy
- Set `require_proxy_auth: true` in config
- Bind to `127.0.0.1` if the proxy is on the same machine

### Can agents run arbitrary system commands?

No. The security validator blocks `system()`, `unix()`, `dos()`, `!`, `eval()`, `feval()`, `evalc()`, `evalin()`, `assignin()`, `perl()`, and `python()` by default. You can customize the blocklist. See [[Security]].

### Are user sessions isolated?

Yes. When `workspace_isolation: true` (default), the workspace is fully cleared between sessions: `clear all; clear global; clear functions; fclose all; restoredefaultpath`.

## Development

### How do I run tests?

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests use a mock MATLAB engine — no MATLAB installation needed for testing.

### How do I add a new MCP tool?

1. Create the implementation in `src/matlab_mcp/tools/`
2. Register it in `server.py` with `@mcp.tool`
3. Add tests in `tests/`

### Can I contribute?

Yes! Open an issue or PR on [GitHub](https://github.com/HanSur94/matlab-mcp-server-python).
