# Troubleshooting

Common install and runtime problems, with verified fixes. See also [Installation](Installation) and [Configuration](Configuration).

Quick reference for what version pairs with what:

- **Python** 3.10, 3.11, or 3.12
- **MATLAB** R2022b or newer, with the MATLAB Engine API for Python
- **FastMCP** 3.4.4
- **Transports**: `stdio` (default), `streamablehttp` (recommended HTTP), `sse` (legacy, deprecated)

---

## MATLAB not detected

**Symptom:** `install.bat` prints `[WARNING] No compatible MATLAB found`, or `scripts/install_matlab_engine.py` exits with `ERROR: No MATLAB installation detected`.

**How detection works:** the installer looks for MATLAB via the Windows registry (`SOFTWARE\MathWorks\MATLAB` under both `HKLM` and `HKCU`, both non-admin readable) and by globbing standard install locations:

- Windows: `C:\Program Files\MATLAB\R20*`, `%LOCALAPPDATA%\Programs\MATLAB\R20*`
- Linux: `/usr/local/MATLAB/R20*`
- macOS: `/Applications/MATLAB_R20*.app`

The newest detected release wins.

**Solutions:**

1. **Force the release** with the `MATLAB_RELEASE` environment variable (must be a supported release token — see the table below):
   ```bash
   MATLAB_RELEASE=R2024b python scripts/install_matlab_engine.py
   ```
2. **Point at a specific install** when running `install.bat` — when no compatible MATLAB is auto-detected, the installer prompts for a path (e.g. `C:\Program Files\MATLAB\R2024a`).
3. **Verify the Engine API tree exists** at `<MATLABROOT>\extern\engines\python`. If it's missing, your MATLAB install does not include the Python Engine API — reinstall MATLAB with that component.

---

## `matlabengine` version mismatch

**Symptom:** `import matlab.engine` fails after install, or the engine build errors, or the installed `matlabengine` doesn't match your MATLAB release.

**Explanation:** The `matlabengine` PyPI package is version-locked to a specific MATLAB release. `scripts/install_matlab_engine.py` detects your local release and installs the matching pin. It is deliberately **not** a static project dependency (its build reads the local MATLAB install and raises if absent), so `pip install matlab-mcp-python` alone does **not** install it — you run the engine installer separately.

**Release → `matlabengine` pin** (the whitelist in `scripts/install_matlab_engine.py`):

| MATLAB release | `matlabengine` pip spec |
|---|---|
| R2022b | `matlabengine==9.13.*` |
| R2023a | `matlabengine==9.14.*` |
| R2023b | `matlabengine==9.15.*` |
| R2024a | `matlabengine==24.1.*` |
| R2024b | `matlabengine==24.2.*` |
| R2025a | `matlabengine==25.1.*` |
| R2025b | `matlabengine==25.2.*` |
| R2026a | `matlabengine==26.1.*` |

**Solutions:**

1. **Re-run the engine installer** so it picks the right pin for your release:
   ```bash
   pixi run install-engine          # Pixi
   python scripts/install_matlab_engine.py   # any environment
   ```
2. **Install the exact pin manually** if you know your release:
   ```bash
   pip install "matlabengine==24.2.*"   # example: R2024b
   ```
3. **A release token that isn't whitelisted is rejected** — `resolve_engine_spec` raises `ValueError: Unknown/unsupported MATLAB release token`. Only the releases in the table above are supported. If you're on a newer/older MATLAB, upgrade or downgrade MATLAB to a supported release, or use the offline/vendored path (below) which builds from the local tree and skips the whitelist.

---

## Python-version / MATLAB-release compatibility

**Symptom:** Engine install fails, or `install.bat` warns that a detected MATLAB `does NOT support Python 3.10+`.

**Explanation:** Each MATLAB release supports a specific band of Python versions. This project requires Python 3.10–3.12 and MATLAB R2022b+; you must pick a Python version that your MATLAB release supports.

| MATLAB release | Supported Python |
|---|---|
| R2022b | 3.8, 3.9, 3.10 |
| R2023a | 3.8, 3.9, 3.10 |
| R2023b | 3.9, 3.10, 3.11 |
| R2024a | 3.9, 3.10, 3.11 |
| R2024b | 3.10, 3.11, 3.12 |
| R2025a | 3.10, 3.11, 3.12 |

**Solutions:**

1. If your Python is too new for your MATLAB (e.g. Python 3.12 with R2023b), either upgrade MATLAB or create the environment with an older supported Python (3.10). Pixi pins Python to `>=3.10,<3.13`, so `pixi install` already gives you a compatible interpreter.
2. `install.bat` rejects a detected MATLAB older than R2022b and continues without the engine — install a supported MATLAB, then re-run `python scripts/install_matlab_engine.py` from the activated venv.

---

## `No module named pip` in Pixi

**Symptom:** `pixi run install-engine` (or any pip step) fails with `No module named pip`.

**Explanation:** A conda/Pixi environment does not always ship `pip` by default. The engine installer shells out to `python -m pip`, which needs `pip` present in the environment.

**Solution:** Ensure `pip` is in the Pixi environment, then re-run the engine task:
```bash
pixi add pip
pixi run install-engine
```

---

## Engine won't start / start timeout

**Symptom:** `Engine start timeout`, or MATLAB tools stay inert after `pixi run start`.

**Solutions:**

1. **Confirm the engine is importable:**
   ```bash
   python -c "import matlab.engine; print('OK')"
   ```
   If this fails, install the engine (`pixi run install-engine` or `python scripts/install_matlab_engine.py`). With Pixi, remember MATLAB tools are inert until you run `install-engine`.
2. **Point at MATLAB explicitly** if auto-detection fails, via `pool.matlab_root` in `config.yaml`:
   ```yaml
   pool:
     matlab_root: "/Applications/MATLAB_R2024a.app"
   ```
3. **Increase the start timeout** if MATLAB is slow to launch (default 120s):
   ```yaml
   pool:
     engine_start_timeout: 300
   ```
4. **Start without MATLAB** to isolate config vs. engine problems: `matlab-mcp --inspect` (or `pixi run inspect`) brings the server up with `min_engines=0` and no engine pool.

---

## "Max engines" warning on macOS

**Symptom:** A stability warning when `pool.max_engines > 4` on macOS.

**Explanation:** Running more than 4 `matlab.engine` instances in one process is unstable on macOS. The server **warns** but does not hard-cap — it still honors your configured `max_engines`.

**Solution:** Keep `pool.max_engines` at 4 or fewer on macOS:
```yaml
pool:
  max_engines: 4
```

---

## Port already in use

**Symptom:** The server fails to bind, or the dashboard is unreachable.

**Ports used:**

- **`8765`** — the MCP server port (`server.port`), used by the `sse` and `streamablehttp` transports.
- **`8766`** — the monitoring dashboard/health port (`monitoring.http_port`), started as a separate app **only under `stdio` transport**. Under `sse`/`streamablehttp` the monitoring routes (`/health`, `/metrics`, `/dashboard`, …) are mounted on the main MCP app (port 8765) instead.

**Solutions:**

1. **Change the MCP port:**
   ```yaml
   server:
     port: 8770
   ```
   or via env: `MATLAB_MCP_SERVER_PORT=8770`.
2. **Change the dashboard port:**
   ```yaml
   monitoring:
     http_port: 8771
   ```
   or via env: `MATLAB_MCP_MONITORING_HTTP_PORT=8771`.
3. **Find the conflicting process:** `lsof -i :8765` (macOS/Linux) or `netstat -ano | findstr 8765` (Windows).

---

## Transport / agent connection issues

**Symptom:** An MCP client can't connect, or an HTTP client gets `401 Unauthorized`.

**Pick the right transport and endpoint:**

- **`stdio`** (default) — for local single-client agents (Claude Code, Cursor). Registered by command, e.g. `claude mcp add matlab -- matlab-mcp`, or `{ "mcpServers": { "matlab": { "command": "matlab-mcp" } } }`.
- **`streamablehttp`** (recommended HTTP) — endpoint `http://<host>:<port>/mcp`. Start with `matlab-mcp --transport streamablehttp` (or `pixi run http`).
- **`sse`** (legacy, **deprecated**) — endpoint `http://<host>:<port>/sse`. Logs a deprecation warning at startup and will be removed in a future release. Prefer `streamablehttp`.

**Solutions:**

1. **Verify the server is running** and on the expected transport/port. For HTTP, `host: 0.0.0.0` allows remote access; `127.0.0.1` is local-only.
2. **Bearer auth (HTTP transports only):** if `MATLAB_MCP_AUTH_TOKEN` is set, every request needs an `Authorization: Bearer <token>` header (the `/health` path and CORS `OPTIONS` preflight are exempt). A missing/wrong token yields `401`. Generate a token with:
   ```bash
   matlab-mcp --generate-token     # or: pixi run generate-token
   ```
   If `MATLAB_MCP_AUTH_TOKEN` is **unset**, auth is disabled and all HTTP requests are accepted (the server logs a warning). Note the token lives only in the env var — never put it in `config.yaml`.
3. **CORS:** allowed origins come from `server.cors_origins` (default `["*"]`); allowed methods are `GET, POST, OPTIONS`; allowed headers are `Authorization, Content-Type, Accept`.
4. **Firewall:** ensure the MCP port (default 8765) is open for remote clients.

---

## Offline / air-gapped install

**Symptom:** No internet access on the target machine (PyPI unreachable), or you want a fully local install.

**How it works:** The engine installer can build `matlabengine` from the local MATLAB tree at `<MATLABROOT>/extern/engines/python` instead of PyPI. This is forced by setting `MATLAB_MCP_VENDOR`, and it also happens automatically if the online pip install fails. It requires `MATLABROOT` to be set/available.

**Solutions:**

1. **Pixi offline engine task:**
   ```bash
   pixi run install-engine-offline
   ```
   (runs the installer with `MATLAB_MCP_VENDOR` set).
2. **Manual offline engine install:**
   ```bash
   MATLABROOT=/path/to/MATLAB/R2024b MATLAB_MCP_VENDOR=1 \
     python scripts/install_matlab_engine.py
   ```
   Note: the offline path builds from the local tree and skips the release whitelist, so it can install for a release not yet in the table above.
3. **`install.bat` fully offline:** drop dependency wheels into a `vendor/` directory next to `install.bat`. When wheels are present, it installs pip/setuptools/wheel, the engine, and the MCP server with `--no-index --find-links vendor` — no internet needed. If the engine tree is available it sets `MATLAB_MCP_VENDOR` and builds from the local MATLAB tree.
4. **If `MATLAB_MCP_VENDOR` is set but no `MATLABROOT` is available**, the installer raises `RuntimeError` — set `MATLABROOT` to your MATLAB install root.

---

## Upgrading from the old package name

**Symptom:** Conflicts or stale files after upgrading from an older release.

**Explanation:** The distribution was renamed from `matlab-mcp-server` to `matlab-mcp-python`.

**Solution:** Uninstall the old package first:
```bash
pip uninstall matlab-mcp-server
pip install matlab-mcp-python
```

---

## Blocked function error

**Symptom:** `BlockedFunctionError: Function 'system' is blocked`.

**Explanation:** The security validator blocks dangerous MATLAB functions by default (`system`, `unix`, `dos`, `!`, `eval`, `feval`, `evalc`, `evalin`, `assignin`, `perl`, `python`, and more).

**Solutions:**

1. **Use MATLAB-native alternatives** instead of `system()` — e.g. `dir`, `mkdir`, `copyfile`, `movefile`, `getenv`.
2. **Remove specific functions** from the blocklist in `config.yaml`:
   ```yaml
   security:
     blocked_functions:
       - "unix"
       - "dos"
       # "system" removed from the list
   ```
3. **Disable the blocklist entirely** (not recommended on shared servers):
   ```yaml
   security:
     blocked_functions_enabled: false
   ```

---

## Job stuck in "running"

**Symptom:** A job never completes; progress stops updating.

**Solutions:**

1. **Cancel it** — ask your agent to call `cancel_job` with the job ID.
2. **Check the hard limit** (`execution.max_execution_time`, default 86400s / 24h). Jobs are also auto-promoted to async after `execution.sync_timeout` (default 30s).
3. **Inspect the MATLAB code** for infinite loops.

---

## Debug logging

Enable verbose logging to diagnose most issues:

```yaml
server:
  log_level: "debug"
  log_file: "./logs/server.log"
```

Or via environment variable:
```bash
export MATLAB_MCP_SERVER_LOG_LEVEL=debug
```

Then check the log file (default `./logs/server.log`) for detailed error output.
