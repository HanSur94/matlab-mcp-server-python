# Connecting AI Agents to MATLAB MCP Server

This guide shows developers how to connect Claude Code, Codex CLI, or Cursor to a running MATLAB MCP server. Each section is self-contained — skip directly to your agent.

## Overview

The MATLAB MCP server speaks the Model Context Protocol. Any MCP-compatible agent can connect and use tools like `execute_code`, `get_workspace`, and `list_toolboxes` to interact with MATLAB.

Two transport modes are available:

| Transport | When to use | Auth required |
|-----------|-------------|---------------|
| **stdio** | Single agent, local, direct process spawn | No |
| **streamable HTTP** | Multi-agent, remote-capable, team shared | Yes — bearer token |

**Default endpoint (HTTP):** `http://127.0.0.1:8765/mcp`

> **Note:** SSE transport is deprecated. If you previously used SSE, switch to streamable HTTP (`--transport streamablehttp`). See the [Troubleshooting](#troubleshooting) section for migration help.

---

## Prerequisites

Before configuring your agent:

- [ ] MATLAB MCP server installed: `pip install matlab-mcp-python`
- [ ] MATLAB R2022b+ installed with Python Engine API configured
  - See [Windows deployment guide](windows-deployment.md) for no-admin Windows setup
- [ ] (HTTP transport only) Server running with `--transport streamablehttp`
- [ ] (HTTP transport only) `MATLAB_MCP_AUTH_TOKEN` environment variable set on the server

**Quick server start (HTTP mode):**

```bash
# Generate a token (run once, save the output)
matlab-mcp --generate-token

# Set the token and start the server
export MATLAB_MCP_AUTH_TOKEN=<your-token>      # Linux/macOS
# set MATLAB_MCP_AUTH_TOKEN=<your-token>       # Windows cmd
# $env:MATLAB_MCP_AUTH_TOKEN="<your-token>"   # Windows PowerShell

matlab-mcp --transport streamablehttp --config path/to/config.yaml
```

The server will log: `HTTP endpoint: http://127.0.0.1:8765/mcp`

---

## Claude Code

### Option A — stdio (recommended for local single-user)

In stdio mode, Claude Code spawns the MATLAB MCP server process directly. No server needs to be running beforehand, and no auth token is required.

**For Claude Code CLI (`.mcp.json` in your project root):**

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp",
      "args": ["--config", "path/to/config.yaml"]
    }
  }
}
```

**For Claude Desktop (`~/.claude/claude_desktop_config.json`):**

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp",
      "args": ["--config", "path/to/config.yaml"]
    }
  }
}
```

Omit `--config` to use all defaults (MATLAB auto-detected, stdio transport, 2–10 engine pool).

### Option B — streamable HTTP

Use this when the MATLAB server is already running (e.g., shared team server, Docker deployment, or multi-agent scenario).

**For Claude Code CLI (`.mcp.json`):**

```json
{
  "mcpServers": {
    "matlab": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${MATLAB_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

**For Claude Desktop (`~/.claude/claude_desktop_config.json`):**

```json
{
  "mcpServers": {
    "matlab": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${MATLAB_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

Set `MATLAB_MCP_AUTH_TOKEN` in your shell before launching Claude Code. The value must match the token set on the server.

---

## Codex CLI (OpenAI)

Codex CLI reads its MCP configuration from `~/.codex/config.json` or a project-level config file.

> **Important:** Codex CLI requires streamable HTTP transport. SSE transport is incompatible with Codex CLI's connection model — this is what caused the original Codex CLI connectivity failures. Always use `streamablehttp` when connecting Codex CLI.

### Option A — stdio

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp",
      "args": ["--config", "path/to/config.yaml"]
    }
  }
}
```

### Option B — streamable HTTP (recommended for Codex CLI)

```json
{
  "mcpServers": {
    "matlab": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${MATLAB_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

Ensure `MATLAB_MCP_AUTH_TOKEN` is exported in the same shell session where you run `codex`. The server must be started separately with `--transport streamablehttp` before invoking Codex CLI.

---

## Cursor

Cursor supports MCP servers via **Settings > MCP** or a `.cursor/mcp.json` config file.

### Option A — stdio (via Settings UI)

1. Open Cursor Settings
2. Navigate to **Features > MCP Servers** (or search "MCP")
3. Click **Add Server**
4. Fill in:
   - **Name:** `matlab`
   - **Command:** `matlab-mcp`
   - **Arguments:** `--config path/to/config.yaml`
5. Save and reload the window

### Option B — streamable HTTP (via `.cursor/mcp.json`)

Create or edit `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "matlab": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${MATLAB_MCP_AUTH_TOKEN}"
      }
    }
  }
}
```

Set `MATLAB_MCP_AUTH_TOKEN` as a system or shell environment variable. Cursor must be launched from the same environment where the variable is set (or added to your shell profile so it persists across sessions).

---

## Other MCP-Compatible Agents

For any MCP client not listed above, use the following connection details:

### stdio transport

Spawn `matlab-mcp` as a subprocess. The executable reads from stdin and writes to stdout using the MCP JSON-RPC framing.

```
command: matlab-mcp
args:    [--config, path/to/config.yaml]   # optional
stdin/stdout: MCP protocol stream
```

No authentication is required for stdio — the spawning process controls access.

### Streamable HTTP transport

Connect to:

```
URL:     http://<host>:<port>/mcp
Method:  POST (for requests), GET (for SSE streams)
Header:  Authorization: Bearer <token>
```

Default: `http://127.0.0.1:8765/mcp`

The server implements **MCP protocol version 1.26.0** via FastMCP. All standard MCP tool invocation, resource listing, and prompt handling are supported.

---

## Verifying the Connection

After configuring your agent, verify the connection with these test prompts:

1. **List available MATLAB toolboxes:**
   > "List the available MATLAB toolboxes"

   This calls the `list_toolboxes` tool. Expected: a list of installed toolboxes with names and versions.

2. **Run a simple MATLAB expression:**
   > "Run `disp('Hello from MATLAB')` in MATLAB"

   This calls the `execute_code` tool. Expected: the agent returns `Hello from MATLAB` as the output.

3. **Check workspace state:**
   > "Show the current MATLAB workspace variables"

   This calls the `get_workspace` tool. Expected: an empty workspace (or your variables if you've run code).

If all three work, the connection is healthy.

---

## Troubleshooting

### "Connection refused" or "Failed to connect"

The server is not running or is listening on a different port.

- Verify the server is running: check for a `matlab-mcp` process
- Confirm transport: `--transport streamablehttp` must be set (not `stdio`)
- Check the port: default is `8765`. If changed in `config.yaml`, update your agent config URL
- On Windows with non-loopback host (`0.0.0.0`): a firewall rule may be needed (requires admin)

### "401 Unauthorized"

Token mismatch between agent and server.

1. Regenerate the token: `matlab-mcp --generate-token`
2. Set the token on the server: `export MATLAB_MCP_AUTH_TOKEN=<new-token>`
3. Update the agent config to use the new token value
4. Restart both the server and your agent

### "Agent doesn't see MATLAB tools" / MCP handshake failed

The agent connected but the tool list is empty.

- Try `--inspect` mode to start the server without MATLAB for debugging: `matlab-mcp --inspect --transport streamablehttp`
- Check server logs for errors (default: `./logs/server.log`)
- Verify the MCP endpoint URL is `/mcp` (not `/sse` or `/`)

### "SSE transport errors with Codex CLI"

Codex CLI does not support SSE transport. Switch the server to streamable HTTP:

```bash
matlab-mcp --transport streamablehttp
```

Update your Codex CLI config to use `"type": "streamable-http"` with URL `http://127.0.0.1:8765/mcp`.

### MATLAB startup is slow (first tool call takes 30+ seconds)

Normal behavior — MATLAB Engine startup takes 20–60 seconds. Subsequent calls are fast. The pool pre-warms engines in the background; configure `pool.min_engines` in `config.yaml` to reduce wait time.

### Windows: "Access denied" or Firewall prompt

The server defaults to `127.0.0.1` (loopback only) to avoid Windows Firewall UAC prompts. If you need to bind to `0.0.0.0` for remote access, you must create an inbound firewall rule with admin rights or use an SSH tunnel.

---

## Configuration Reference

Key settings in `config.yaml` relevant to agent connectivity:

```yaml
server:
  transport: streamablehttp   # stdio | sse (deprecated) | streamablehttp
  host: 127.0.0.1             # bind address; 0.0.0.0 for remote access (Windows: needs firewall rule)
  port: 8765                  # MCP endpoint port

pool:
  min_engines: 2              # engines kept warm at startup
  max_engines: 10             # maximum concurrent MATLAB engines
```

For full configuration options, see `config.yaml` in the project root.

---

## Security Notes

- The bearer token is a 64-character hex string generated by `matlab-mcp --generate-token`
- Store it in your environment, not in config files (the server warns if it detects a token in `config.yaml`)
- If `MATLAB_MCP_AUTH_TOKEN` is not set on the server, HTTP connections are accepted without authentication — not recommended for shared or network-accessible servers
- For multi-user deployments, consider running the server behind a reverse proxy (nginx, Caddy) that handles TLS termination
