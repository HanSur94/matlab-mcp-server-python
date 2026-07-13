# Design: Friendly Win10 Install + FastMCP 3.4.4 — MATLAB MCP Server

**Date:** 2026-07-12 · **Status:** Approved (design), pending implementation via GSD · **Branch:** claude/win10-install-lean-3d6b8f

## Goal

Make the Win10 install **dead-simple and friendly**, runnable via **Pixi** (desktop) and **Docker** (server), on the **newest FastMCP (3.4.4)**, adopting the new-lib features that genuinely benefit this server.

## Non-goals

- Raw-MCP-SDK migration (fastmcp stays — user directive: "newest fastMCP must be in the project").
- Single-Python-ABI vendor narrowing / moving `vendor/` out of git (offline air-gapped support retained).
- report_progress / Docket background tasks / server composition / OpenAPI.

## Decisions locked (from user)

1. **MATLAB engine:** install `matlabengine` from PyPI, auto-matched to the detected local MATLAB release, as the **primary** path; keep the local-tree build only as an **offline fallback**.
2. **Docker:** build the **real** working image `FROM mathworks/matlab` + network license manager (`MLM_LICENSE_FILE`). Not a Win10-laptop path.
3. **Offline:** **keep** air-gapped support — retain `vendor/` + `install.bat` offline branch; extend `update_vendor.bat` to also fetch `matlabengine` sdists (`--no-binary :all:`).
4. **FastMCP scope this pass:** install/packaging overhaul + bump to 3.4.4 **and** adopt-now features **F5** (middleware metrics), **F6** (structured output), **F12** (streamable-http default).

---

## 1. MATLAB engine acquisition (the pivot)

`matlabengine` is published on PyPI but is **sdist-only**, and its build step reads the Windows registry and *raises* if a matching MATLAB isn't installed. Therefore it **must never** be a static dependency (would break `pixi install` / `pip install` / CI on any machine without that exact MATLAB). It is installed by a shared script.

**`scripts/install_matlab_engine.py`** (single source of truth, called by both pixi task and `install.bat`):
1. Detect installed release: registry `SOFTWARE\MathWorks\MATLAB` (non-admin readable) → fallback glob `C:\Program Files\MATLAB\R20??`, `%LOCALAPPDATA%\Programs\MATLAB`. Newest wins. `MATLAB_RELEASE` env override.
2. Map release → `matlabengine==<major>.<minor>.*` and pip-install (patch left `*`).
3. Offline fallback (air-gapped, PyPI unreachable): `pip install "%MATLABROOT%\extern\engines\python"` (plain local-tree build — no junctions).

**Version map (verified):** R2022b=9.13 · R2023a=9.14 · R2023b=9.15 · R2024a=24.1 · R2024b=24.2 · R2025a=25.1 · R2025b=25.2 · R2026a=26.1.

Runtime unchanged: `engine.py` lazy `importlib.import_module("matlab.engine")` stays as-is; a licensed local MATLAB R2022b+ still required.

## 2. Install matrix

| Method | Audience | Flow | Status |
|---|---|---|---|
| **Pixi** | Win10 desktop + local MATLAB (primary) | install pixi (PS one-liner / winget) → `pixi run start` → `pixi run install-engine` → `pixi run start` | recommended |
| `install.bat` (slimmed) | double-click / air-gapped | detects MATLAB → shared engine script → venv | supported |
| pip / venv | advanced / CI | `pip install matlab-mcp-python[monitoring]` + engine script | supported |
| **Docker** (`FROM mathworks/matlab`) | Linux/server + network license | `MLM_LICENSE_FILE=port@host; docker compose up` | supported (server-only) |
| ~~install.bat junction build~~ | — | deleted (superseded) | removed |
| ~~python:slim + host-MATLAB mount~~ | — | fiction — deleted | removed |

**pixi.toml** (repo root, commit `pixi.lock`): `[dependencies] python=">=3.10,<3.13"`; `[pypi-dependencies]` = editable self (`extras=["monitoring"]`) + `fastmcp=="==3.4.4"`; `matlabengine` **NOT** listed (task-installed). Tasks: `start`, `inspect`, `http`, `sse`, `dashboard`, `generate-token`, `install-engine`, `install-engine-offline`. `dev` feature for pytest/ruff/build/pip-audit.

**Dockerfile** (rewrite): `ARG MATLAB_RELEASE=r2025a`; `FROM mathworks/matlab:${MATLAB_RELEASE}`; apt python3/pip; `pip install matlabengine==25.1.*` (matched to image); `pip install ".[monitoring]"` (single source of truth → fastmcp 3.4.x, no plotly); `USER matlab`; HEALTHCHECK on `:8766/health`; `ENTRYPOINT matlab-mcp`; `CMD --transport streamablehttp`. Compose: `shm_size: 512m`, required `MLM_LICENSE_FILE`, `MATLAB_MCP_POOL_MAX_ENGINES=2` (1 engine = 1 license seat). Delete the bind-mount fiction.

## 3. FastMCP 3.4.4 adoption

**Bump everywhere:** pyproject `fastmcp>=3.4.4,<4.0.0`; pixi hard-pin `==3.4.4`; Dockerfile via pyproject; CLAUDE.md text; regenerate lock/vendor to 3.x closure; rebuild vendored project wheel to v1.5.0 (kills the offline-runs-v1.4.1/2.x drift).

**Adopt now:**
- **F5 Middleware** — new `src/matlab_mcp/middleware/timing.py` `TimingMiddleware(Middleware).on_call_tool` records duration + success/failure into `MetricsCollector`; registered in `create_server` (`server.py:393`). Migrate `executor.py`/`collector.py` imperative timing incrementally; own test pass (hot path).
- **F6 Structured output** — `ExecuteResult`/`CheckResult` Pydantic models in `tools/core.py`; annotate `execute_code`/`check_code` returns; `ToolResult(is_error=True)` for MATLAB errors. **Preserve current dict keys** (schema-additive; see open item).
- **F12 Transport** — default HTTP transport → `streamable-http` in docs/compose/Dockerfile; keep `sse` alias (must not break existing SSE clients).

**Defer:** F7 progress (job-loop rework), F8 auth providers, F9 resources/prompts, F10 elicitation cleanup, F11 tag-gating.
**Skip:** composition/proxy, OpenAPI, `task=True`/Docket.

## 4. Carried-over cleanup

- Drop unused **`plotly`** runtime dep (converter emits hand-built dicts; dashboard uses bundled `plotly.min.js`). −9.9MB vendor.
- Dedup redundant `cryptography` wheel; add dedup step to `update_vendor.bat`. −3.3MB.
- Reconcile version strings: install.bat banner, wiki "MATLAB 2020b+"→R2022b+, CLAUDE.md fastmcp text.
- Deprecate `environment.yml` / `environment-dev.yml` / `requirements-lock.txt` (superseded by pixi.lock + vendor) — one release, then remove; re-home the conda-test-pypi CI job onto pip.
- `install.bat`: drop unconditional `--trusted-host`; echo resolved install/venv dirs on LocalAppData fallback.
- CI guards: version-drift grep check; clean-venv offline smoke test (`pip install --no-index --find-links vendor`).

## 5. Proposed workstreams (implementation order)

- **WS1 — Engine bootstrap:** `scripts/install_matlab_engine.py` (+ tests); slim `install.bat` to call it; keep offline fallback branch.
- **WS2 — Pixi:** `pixi.toml` + committed `pixi.lock` + tasks; README quickstart.
- **WS3 — Docker:** rewrite Dockerfile + compose (mathworks/matlab, network license); fix healthcheck; update `docker-compose.test.yml`.
- **WS4 — FastMCP bump + drift:** pins everywhere, rebuild vendor/lock/wheel to 3.4.4/v1.5.0, `update_vendor.bat` fixes (project wheel via `pip wheel .`, matlabengine sdist, dedup), CI guards.
- **WS5 — FastMCP features:** F5 middleware, F6 structured output, F12 transport default.
- **WS6 — Cleanup/docs:** drop plotly, version strings, deprecate conda envs, consolidate install docs.

## 6. Verification

- `pixi run install-engine` unit-tested with mocked registry/release → correct `matlabengine==` pin per release.
- Offline smoke test in CI (`--no-index --find-links vendor`).
- Existing stdio + SSE + streamable-http integration tests must stay green (SSE back-compat is a hard constraint).
- `docker compose config` validates; image build gated behind a MATLAB-license-available CI flag (can't run mathworks/matlab without a license in generic CI).

## 7. Open items to settle during planning

- MATLAB release floor: keep advertising R2022b+ (maintain 9.13/9.14/9.15 mapping + fallback) vs raise. Default: keep R2022b+.
- F6 wire shape: schema-additive (same keys + emitted output_schema) — confirmed default to preserve existing clients.
- F5: replace vs run-alongside the imperative executor timing in this milestone. Default: add middleware, migrate incrementally (not a big-bang hot-path rewrite).
