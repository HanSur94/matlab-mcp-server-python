# Installation

This is the page to start from. It covers prerequisites, the four install
methods (in recommended order), the separate MATLAB-engine step, and per-agent
MCP config snippets.

See also: [Configuration](Configuration) · [MCP Tools Reference](MCP-Tools-Reference)

## Prerequisites

- **Python 3.10, 3.11, or 3.12** (`requires-python >=3.10`; Pixi pins `<3.13`).
- **MATLAB R2022b or newer** installed locally, including the **MATLAB Engine
  API for Python**. This is an external user dependency — MATLAB is never
  bundled.
- The engine is installed from PyPI (`matlabengine`), matched to your detected
  MATLAB release, by `scripts/install_matlab_engine.py`. It is **not** a static
  project dependency (its sdist build reads the local MATLAB install and fails
  where none is present), so it is always installed as a separate step.

> **Package name:** the PyPI distribution is `matlab-mcp-python`; the import
> package and console command are `matlab_mcp` / `matlab-mcp`. If you previously
> installed the old `matlab-mcp-server`, run
> `pip uninstall matlab-mcp-server` first.

---

## Method 1 — Pixi (no admin, recommended)

[Pixi](https://pixi.sh) installs Python and all dependencies into an isolated
per-project environment — no venv wrangling, no admin rights, identical on
Windows/macOS/Linux. `pixi.lock` is committed, so the environment (Python
3.10–3.12, `fastmcp==3.4.4`) reproduces exactly on any machine.

**1. Install pixi** (one-time, no admin — it installs to your user profile and edits only your user `PATH`):

```powershell
# Windows — winget (ships with Windows 10/11) …
winget install prefix-dev.pixi
# … or the PowerShell one-liner:
powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

```bash
# macOS / Linux
curl -fsSL https://pixi.sh/install.sh | bash
```

Reopen your terminal afterwards so `pixi` is on `PATH`.

**2. Clone and run:**

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python

pixi run start            # engine-free start — server comes up; MATLAB tools inert until the engine is installed
pixi run install-engine   # detect the local MATLAB release, pip-install the matching matlabengine
pixi run start            # full start
```

`matlabengine` is installed on demand by the `install-engine` task, never by
`pixi install`.

### Pixi tasks

| Task | Runs | Notes |
|------|------|-------|
| `pixi run start` | `matlab-mcp` | stdio transport |
| `pixi run inspect` | `matlab-mcp --inspect` | start without MATLAB (no engine pool) |
| `pixi run http` | `matlab-mcp --transport streamablehttp` | preferred HTTP transport |
| `pixi run sse` | `matlab-mcp --transport sse` | legacy alias, back-compat only |
| `pixi run dashboard` | opens `http://localhost:8766/dashboard` | monitoring UI |
| `pixi run generate-token` | `matlab-mcp --generate-token` | bearer token for HTTP auth |
| `pixi run install-engine` | `python scripts/install_matlab_engine.py` | detect + install `matlabengine` |
| `pixi run install-engine-offline` | same script with `MATLAB_MCP_VENDOR=vendor` | forces local-tree install |
| `pixi run test` | `pytest tests/ -v` | `dev` environment |
| `pixi run lint` | `ruff check src/ tests/` | `dev` environment |
| `pixi run audit` | `pip-audit` | `dev` environment |

---

## Method 2 — One-click Windows `install.bat` (no admin)

```bat
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
install.bat
```

`install.bat` requires no admin rights. It checks that Python is on `PATH`
(3.10+), creates a user-local virtual environment, upgrades pip/setuptools/wheel,
installs the MATLAB engine by delegating to
`python scripts\install_matlab_engine.py` (the same single source of truth as the
Pixi task), then installs the package. If a bundled `vendor\` directory of wheels
is present, everything installs fully offline via `--no-index --find-links`
(and the engine install falls back to the local MATLAB tree via
`MATLAB_MCP_VENDOR`). When the script directory is not writable, it falls back to
`%LOCALAPPDATA%\matlab-mcp`.

After it finishes, start the server with the generated `start-matlab-mcp.bat`
helper or by activating the venv and running `matlab-mcp`.

---

## Method 3 — pip (from PyPI)

```bash
pip install matlab-mcp-python
```

With the monitoring extra (adds `psutil` + `uvicorn` for the dashboard/health
endpoints):

```bash
pip install matlab-mcp-python[monitoring]
```

From source (editable, with dev tooling):

```bash
git clone https://github.com/HanSur94/matlab-mcp-server-python.git
cd matlab-mcp-server-python
pip install -e ".[dev]"
```

> **pip does not install `matlabengine`.** Install it separately — either
> `python scripts/install_matlab_engine.py`, or
> `pip install "matlabengine==<major>.<minor>.*"` for your release (see the
> [release map](#matlab-release--matlabengine-version-map) below).

**Extras** (`pyproject.toml`): `monitoring` = `psutil`, `uvicorn`;
`dev` = pytest, pytest-asyncio, pytest-cov, ruff, psutil, uvicorn, pip-audit,
build.

---

## Method 4 — Docker (NETWORK license only)

```bash
docker build -t matlab-mcp .

docker run -p 8765:8765 \
  -e MLM_LICENSE_FILE=port@host \
  matlab-mcp

# or with docker compose:
docker compose up
```

- Base image `FROM mathworks/matlab:${MATLAB_RELEASE}` (default build arg
  `MATLAB_RELEASE=r2025a`); the matching `matlabengine` is installed from the
  release map inside the image.
- Container default command is `matlab-mcp --transport streamablehttp`;
  `EXPOSE 8765`. `docker-compose.yml` sets
  `MATLAB_MCP_SERVER_TRANSPORT=streamablehttp` and
  `MATLAB_MCP_POOL_MAX_ENGINES=2` (each engine = one license seat).
- **Requires a NETWORK license** via `MLM_LICENSE_FILE=port@host`. Compose
  fail-fast-guards on it and refuses to start if unset.
- **Not suitable** for home / individual-license Windows 10 laptops — use Pixi
  or `install.bat` there instead.
- The Docker `HEALTHCHECK` hits `http://localhost:8765/health` (the main MCP
  app port, not 8766).

---

## MATLAB release → `matlabengine` version map

`scripts/install_matlab_engine.py` detects the newest installed MATLAB release
(Windows registry under `SOFTWARE\MathWorks\MATLAB` in HKLM/HKCU, plus
filesystem globs of the standard install locations) and installs the matching
whitelisted PyPI pin. Set `MATLAB_RELEASE` to override detection (still
whitelist-checked). Set `MATLAB_MCP_VENDOR` to force an offline install from
`<MATLABROOT>/extern/engines/python` (also triggered automatically if the online
pip install fails).

| MATLAB release | `matlabengine` pip spec |
|----------------|--------------------------|
| R2022b | `matlabengine==9.13.*` |
| R2023a | `matlabengine==9.14.*` |
| R2023b | `matlabengine==9.15.*` |
| R2024a | `matlabengine==24.1.*` |
| R2024b | `matlabengine==24.2.*` |
| R2025a | `matlabengine==25.1.*` |
| R2025b | `matlabengine==25.2.*` |
| R2026a | `matlabengine==26.1.*` |

### Verify the engine

```python
import matlab.engine
eng = matlab.engine.start_matlab()
print(eng.eval("2 + 2", nargout=1))  # 4.0
eng.quit()
```

---

## Run

```bash
matlab-mcp                              # stdio (default, single local client)
matlab-mcp --transport streamablehttp   # preferred HTTP transport
matlab-mcp --transport sse              # legacy SSE (deprecated, back-compat)
matlab-mcp --config my_config.yaml      # custom config
matlab-mcp --inspect                    # start without MATLAB (no engine pool)
matlab-mcp --generate-token             # print a bearer token + env snippet, then exit
```

- **stdio** — local single-client agents. **streamablehttp** — recommended HTTP
  transport, endpoint `http://<host>:<port>/mcp`. **sse** — deprecated, endpoint
  `http://<host>:<port>/sse`, logs a deprecation warning.
- Ports: MCP server `8765` (`server.port`); monitoring dashboard/health `8766`
  (`monitoring.http_port`) under stdio only — under HTTP transports the
  monitoring routes (`/health`, `/metrics`, `/dashboard`, …) mount on the main
  app at `8765`.
- **HTTP auth (bearer token):** set `MATLAB_MCP_AUTH_TOKEN` (env var only, never
  in `config.yaml`). If unset, HTTP auth is disabled and all requests are
  accepted (the server warns at startup). `/health` and CORS pre-flight requests
  bypass auth. Generate a token with `matlab-mcp --generate-token`.

---

## Connect your AI agent

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp"
    }
  }
}
```

On Windows via `install.bat`, point `command` at the venv executable, e.g.
`%LOCALAPPDATA%\matlab-mcp\.venv\Scripts\matlab-mcp.exe`.

### Claude Code

```bash
claude mcp add matlab -- matlab-mcp
```

Or via `.mcp.json` in your project root:

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

### Codex CLI

Codex CLI reads MCP config from `~/.codex/config.json` (or a project-level
config). Codex CLI **requires streamable HTTP** — SSE is incompatible with its
connection model. Start the server separately with `--transport streamablehttp`,
export `MATLAB_MCP_AUTH_TOKEN` in the same shell, then configure:

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

Any agent can also use HTTP: start with `matlab-mcp --transport streamablehttp`
and point the client at `http://127.0.0.1:8765/mcp` with a bearer token. See
[Configuration](Configuration) for details.

---

## Upgrading

If you previously installed the old distribution name, uninstall it first:

```bash
pip uninstall matlab-mcp-server
pip install matlab-mcp-python
```
