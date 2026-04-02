# Windows 10 Deployment Guide (No Admin Rights)

This guide walks through setting up the MATLAB MCP Server on a restricted Windows 10 machine — a corporate workstation, a university lab PC, or any environment where you do not have local administrator privileges. Every step here works without elevation.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Authentication](#authentication)
5. [Starting the Server](#starting-the-server)
6. [First MATLAB Tool Call](#first-matlab-tool-call)
7. [Troubleshooting](#troubleshooting)
8. [Human-in-the-Loop (HITL) Approval Gates](#hitl)

---

## Prerequisites

### 1. Python 3.10 or newer (user-space install, no admin required)

Download the Windows installer from <https://www.python.org/downloads/> and run it as your normal user account.

> **Important:** On the first installer screen, check **"Add Python to PATH"**. If you miss this, the `python` and `pip` commands will not be available in Command Prompt.

Supported Python versions: 3.10, 3.11, 3.12.

Verify your installation:

```cmd
python --version
```

Expected output: `Python 3.10.x` (or 3.11.x / 3.12.x).

---

### 2. MATLAB R2022b or newer with Python Engine API

The server requires MATLAB R2022b+ (earlier releases do not support Python 3.10+).

**MATLAB–Python compatibility matrix:**

| MATLAB version | Supported Python versions |
|----------------|--------------------------|
| R2022b         | 3.8, 3.9, **3.10**       |
| R2023a         | 3.8, 3.9, **3.10**       |
| R2023b         | 3.9, **3.10, 3.11**      |
| R2024a         | 3.9, **3.10, 3.11**      |
| R2024b         | **3.10, 3.11, 3.12**     |
| R2025a         | **3.10, 3.11, 3.12**     |

#### Installing the MATLAB Engine API

**Option A — pip install (recommended, no admin needed):**

```cmd
pip install matlabengine
```

This installs a pre-built wheel from PyPI and works even when MATLAB is installed under `C:\Program Files` (which is read-only for standard users).

**Option B — install from your MATLAB directory:**

If your MATLAB installation is accessible (i.e., not in a read-only location), you can build the engine from source. This example uses R2024b:

```cmd
cd "C:\Program Files\MATLAB\R2024b\extern\engines\python"
pip install .
```

> **Note:** If the MATLAB directory is under `C:\Program Files` and you get a permission error during the build, use Option A (`pip install matlabengine`) instead. The installer script `install.bat` included in the repository handles this automatically with a copy-to-TEMP workaround.

#### Verify both prerequisites

```cmd
python --version
python -c "import matlab.engine; print('MATLAB Engine API: OK')"
```

Both commands must succeed before continuing.

---

## Installation

### Option A: Install from PyPI (recommended)

```cmd
pip install matlab-mcp-python
```

### Option B: Install from source (for development or testing unreleased changes)

```cmd
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
pip install -e .
```

### Option C: One-click installer (offline-capable)

Run `install.bat` from the repository root. This script:
- Creates a Python virtual environment under your user profile
- Detects MATLAB and installs the Engine API (no admin required)
- Installs the MCP server from bundled wheels if `vendor/` is present, or from PyPI

```cmd
install.bat
```

### Verify the installation

```cmd
matlab-mcp --help
```

You should see usage information with flags like `--config`, `--transport`, `--inspect`, and `--generate-token`.

---

## Configuration

Create a `config.yaml` file in the directory where you will run the server. The minimal configuration for streamable HTTP transport (recommended for agent connections) is:

```yaml
server:
  transport: "streamablehttp"
  host: "127.0.0.1"
  port: 8765
```

### Why `host: "127.0.0.1"`?

`127.0.0.1` is the loopback address — it only accepts connections from the same machine. This is the **default** and is strongly recommended for restricted machines because:

- It does **not** trigger a Windows Defender Firewall popup.
- It does **not** require an admin to create an inbound firewall rule.
- AI agents running locally (Claude Code, Cursor, Copilot) connect to `127.0.0.1` without any firewall interaction.

> **Accepting remote connections:** To let agents on other machines connect, change `host` to `"0.0.0.0"`. This **requires an admin-created Windows Firewall inbound rule** for port 8765. On a restricted machine without admin rights, setting `host: "0.0.0.0"` will either be blocked by the OS or trigger a UAC elevation prompt that you cannot approve. Stick to `127.0.0.1` unless you have confirmed admin support.

### Environment variable overrides

Any config value can be overridden with an environment variable prefixed with `MATLAB_MCP_`. For example:

```cmd
set MATLAB_MCP_POOL_MAX_ENGINES=4
```

This is useful in CI pipelines or when you want to avoid editing `config.yaml`. The format is `MATLAB_MCP_<SECTION>_<KEY>` in UPPERCASE.

### Example: full minimal config for a restricted machine

```yaml
server:
  transport: "streamablehttp"
  host: "127.0.0.1"
  port: 8765
  log_level: "info"

pool:
  min_engines: 1
  max_engines: 4

execution:
  temp_dir: "%LOCALAPPDATA%\\matlab-mcp\\temp"

monitoring:
  enabled: true
  db_path: "%LOCALAPPDATA%\\matlab-mcp\\monitoring\\metrics.db"
```

Placing `temp_dir` and `db_path` under `%LOCALAPPDATA%` ensures they are always in a user-writable location.

---

## Authentication

For streamable HTTP transport, it is strongly recommended to enable bearer token authentication so that only your AI agent can send requests to the server.

### Step 1: Generate a token

```cmd
matlab-mcp --generate-token
```

Sample output:

```
Generated MATLAB MCP auth token (64 hex chars):

  a3f9e2...c8b1d4

Set the environment variable:

  # Windows (cmd):
  set MATLAB_MCP_AUTH_TOKEN=a3f9e2...c8b1d4

  # Windows (PowerShell):
  $env:MATLAB_MCP_AUTH_TOKEN="a3f9e2...c8b1d4"
```

### Step 2: Set the token in your shell session

**Command Prompt:**

```cmd
set MATLAB_MCP_AUTH_TOKEN=<your-token-here>
```

**PowerShell:**

```powershell
$env:MATLAB_MCP_AUTH_TOKEN="<your-token-here>"
```

> **Security note:** The token is read exclusively from the `MATLAB_MCP_AUTH_TOKEN` environment variable. Never put it in `config.yaml` — the server will refuse to start if it detects a token in the config file (to prevent accidental git commits of secrets).

The token must be set in the **same shell session** from which you start the server.

### Stdio transport (single-user, local agent)

If you are using the default `stdio` transport (for example, connecting Claude Desktop or Claude Code directly), authentication is **not required** — the agent communicates over stdin/stdout and there is no network exposure.

---

## Starting the Server

### Stdio transport (default — single agent, local machine)

```cmd
matlab-mcp
```

or equivalently:

```cmd
matlab-mcp --transport stdio
```

No config file is required. The server starts MATLAB engines, waits for MCP messages on stdin, and replies on stdout.

### Streamable HTTP transport (recommended for multi-agent or remote use)

```cmd
matlab-mcp --transport streamablehttp
```

or set `transport: "streamablehttp"` in `config.yaml` and just run:

```cmd
matlab-mcp
```

### With a custom config file

```cmd
matlab-mcp --config path\to\config.yaml
```

### Startup banner

When the server starts successfully, you will see log lines like:

```
2026-04-01 12:00:00 INFO matlab_mcp.server — ============================================================
2026-04-01 12:00:00 INFO matlab_mcp.server — MATLAB MCP Server starting
2026-04-01 12:00:00 INFO matlab_mcp.server — ============================================================
2026-04-01 12:00:00 INFO matlab_mcp.server —   Transport:       streamablehttp
2026-04-01 12:00:00 INFO matlab_mcp.server —   HTTP endpoint:   http://127.0.0.1:8765/mcp
2026-04-01 12:00:00 INFO matlab_mcp.server —   Log level:       info
2026-04-01 12:00:00 INFO matlab_mcp.server — --- Pool ---
2026-04-01 12:00:00 INFO matlab_mcp.server —   Min engines:     2
2026-04-01 12:00:00 INFO matlab_mcp.server —   Max engines:     10
...
2026-04-01 12:00:00 INFO matlab_mcp.server — ============================================================
```

The line `HTTP endpoint: http://127.0.0.1:8765/mcp` confirms the server is listening.

### Inspection mode (no MATLAB required)

To verify configuration and tool listing without a MATLAB installation:

```cmd
matlab-mcp --inspect
```

---

## First MATLAB Tool Call

Once the server is running in streamable HTTP mode, you can verify it responds correctly with a quick test.

### Using curl (Windows 10 ships with curl)

The MCP protocol uses JSON-RPC over HTTP. Send an `initialize` message to confirm connectivity:

```cmd
curl -s -X POST http://127.0.0.1:8765/mcp ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer <your-token-here>" ^
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}"
```

Expected response: a JSON object containing `"result": { "protocolVersion": "2024-11-05", ... }`.

### Connecting an AI agent

AI agents handle the MCP protocol automatically. Configure your agent to use the server endpoint:

**Claude Code (stdio — simplest for single user):**

```cmd
claude mcp add matlab -- matlab-mcp
```

**Claude Code (streamable HTTP):**

```cmd
claude mcp add matlab --transport http http://127.0.0.1:8765/mcp
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp"
    }
  }
}
```

Once connected, ask the agent to run MATLAB code. The server logs will show:

```
INFO matlab_mcp.jobs.executor — Job abc123 started
INFO matlab_mcp.jobs.executor — Job abc123 completed in 0.42s
```

---

## Troubleshooting

### "MATLAB engine not found" or `ModuleNotFoundError: No module named 'matlab'`

The MATLAB Engine API for Python is not installed or not visible to your Python environment.

**Fix:**
1. Activate your virtual environment: `call .venv\Scripts\activate.bat`
2. Run: `python -c "import matlab.engine"`
3. If this fails, reinstall: `pip install matlabengine`
4. Verify MATLAB is R2022b or newer and matches your Python version (see the compatibility table in Prerequisites).

---

### "Address already in use" / `OSError: [WinError 10048]`

Port 8765 is already in use by another process.

**Fix:** Change the port in `config.yaml`:

```yaml
server:
  port: 8766
```

Or set an override: `set MATLAB_MCP_SERVER_PORT=8766`

---

### Windows Firewall popup appears when starting the server

You set `host: "0.0.0.0"` (or left the default in an older config), and Windows is asking for permission to open a network port.

**Fix:** Switch back to loopback binding in `config.yaml`:

```yaml
server:
  host: "127.0.0.1"
```

Click **Cancel** on the firewall dialog — you do not need to approve it when using `127.0.0.1`.

---

### "Permission denied" on temp directory

The server cannot write to the configured `execution.temp_dir`.

**Fix:** Point `temp_dir` to a user-writable location:

```yaml
execution:
  temp_dir: "%LOCALAPPDATA%\\matlab-mcp\\temp"
```

The default `./temp` (relative to the working directory) is also user-writable as long as you launch the server from a directory you own (e.g., your home folder or Documents).

---

### "Token rejected" / HTTP 401 Unauthorized

The bearer token sent by the agent does not match the `MATLAB_MCP_AUTH_TOKEN` environment variable.

**Checklist:**
1. Confirm the env var is set in the shell where the **server** is running: `echo %MATLAB_MCP_AUTH_TOKEN%`
2. Confirm the same token is configured in your agent (Claude Code, Cursor, etc.).
3. The env var is session-scoped — if you open a new Command Prompt window, you must set it again (or add it to your user environment variables via System Properties).

---

### Server starts but MATLAB engines take a long time to become available

MATLAB startup takes 30–120 seconds depending on hardware and installed toolboxes. This is expected.

**Tip:** Reduce `pool.min_engines` to `1` to shorten initial startup on low-memory machines. The pool will scale up on demand.

```yaml
pool:
  min_engines: 1
  max_engines: 4
```

---

## HITL

### Human-in-the-Loop (HITL) Approval Gates

For additional safety in shared environments, the server supports approval gates that pause execution and require a human to confirm before MATLAB runs a designated protected function. This is entirely opt-in and disabled by default.

To enable HITL gates, add a `hitl:` section to `config.yaml`:

```yaml
hitl:
  enabled: true
  protected_functions:
    - "system"
    - "eval"
```

When an agent calls a gated function, the server will emit a prompt and wait for your `yes` or `no` before proceeding.

For full HITL configuration options (timeout, audit logging, bypass list), see the comments in `config.yaml`.

---

*For additional topics — custom toolboxes, monitoring dashboard, Docker deployment, and multi-agent session isolation — see the project [Wiki](https://github.com/HanSur94/matlab-mcp-server-python/wiki).*
