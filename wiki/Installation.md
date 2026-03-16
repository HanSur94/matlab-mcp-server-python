# Installation

## Prerequisites

- **Python 3.9+**
- **MATLAB 2020b+** installed locally
- **MATLAB Engine API for Python** — comes with MATLAB, needs separate install

## Step 1: Install MATLAB Engine API

The MATLAB Engine API lets Python call MATLAB. Install it from your MATLAB installation:

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

## Step 2: Install the MCP Server

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
