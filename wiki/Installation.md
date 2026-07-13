# Installation

## Prerequisites

- **Python 3.10+**
- **MATLAB R2022b+** installed locally
- **MATLAB Engine API for Python** — comes with MATLAB, needs separate install

## Recommended: Install with Pixi (no admin needed)

[Pixi](https://pixi.sh) installs Python + all dependencies into an isolated, per-project
environment — no venv wrangling, no admin rights, works the same on Windows/macOS/Linux. This
is the recommended path, especially on Windows 10 without admin rights.

```powershell
# Install pixi (Windows PowerShell)
irm -useb https://pixi.sh/install.ps1 | iex
# ...or via winget:
winget install prefix-dev.pixi
```

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python

# 1. Engine-free start — verifies the server comes up (no MATLAB required yet)
pixi run start

# 2. Detect your local MATLAB install and pip-install the matching matlabengine
pixi run install-engine

# 3. Start again — MATLAB code now actually executes
pixi run start
```

`pixi.lock` is committed, so `pixi run ...` always reproduces the exact resolved environment
(Python 3.10-3.12, `fastmcp==3.4.4`) on any machine — no separate `pip install` step needed.
`matlabengine` is deliberately never a static dependency (its sdist build reads the local
MATLAB installation and fails on machines without a matching release); the `install-engine`
task installs it on demand, matched to your detected MATLAB release.

The sections below cover manual/alternative install paths (`pip`, `install.bat`, Docker,
conda). Skip to [Step 3: Run](#step-3-run) once the pixi quickstart above works.

## Step 1: Install MATLAB Engine API (manual path)

The MATLAB Engine API lets Python call MATLAB. If you used the pixi quickstart above via
`pixi run install-engine`, this step is already done. To install manually instead:

### macOS

```bash
cd /Applications/MATLAB_R2024a.app/extern/engines/python
pip install .
```

> Adjust the path for your MATLAB version (e.g., `R2023b`, `R2024b`).

### Windows

```bash
cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"
pip install .
```

### Verify Installation

```python
import matlab.engine
eng = matlab.engine.start_matlab()
result = eng.eval("2 + 2", nargout=1)
print(result)  # Should print 4
eng.quit()
```

## Step 2: Install the MCP Server (manual path)

If you used the pixi quickstart above, this step is already done. Manual alternatives:

### Option A: Install from PyPI

```bash
pip install matlab-mcp-python
```

### Option B: Install from source

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
pip install -e ".[dev]"
```

**Note:** The `[dev]` extras include all optional dependencies (testing, monitoring). For a minimal install without dev/monitoring dependencies, use `pip install -e .` instead. To add only monitoring support (dashboard, health endpoint), use `pip install -e ".[monitoring]"`.

### Option C: `install.bat` (Windows, one-click, no admin needed)

```cmd
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
install.bat
```

The installer auto-detects MATLAB, creates a virtual environment, and installs everything from
bundled wheels — fully offline, no internet required. Works on Windows 10/11 with Python 3.10,
3.11, or 3.12.

### Option D: conda (deprecated)

`environment.yml` / `environment-dev.yml` are deprecated in favor of pixi and kept for one
release. Prefer the pixi quickstart above for new installs.

## Step 3: Run

```bash
# Single user (stdio transport)
matlab-mcp

# Multi-user (SSE transport)
matlab-mcp --transport sse

# With custom config
matlab-mcp --config my_config.yaml
```

## Step 4: Connect to Your AI Agent

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp"
    }
  }
}
```

### Claude Code

```bash
claude mcp add matlab -- matlab-mcp
```

### Cursor

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

### SSE Transport (Multi-User)

Start the server:

```bash
matlab-mcp --transport sse
```

Then point your client to `http://localhost:8765/sse`.

### Run with Docker

```bash
# Build the image
docker build -t matlab-mcp .

# Run with your MATLAB mounted
docker run -p 8765:8765 -p 8766:8766 \
  -v /path/to/MATLAB:/opt/matlab:ro \
  -e MATLAB_MCP_POOL_MATLAB_ROOT=/opt/matlab \
  matlab-mcp

# Or use docker-compose (edit docker-compose.yml to set your MATLAB path)
docker compose up
```

> **Note:** The Docker image does not include MATLAB. You must mount your own MATLAB installation and ensure the MATLAB Engine API for Python is accessible inside the container.

> **Upgrading?** If you previously installed as `matlab-mcp-server`, uninstall first: `pip uninstall matlab-mcp-server && pip install matlab-mcp-python`

## Virtual Environment (Recommended)

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Install MATLAB Engine API into the venv
cd /Applications/MATLAB_R2024a.app/extern/engines/python
pip install .

# Install server
cd /path/to/matlab-mcp-server-python
pip install -e ".[dev]"
```
