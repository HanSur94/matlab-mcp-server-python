<p align="center">
  <h1 align="center">MATLAB MCP Server</h1>
  <p align="center">
    Give any AI agent the power of MATLAB — via the Model Context Protocol
  </p>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#examples">Examples</a> &bull;
  <a href="#mcp-tools-reference">Tools Reference</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="https://github.com/HanSur94/matlab-mcp-server-python/wiki">Wiki</a>
</p>

---

A Python MCP server that connects **any AI agent** (Claude, Cursor, Copilot, custom agents) to a shared MATLAB installation. Execute code, discover toolboxes, check code quality, get interactive Plotly plots, and run long simulations — all through [MCP](https://modelcontextprotocol.io/).

## Why?

- Your AI agent can now **write and run MATLAB code** directly
- **Long-running jobs** (hours!) run async — the agent keeps working while MATLAB computes
- **Multiple users** share one MATLAB server via an elastic engine pool
- **Interactive plots** come back as Plotly JSON — renderable in any web UI
- **Custom MATLAB libraries** become first-class AI tools with zero code changes

## Features

| Feature | Description |
|---------|-------------|
| Execute MATLAB code | Sync for fast commands, auto-async for long jobs |
| Elastic engine pool | Scales 2-10+ engines based on demand |
| Toolbox discovery | Browse installed toolboxes, functions, help text |
| Code checker | Run `checkcode`/`mlint` before execution |
| Interactive plots | Figures auto-converted to Plotly JSON |
| Multi-user (SSE) | Session isolation with per-user workspaces |
| Custom tools | Expose your `.m` functions as MCP tools via YAML |
| Progress reporting | Long jobs report percentage back to the agent |
| Cross-platform | Windows + macOS, MATLAB 2020b+ |

## Quick Start

### Prerequisites

- **Python 3.9+**
- **MATLAB 2020b+** with the [MATLAB Engine API for Python](https://www.mathworks.com/help/matlab/matlab-engine-for-python.html) installed

```bash
# Install MATLAB Engine API (from your MATLAB installation)
cd /Applications/MATLAB_R2024a.app/extern/engines/python  # macOS
# cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"  # Windows
pip install .
```

### Install the server

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
pip install -e ".[dev]"
```

### Run it

```bash
# Single user (stdio) — simplest setup
matlab-mcp

# Multi-user (SSE) — shared server
matlab-mcp --transport sse
```

### Connect to Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp"
    }
  }
}
```

### Connect to Claude Code

```bash
claude mcp add matlab -- matlab-mcp
```

### Connect to Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp"
    }
  }
}
```

## Examples

### Basic: Run MATLAB Code

Ask your AI agent:

> "Calculate the eigenvalues of a 3x3 magic square in MATLAB"

The agent calls `execute_code`:
```matlab
A = magic(3);
eigenvalues = eig(A);
disp(eigenvalues)
```

Result returned inline:
```
15.0000
 4.8990
-4.8990
```

### Signal Processing

> "Generate a 1kHz sine wave, add noise, then filter it with a low-pass Butterworth filter and plot both"

```matlab
fs = 8000;
t = 0:1/fs:0.1;
clean = sin(2*pi*1000*t);
noisy = clean + 0.5*randn(size(t));

[b, a] = butter(6, 1500/(fs/2));
filtered = filter(b, a, noisy);

subplot(2,1,1); plot(t, noisy); title('Noisy Signal');
subplot(2,1,2); plot(t, filtered); title('Filtered Signal');
```

Returns: Interactive Plotly chart + static PNG + thumbnail.

### Long-Running Simulation (Async)

> "Run a Monte Carlo simulation with 1 million trials"

```matlab
n = 1e6;
results = zeros(n, 1);
for i = 1:n
    results(i) = simulate_trial();  % your custom function
    if mod(i, 1e5) == 0
        mcp_progress(__mcp_job_id__, i/n*100, sprintf('Trial %d/%d', i, n));
    end
end
disp(mean(results));
```

The agent gets a job ID immediately, polls progress ("Trial 500000/1000000 — 50%"), and retrieves results when done.

### Custom Tools

Expose your proprietary MATLAB functions as first-class AI tools. Create `custom_tools.yaml`:

```yaml
tools:
  - name: analyze_signal
    matlab_function: mylib.analyze_signal
    description: "Analyze a signal and return frequency components, SNR, and peak detection"
    parameters:
      - name: signal_path
        type: string
        required: true
        description: "Path to the signal data file (.mat)"
      - name: sample_rate
        type: double
        required: true
      - name: window_size
        type: int
        default: 1024
    returns: "Struct with fields: frequencies, magnitudes, snr, peaks"

  - name: train_model
    matlab_function: ml.train_classifier
    description: "Train a classification model on the given dataset"
    parameters:
      - name: dataset_path
        type: string
        required: true
      - name: model_type
        type: string
        default: "svm"
    returns: "Trained model object saved to workspace"
```

Now the agent can call `analyze_signal` or `train_model` directly — with full parameter validation and help text.

## MCP Tools Reference

### Code Execution

| Tool | Parameters | Description |
|------|-----------|-------------|
| `execute_code` | `code: str` | Run MATLAB code. Returns inline if fast (<30s), or a job ID if promoted to async |
| `check_code` | `code: str` | Run `checkcode`/`mlint`. Returns structured warnings/errors |
| `get_workspace` | — | Show variables in the current MATLAB workspace |

### Async Job Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_job_status` | `job_id: str` | Status + progress percentage for running jobs |
| `get_job_result` | `job_id: str` | Full result of a completed job |
| `cancel_job` | `job_id: str` | Cancel a pending or running job |
| `list_jobs` | — | List all jobs in this session |

### Discovery

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_toolboxes` | — | List installed MATLAB toolboxes |
| `list_functions` | `toolbox_name: str` | List functions in a toolbox |
| `get_help` | `function_name: str` | Get MATLAB help text for any function |

### File Management

| Tool | Parameters | Description |
|------|-----------|-------------|
| `upload_data` | `filename: str, content_base64: str` | Upload data files to the session |
| `delete_file` | `filename: str` | Delete a session file |
| `list_files` | — | List files in the session directory |

### Admin

| Tool | Parameters | Description |
|------|-----------|-------------|
| `get_pool_status` | — | Engine pool stats (available/busy/max) |

## Configuration

All settings live in `config.yaml` with sensible defaults. Override any setting via environment variables:

```bash
# Override pool size
export MATLAB_MCP_POOL_MIN_ENGINES=4
export MATLAB_MCP_POOL_MAX_ENGINES=16

# Override sync timeout (promote to async after 60s instead of 30s)
export MATLAB_MCP_EXECUTION_SYNC_TIMEOUT=60

# Override transport
export MATLAB_MCP_SERVER_TRANSPORT=sse
```

### Key Configuration Sections

<details>
<summary><b>Server</b> — transport, host, port, logging</summary>

```yaml
server:
  name: "matlab-mcp-server"
  transport: "stdio"        # stdio | sse
  host: "0.0.0.0"           # SSE only
  port: 8765                # SSE only
  log_level: "info"         # debug | info | warning | error
  log_file: "./logs/server.log"
  result_dir: "./results"
  drain_timeout_seconds: 300
```
</details>

<details>
<summary><b>Pool</b> — engine count, scaling, health checks</summary>

```yaml
pool:
  min_engines: 2            # always warm
  max_engines: 10           # hard ceiling
  scale_down_idle_timeout: 900   # 15 min
  engine_start_timeout: 120
  health_check_interval: 60
  proactive_warmup_threshold: 0.8
  queue_max_size: 50
  matlab_root: null         # auto-detect
```
</details>

<details>
<summary><b>Execution</b> — timeouts, workspace isolation</summary>

```yaml
execution:
  sync_timeout: 30          # seconds before async promotion
  max_execution_time: 86400 # 24h hard limit
  workspace_isolation: true
  engine_affinity: false    # pin session to engine
  temp_dir: "./temp"
  temp_cleanup_on_disconnect: true
```
</details>

<details>
<summary><b>Security</b> — function blocklist, upload limits</summary>

```yaml
security:
  blocked_functions_enabled: true
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"
  max_upload_size_mb: 100
  require_proxy_auth: false
```
</details>

<details>
<summary><b>Toolboxes</b> — whitelist/blacklist exposure</summary>

```yaml
toolboxes:
  mode: "whitelist"         # whitelist | blacklist | all
  list:
    - "Signal Processing Toolbox"
    - "Optimization Toolbox"
    - "Statistics and Machine Learning Toolbox"
    - "Image Processing Toolbox"
```
</details>

<details>
<summary><b>Output</b> — Plotly, images, thumbnails</summary>

```yaml
output:
  plotly_conversion: true
  static_image_format: "png"
  static_image_dpi: 150
  thumbnail_enabled: true
  thumbnail_max_width: 400
  large_result_threshold: 10000
  max_inline_text_length: 50000
```
</details>

## Architecture

```
AI Agent (Claude, Cursor, etc.)
       │
       │ MCP Protocol (stdio or SSE)
       ▼
┌─────────────────────────────┐
│   MCP Server (FastMCP)       │
│   14 tools + custom tools    │
│   Session manager            │
│   Result formatter           │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│   MATLAB Pool Manager        │
│   Elastic engine pool        │
│   Job scheduler (sync/async) │
│   Health checks & scaling    │
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────┐
│   MATLAB Engines (2020b+)    │
│   Engine 1 │ Engine 2 │ ... │
└─────────────────────────────┘
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (no MATLAB needed — uses mock engine)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=matlab_mcp --cov-report=term-missing

# Lint
ruff check src/ tests/
```

### Project Structure

```
src/matlab_mcp/
├── server.py          # MCP server entry point, tool registration
├── config.py          # YAML config, pydantic validation, env overrides
├── pool/
│   ├── engine.py      # Single MATLAB engine wrapper
│   └── manager.py     # Elastic pool manager
├── jobs/
│   ├── models.py      # Job data model, lifecycle
│   ├── tracker.py     # Job store, pruning
│   └── executor.py    # Sync/async execution, timeout promotion
├── tools/
│   ├── core.py        # execute_code, check_code, get_workspace
│   ├── discovery.py   # list_toolboxes, list_functions, get_help
│   ├── jobs.py        # job status, result, cancel, list
│   ├── files.py       # upload, delete, list files
│   ├── admin.py       # pool status
│   └── custom.py      # Custom tool loader from YAML
├── output/
│   ├── formatter.py   # Result formatting
│   ├── plotly_convert.py
│   └── thumbnail.py
├── session/
│   └── manager.py     # Session lifecycle, temp dirs
├── security/
│   └── validator.py   # Function blocklist, filename sanitization
└── matlab_helpers/
    ├── mcp_fig2plotly.m
    ├── mcp_checkcode.m
    └── mcp_progress.m
```

## Security

| Protection | Description |
|-----------|-------------|
| Function blocklist | Blocks `system()`, `unix()`, `dos()`, `!` by default |
| Filename sanitization | Prevents path traversal in uploads |
| Workspace isolation | `clear all; clear global; clear functions;` between sessions |
| SSE proxy auth | Requires reverse proxy with auth for production |
| Upload size limits | Configurable max upload size (default 100MB) |

## License

[MIT](LICENSE)

## Contributing

Contributions welcome! Please open an issue or PR on [GitHub](https://github.com/HanSur94/matlab-mcp-server-python).
