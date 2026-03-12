# MATLAB MCP Server (Python)

A Python-based [MCP](https://modelcontextprotocol.io/) server that exposes MATLAB capabilities to any AI agent. Run MATLAB code, discover toolboxes, check code quality, and get interactive Plotly plots — all through the Model Context Protocol.

## Features

- **Execute MATLAB code** — sync for fast commands, auto-async for long-running jobs
- **Elastic engine pool** — scales from min to max engines based on demand
- **Toolbox discovery** — list installed toolboxes, browse functions, read help
- **Code checker** — run `checkcode`/`mlint` on code before execution
- **Interactive plots** — figures converted to Plotly JSON for web rendering
- **Multi-user support** — SSE transport with session isolation
- **Fully configurable** — single YAML config, env var overrides
- **Cross-platform** — Windows and macOS, MATLAB 2020b+

## Quick Start

### Prerequisites

- Python 3.9+
- MATLAB 2020b or newer (with MATLAB Engine API for Python installed)

### Install

```bash
pip install -e ".[dev]"
```

### Configure

Edit `config.yaml` or use environment variables:

```bash
export MATLAB_MCP_POOL_MIN_ENGINES=2
export MATLAB_MCP_POOL_MAX_ENGINES=8
```

### Run

```bash
# stdio transport (single user)
matlab-mcp

# SSE transport (multi-user)
matlab-mcp config.yaml  # with transport: sse in config
```

### Add to Claude Desktop

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp",
      "args": []
    }
  }
}
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `execute_code` | Run MATLAB code (auto sync/async) |
| `get_job_status` | Check async job progress |
| `get_job_result` | Get completed job result |
| `cancel_job` | Cancel pending/running job |
| `list_jobs` | List session jobs |
| `check_code` | Run checkcode/mlint |
| `list_toolboxes` | List MATLAB toolboxes |
| `list_functions` | List toolbox functions |
| `get_help` | Get function help text |
| `get_workspace` | Show workspace variables |
| `upload_data` | Upload files to session |
| `delete_file` | Delete session file |
| `list_files` | List session files |
| `get_pool_status` | Engine pool status |

## Async Jobs

Long-running MATLAB code (simulations, optimizations, etc.) is automatically promoted to async after a configurable timeout (default: 30 seconds):

1. Call `execute_code` with your MATLAB code
2. If it finishes quickly, results are returned inline
3. If it takes longer, you get a `job_id` back
4. Poll with `get_job_status` (includes progress if your code uses `mcp_progress`)
5. Retrieve results with `get_job_result`

### Progress Reporting

Your MATLAB code can report progress:

```matlab
for i = 1:1000
    % ... computation ...
    mcp_progress(__mcp_job_id__, i/1000*100, sprintf('Iteration %d/1000', i));
end
```

## Interactive Plots

Figures are automatically converted to [Plotly](https://plotly.com/) JSON for interactive rendering in web UIs:

```matlab
x = linspace(0, 2*pi, 100);
plot(x, sin(x));
title('Sine Wave');
xlabel('x');
ylabel('sin(x)');
```

Returns: Plotly JSON (interactive) + PNG (static) + base64 thumbnail.

## Custom Tools

Define custom MATLAB functions as first-class MCP tools in `custom_tools.yaml`:

```yaml
tools:
  - name: run_simulation
    matlab_function: mylib.run_sim
    description: "Run physics simulation"
    parameters:
      - name: model_name
        type: string
        required: true
      - name: duration
        type: double
        default: 100.0
    returns: "Struct with fields: time, state, energy"
```

## Configuration

All settings in `config.yaml` with sensible defaults. Key sections:

| Section | What it controls |
|---------|-----------------|
| `server` | Transport (stdio/sse), host, port, logging |
| `pool` | Engine count (min/max), timeouts, health checks |
| `execution` | Sync timeout, max execution time, workspace isolation |
| `toolboxes` | Whitelist/blacklist/all mode for toolbox discovery |
| `security` | Function blocklist, upload limits |
| `output` | Plotly conversion, image format, thumbnails |
| `sessions` | Max sessions, timeout, job retention |

Environment variable overrides: `MATLAB_MCP_<SECTION>_<KEY>=value`

## Security

- **Function blocklist** — blocks `system()`, `unix()`, `dos()`, `!` shell escape by default
- **Filename sanitization** — prevents path traversal in file uploads
- **Session isolation** — workspace cleared between users
- **SSE auth** — deploy behind reverse proxy with authentication for production

## License

MIT
