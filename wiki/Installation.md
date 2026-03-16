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
