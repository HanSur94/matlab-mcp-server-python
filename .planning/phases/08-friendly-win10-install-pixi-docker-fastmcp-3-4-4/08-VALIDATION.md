---
phase: 8
slug: friendly-win10-install-pixi-docker-fastmcp-3-4-4
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-12
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Validation Architecture

How each workstream is validated (feeds Dimension 8; per-task map filled by the planner):

- **Engine bootstrap (`scripts/install_matlab_engine.py`)** — unit tests with a mocked registry / MATLAB glob assert the release→`matlabengine==X.Y.*` mapping for every supported release (R2022b→9.13 … R2026a→26.1), the newest-wins tiebreak, the `MATLAB_RELEASE` override, and the offline-fallback branch selection. No live MATLAB required (pip call mocked).
- **Pixi** — `pixi.toml` parses; `matlabengine` is absent from `[pypi-dependencies]` (regression test / CI grep, since a static entry breaks off-host `pixi install`); tasks resolve. CI job runs `pixi install` on a runner without MATLAB and asserts the server imports (engine-free).
- **Docker** — `docker compose config` validates; image build gated behind a `MATLAB_LICENSE_AVAILABLE` CI flag (generic CI cannot run `mathworks/matlab`); Dockerfile installs from pyproject (no stale pins). `docker-compose.test.yml` remote-integration test stays green.
- **FastMCP 3.4.4 + features** — existing stdio + SSE + streamable-http integration tests MUST stay green (SSE back-compat is a hard constraint). New unit tests: `TimingMiddleware.on_call_tool` records completed/failed events with duration into a fake collector; `ExecuteResult`/`CheckResult` serialize with the existing dict keys preserved (wire-compat) and emit an output schema; error path returns `ToolResult(is_error=True)`.
- **Vendor / drift** — CI clean-venv offline smoke test: `pip install --no-index --find-links vendor matlab-mcp-python` resolves and imports; a version-drift grep guard fails the build if fastmcp / project-version strings disagree across pyproject, lock, Dockerfile, CLAUDE.md, install.bat.
- **Cleanup** — grep asserts no `import plotly` remains and `plotly` is absent from deps; vendor contains exactly one `cryptography` wheel.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| _(filled by planner from PLAN.md tasks)_ | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_install_matlab_engine.py` — mocked-registry unit tests for the release→matlabengine mapping + fallback
- [ ] Existing `tests/conftest.py` fixtures cover the middleware/structured-output tests

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end `pixi run install-engine` on a real Win10 box with licensed MATLAB | Engine acquisition | Needs a licensed MATLAB install + Windows registry | On Win10: install pixi, `pixi run install-engine`, confirm `matlabengine==<release>.*` installed and `pixi run start` connects |
| Docker image runs against a real network license | Docker path | Needs `mathworks/matlab` + MLM license server | `MLM_LICENSE_FILE=port@host docker compose up`; confirm engine starts and MCP responds on :8765 |
