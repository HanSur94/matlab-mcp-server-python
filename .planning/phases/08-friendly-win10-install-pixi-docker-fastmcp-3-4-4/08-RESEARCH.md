# Phase 8 — Research (technical artifacts)

**Compiled:** 2026-07-12 · Source: two web-verified multi-agent research passes (15 external claims verified, 2 corrected). Companion to `08-CONTEXT.md` (design/decisions).

## 1. MATLAB engine via PyPI `matlabengine`

**Critical constraint (verified):** `matlabengine` is **sdist-only** (no wheels). `pip install matlabengine==X.Y.*` builds the sdist, and MathWorks' build step reads the Windows registry and **raises if a matching MATLAB isn't installed**. → It must **never** be a static dependency (`[project.dependencies]` / `[pypi-dependencies]`) — that breaks `pixi install` / `pip install` / CI on any machine without that exact MATLAB. Install it from a **task/script** that runs where MATLAB lives.

**Release → matlabengine version map (verified):**
| MATLAB | matlabengine | | MATLAB | matlabengine |
|---|---|---|---|---|
| R2022b | 9.13.* | | R2024b | 24.2.* |
| R2023a | 9.14.* | | R2025a | 25.1.* |
| R2023b | 9.15.* | | R2025b | 25.2.* |
| R2024a | 24.1.* | | R2026a | 26.1.* |

Leave the patch as `*` so patches flow. `matlabengine` `requires_python` is `>=3.9,<3.14`.

**`scripts/install_matlab_engine.py` logic (single source of truth, called by pixi task + install.bat):**
1. Resolve release: read registry `HKLM/HKCU\SOFTWARE\MathWorks\MATLAB` subkeys (`24.2`, `9.13`, …), non-admin readable; fallback glob `C:\Program Files\MATLAB\R20??`, `%LOCALAPPDATA%\Programs\MATLAB`. Newest wins. `MATLAB_RELEASE` env override. (On Linux/mac, glob `/usr/local/MATLAB/R20??`, `/Applications/MATLAB_R20??.app`.)
2. Map release → `matlabengine==<maj>.<min>.*`; `pip install` it into the active env.
3. Offline fallback (only if PyPI unreachable / `MATLAB_MCP_VENDOR` set): `pip install "<MATLABROOT>/extern/engines/python"` — the plain local-tree build (NO junctions/PowerShell). Clear pip error surfaced on release/pin mismatch.

**License note:** `matlabengine` LICENSE is BSD-3-Clause-**style** (modified clause 3: "solely for use with MathWorks products" — restricts use, not redistribution). Vendoring the `.tar.gz` sdist is permitted; `update_vendor.bat` must fetch it via `pip download matlabengine==<ver> --no-deps --no-binary :all:` (current `--only-binary` skips sdists).

## 2. Pixi (recommended Win10 desktop path)

Pixi installs a single binary to `%UserProfile%\.pixi`, edits **user** PATH only → **no admin**. Users get it via `powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"` or `winget install prefix-dev.pixi`. `pixi.lock` is committed for reproducibility.

**Draft `pixi.toml` (repo root):**
```toml
[workspace]
name = "matlab-mcp-python"
channels = ["conda-forge"]
platforms = ["win-64", "linux-64", "osx-64", "osx-arm64"]

[dependencies]
python = ">=3.10,<3.13"

[pypi-dependencies]
matlab-mcp-python = { path = ".", editable = true, extras = ["monitoring"] }  # reads pyproject
fastmcp = "==3.4.4"                                                            # newest 3.x
# matlabengine is NOT here — installed by the install-engine task (sdist builds off-host)

[tasks]
start          = "matlab-mcp"                            # stdio (default MCP)
inspect        = "matlab-mcp --inspect"
http           = "matlab-mcp --transport streamablehttp" # preferred HTTP transport
sse            = "matlab-mcp --transport sse"             # legacy alias, kept
dashboard      = { cmd = "python -c \"import webbrowser;webbrowser.open('http://127.0.0.1:8766/dashboard')\"" }
generate-token = "matlab-mcp --generate-token"
install-engine = "python scripts/install_matlab_engine.py"
install-engine-offline = { cmd = "python scripts/install_matlab_engine.py", env = { MATLAB_MCP_VENDOR = "vendor" } }

[feature.dev.pypi-dependencies]
pytest = ">=7.0"
pytest-asyncio = ">=0.21"
pytest-cov = ">=4.0"
ruff = ">=0.1.0"
build = ">=1.0.0"
pip-audit = ">=2.6.0"
[feature.dev.tasks]
test = "pytest tests/ -q"
lint = "ruff check src tests"
audit = "pip-audit"

[environments]
default = { solve-group = "default" }
dev     = { features = ["dev"], solve-group = "default" }
```

**Win10 flow:** install pixi → reopen terminal → `git clone && cd` → `pixi run start` (engine-free) → `pixi run install-engine` → `pixi run start` (live MATLAB).

## 3. Docker (Linux/server, real MATLAB) — verified honest story

A licensed engine cannot run in `python:slim`, and a Windows/mac MATLAB cannot be bind-mounted into Linux. Host↔container `shareEngine`/`connect_matlab`/`find_matlab` is local-only and unsupported across the Docker Desktop boundary (`find_matlab` from outside returns `()`). Real Docker = **`FROM mathworks/matlab` + network license manager** for non-interactive `start_matlab()`. (Individual/home license cannot start MATLAB non-interactively in a container → those users use Pixi.)

**Draft `Dockerfile`:**
```dockerfile
ARG MATLAB_RELEASE=r2025a
FROM mathworks/matlab:${MATLAB_RELEASE}
USER root
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir "matlabengine==25.1.*"   # MUST match image release (r2025a->25.1.*, r2024b->24.2.*)
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY examples/ ./examples/
RUN pip3 install --no-cache-dir ".[monitoring]"          # single source of truth -> fastmcp 3.4.x, no plotly
USER matlab
EXPOSE 8765 8766
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://localhost:8766/health')" || exit 1
ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "streamablehttp"]
```

**Draft `docker-compose.yml`:**
```yaml
services:
  matlab-mcp:
    build: { context: ., args: { MATLAB_RELEASE: r2025a } }
    ports: ["8765:8765", "8766:8766"]
    shm_size: "512m"                                                        # MATLAB needs shared memory
    environment:
      - MLM_LICENSE_FILE=${MLM_LICENSE_FILE:?set MLM_LICENSE_FILE=port@host} # REQUIRED network license
      - MATLAB_MCP_SERVER_TRANSPORT=streamablehttp
      - MATLAB_MCP_POOL_MAX_ENGINES=2                                        # each engine = 1 license seat
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./custom_tools.yaml:/app/custom_tools.yaml:ro
      - results:/app/results
      - monitoring_data:/app/monitoring
volumes: { results: {}, monitoring_data: {} }
```
`docker-compose.test.yml` (CI remote-integration) must also drop the stale `python:slim` assumptions; image build gated behind a MATLAB-license-available CI flag (generic CI cannot run `mathworks/matlab`).

## 4. FastMCP 3.4.4 adoption

Bump `fastmcp>=3.4.4,<4.0.0` in pyproject; pixi hard-pin `==3.4.4`; Dockerfile via pyproject; CLAUDE.md text. Rebuild `vendor/`/lock/**project wheel to v1.5.0** on the 3.x closure (kills offline-runs-2.14.5/v1.4.1 drift). Transport canonical id in 3.x is `http`; `streamablehttp`/`sse` remain accepted aliases — no upgrade breakage; server already emits SSE-deprecation warning.

**F5 — TimingMiddleware** (`src/matlab_mcp/middleware/timing.py`; register in `server.py:393` create_server):
```python
import time
from fastmcp.server.middleware import Middleware, MiddlewareContext

class TimingMiddleware(Middleware):
    def __init__(self, collector):            # existing MetricsCollector
        self._collector = collector
    async def on_call_tool(self, ctx: MiddlewareContext, call_next):
        t0 = time.perf_counter()
        try:
            result = await call_next(ctx)
            self._collector.record_event("completed", ctx.message.name, duration=time.perf_counter() - t0)
            return result
        except Exception:
            self._collector.record_event("failed", ctx.message.name, duration=time.perf_counter() - t0)
            raise
# server.py: mcp.add_middleware(TimingMiddleware(state.metrics))  — migrate executor timing incrementally
```

**F6 — Structured output** (`tools/core.py` + wrappers `server.py:414/439`): define `ExecuteResult`/`CheckResult` Pydantic models (status, stdout, variables, figures, job_id, error); annotate `execute_code`/`check_code` returns → FastMCP emits output schema + structuredContent. Use `ToolResult(content=summary, structured_content=res, is_error=True)` for MATLAB errors instead of `status='error'` dict. **Preserve existing dict keys** (schema-additive) to not break current clients.

**F12 — Default HTTP transport → streamable-http** in docs/compose/Dockerfile ENTRYPOINT; keep `sse` selectable (hard constraint: must not break existing SSE clients). `@mcp.custom_route` dashboard mount (`monitoring/dashboard.py:186`) unchanged in 3.x.

**Defer:** F7 progress (executor `_wait_for_completion` is a single blocking `asyncio.wait_for` on an opaque MATLAB future in a detached task with no reachable ctx/progressToken — not low-effort), F8 auth providers, F9 resources/prompts, F10 elicitation cleanup, F11 tag-gating. **Skip:** composition/proxy, OpenAPI, `task=True`/Docket (duplicates JobTracker, wants Redis).

## 5. Cleanup facts

- `plotly` runtime dep is imported nowhere (`plotly_*` modules emit hand-built JSON; dashboard uses bundled `plotly.min.js`) → removable. −9.9MB vendor.
- `cryptography` ships duplicated in vendor (cp38-abi3 + cp311-abi3); keep cp38-abi3 (covers 3.10+), drop cp311-abi3, add dedup to `update_vendor.bat`. −3.3MB. (cryptography itself stays — pulled by mcp SDK's pyjwt[crypto].)
- Version-string drift to reconcile: install.bat banner (`v1.3.0`), wiki/Installation.md (`MATLAB 2020b+` → R2022b+), CLAUDE.md (`FastMCP 2.14.5` → 3.4.4), Dockerfile pin.
- `update_vendor.bat` currently omits the project wheel (lock doesn't list it) → add `pip wheel . -w vendor`; add matlabengine sdist fetch; add wheel dedup.
- Deprecate `environment.yml` / `environment-dev.yml` / `requirements-lock.txt` in favor of `pixi.lock` (one release, then remove); re-home the `conda-test-pypi` CI job (only published-wheel smoke test) onto pip. Add CI: version-drift grep guard + clean-venv offline smoke test (`pip install --no-index --find-links vendor`).
