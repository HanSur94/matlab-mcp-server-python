---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
verified: 2026-07-12T23:35:28Z
status: human_needed
score: 46/46 here-checkable must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps: []
deferred: []
human_verification:
  - test: "On a real Win10 box with a licensed MATLAB install, run `pixi run install-engine` (or `install.bat`)"
    expected: "Registry/glob detection finds the newest MATLAB release, resolves the matching `matlabengine==<maj>.<min>.*` PyPI pin, installs it into the venv, and `pixi run start` / the venv can then create real engines"
    why_human: "Requires Windows registry (SOFTWARE\\MathWorks\\MATLAB), a real MATLAB install, and PyPI network access — none available on this macOS CI-less verification host"
  - test: "`pip install --no-index --find-links vendor matlab-mcp-python` in a clean venv, then import matlab_mcp.server, on Windows with a matching CPython (3.10/3.11/3.12)"
    expected: "Resolves fully offline and imports cleanly (per the `offline-smoke` CI job, which correctly runs on `windows-latest`)"
    why_human: "vendor/ is a win_amd64-only wheelhouse by design (CONTEXT.md decision D-03); running the same command on this macOS host correctly fails at the platform-specific Pillow wheel (no macOS wheel vendored) — this is expected, not a bug, but only a Windows runner can prove the real path. CI's `offline-smoke` job already targets `windows-latest` correctly."
  - test: "Build and run the real `mathworks/matlab` Docker image against a live network license: `MLM_LICENSE_FILE=port@host docker compose up`"
    expected: "Image builds, container starts as `matlab`, engine pool comes up against the license server, `/health` on :8765 responds, and MCP tool calls execute real MATLAB code"
    why_human: "Requires the licensed `mathworks/matlab` base image and a reachable MLM license server — not available in this sandbox. CI gates the real build behind `vars.MATLAB_LICENSE_AVAILABLE`, so this has never run in generic CI either"
  - test: "`install.bat` end-to-end on a real Win10 machine (double-click, non-admin user)"
    expected: "Creates/activates venv, installs the project, calls `scripts/install_matlab_engine.py`, echoes resolved install/venv dirs on the LocalAppData fallback, and the server starts"
    why_human: "cmd.exe / venv activation / registry behavior can't be exercised on macOS. CI's `test-windows-install-bat` job does exercise this on `windows-latest`, but that CI run itself wasn't observed in this verification pass — flagged so a human confirms the CI job actually went green post-merge"
---

# Phase 8: Friendly Win10 Install (Pixi + Docker) + FastMCP 3.4.4 Verification Report

**Phase Goal:** Make the Win10 install dead-simple and no-admin friendly, runnable via both Pixi (desktop) and Docker (Linux/server), on FastMCP 3.4.4, adopting F5 (TimingMiddleware), F6 (structured output), and F12 (streamable-http default) — while retaining offline/air-gapped support and reconciling version-string drift.

**Verified:** 2026-07-12T23:35:28Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All must-haves below are drawn from the `must_haves.truths` blocks of PLAN.md 08-01 through 08-10 (10 plans, WS1–WS6). Every truth that is checkable on this host (no MATLAB, no Windows registry, no Docker license) was independently re-derived from the actual codebase — not from SUMMARY.md narrative.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Engine script detects newest release + maps every R2022b..R2026a to correct `matlabengine==<maj>.<min>.*` pin | ✓ VERIFIED | `scripts/install_matlab_engine.py` `RELEASE_TO_ENGINE`/`_RELEASE_RANK` cover all 8 releases; `resolve_engine_spec()` whitelist-gated; 28/28 `tests/test_install_matlab_engine.py` pass (`pixi run -e dev pytest tests/test_install_matlab_engine.py -q` → 28 passed) |
| 2 | `MATLAB_RELEASE` env override only accepts whitelisted tokens (injection guard) | ✓ VERIFIED | `resolve_engine_spec()` raises `ValueError` for any token not in `RELEASE_TO_ENGINE`; token never string-interpolated raw into pip spec |
| 3 | Offline fallback installs from local `extern/engines/python` tree when `MATLAB_MCP_VENDOR` set or online install fails | ✓ VERIFIED | `_is_offline_forced()` / `_install_offline()` / `except (CalledProcessError, OSError)` fallback branch in `install_engine()` |
| 4 | `matlabengine` never a static dependency | ✓ VERIFIED | `grep -ri matlabengine pyproject.toml pixi.toml requirements-lock.txt` → zero live matches (only comments); CI `pixi` job has a regression-guard step asserting the same |
| 5 | `install.bat` calls the shared script, junction/robocopy/PowerShell dance removed, offline branch retained, unconditional `--trusted-host` dropped, banner version current | ✓ VERIFIED | `grep -i "mklink\|robocopy\|trusted-host" install.bat` → no matches; `install_matlab_engine.py` invoked at line 263; banner says `v1.5.0` matching `pyproject.toml` `version = "1.5.0"` |
| 6 | `pyproject.toml` pins `fastmcp>=3.4.4,<4.0.0`; plotly runtime dep removed | ✓ VERIFIED | `pyproject.toml:31` `"fastmcp>=3.4.4,<4.0.0"`; no `plotly` in `[project.dependencies]` (internal `matlab_mcp.output.plotly_*` modules retained, only PyPI dep dropped) |
| 7 | `CLAUDE.md` references FastMCP 3.4.4, not stale 2.14.5 | ✓ VERIFIED | `CLAUDE.md:32,50` mention `fastmcp>=3.4.4,<4.0.0`; no `2.14.5` string found |
| 8 | Package imports and full test suite green after dependency changes | ✓ VERIFIED | `pixi run -e dev pytest tests/ -q` (fastmcp 3.4.4 env, matching pixi.lock) → **939 passed, 3 skipped**. See note below on base-env run. |
| 9 | `TimingMiddleware.on_call_tool` records duration + success/failure into `MetricsCollector`, re-raises on error, registered in `create_server` when monitoring enabled, doesn't double-count executor's job counters | ✓ VERIFIED | `src/matlab_mcp/middleware/timing.py` full implementation read; distinct `"tool_call"` event type (not `job_completed`/`job_failed`); `except Exception: ...; raise` re-raise path; `server.py:403-406` wires `mcp.add_middleware(TimingMiddleware(state.collector))` |
| 10 | `pixi.toml` defines project + friendly tasks (start/inspect/http/sse/dashboard/generate-token/install-engine/install-engine-offline); `matlabengine` absent from `[pypi-dependencies]`; `pixi.lock` committed | ✓ VERIFIED | Full `pixi.toml` read — all 8 tasks present; `matlabengine` absent (only comments reference it); `pixi.lock` exists (225.7K, 3534 lines), committed |
| 11 | README documents pixi Win10 quickstart, streamablehttp preferred / sse legacy alias | ✓ VERIFIED | `README.md:110-178` — Pixi section, `pixi run http` (preferred) vs `pixi run sse` (legacy alias) documented |
| 12 | `execute_code`/`check_code` emit structured output via `ExecuteResult`/`CheckResult` Pydantic models, dict keys preserved (wire-compat), errors returned as `ToolResult(is_error=True)` | ✓ VERIFIED | `src/matlab_mcp/tools/core.py:44,97` model definitions; `server.py:458,462,484,488` wire `ExecuteResult(**result).to_wire_dict()` / `ToolResult(content=summary, structured_content=wire, is_error=True)`; **behaviorally proven** — `tests/test_structured_output.py` passes fully under fastmcp 3.4.4 (`TestToolResultErrorPath.test_execute_code_error_returns_tool_result_is_error` and `test_check_code_error_returns_tool_result_is_error` both green in the 939-passed pixi dev run) |
| 13 | Dockerfile builds `FROM mathworks/matlab:${MATLAB_RELEASE}`, installs matched `matlabengine`, installs project via pyproject, `USER matlab`, correct healthcheck port, `streamablehttp` default CMD | ✓ VERIFIED | Full `Dockerfile` read — matches every clause exactly, healthcheck targets `:8765/health` (not stale `:8766`) |
| 14 | `docker-compose.yml` requires `MLM_LICENSE_FILE`, `shm_size: 512m`, `POOL_MAX_ENGINES=2`, `python:slim`/bind-mount fiction deleted | ✓ VERIFIED | Full file read; fail-fast `:?` guard tested live: `docker compose config` errors with `"required variable MLM_LICENSE_FILE is missing a value"` when unset, succeeds and resolves cleanly when set |
| 15 | `docker compose config` validates; real image build gated behind MATLAB-license CI flag | ✓ VERIFIED | Ran `docker compose config` locally (with `MLM_LICENSE_FILE` set) → clean resolved YAML; CI `docker` job gates `docker build`/run steps behind `if: vars.MATLAB_LICENSE_AVAILABLE == 'true'`, `docker compose config` step itself unconditional |
| 16 | `update_vendor.bat` builds project wheel, fetches matlabengine sdist, dedups wheels; vendor reflects fastmcp 3.4.x closure, exactly one cryptography wheel, no plotly | ✓ VERIFIED | `vendor/` contains `fastmcp-3.4.4-py3-none-any.whl`, `matlabengine-25.1.2.tar.gz` (sdist, correctly not a wheel), `matlab_mcp_python-1.5.0-py3-none-any.whl` (project wheel), exactly one `cryptography-49.0.0-cp39-abi3-win_amd64.whl`, zero plotly wheels |
| 17 | `requirements-lock.txt` carries deprecation notice pointing to pixi.lock; offline install from vendor resolves and imports | ✓ VERIFIED (notice) / ⚠️ see below (offline install) | Notice present at top of `requirements-lock.txt`. Offline install *attempted* on this macOS host and correctly fails at the Pillow win_amd64-only wheel — **this is expected behavior, not a defect**, since vendor is intentionally a win_amd64-only wheelhouse (D-03). CI's `offline-smoke` job correctly runs on `windows-latest`. Routed to human verification since the real Windows path can't be proven here. |
| 18 | `environment.yml`/`environment-dev.yml` carry deprecation notices pointing to pixi, retained for one release; wiki reconciled to R2022b+ | ✓ VERIFIED (scoped) | Deprecation notices present in both env files. `wiki/Installation.md` correctly says R2022b+. **Known scoped gap** (not a must-have miss — 08-09-SUMMARY explicitly scoped itself to Installation.md only): `wiki/Architecture.md`, `wiki/FAQ.md`, `wiki/Home.md`, `wiki/Troubleshooting.md` still say "MATLAB 2020b+". Documented below under Anti-Patterns/Minor Gaps — non-blocking. |
| 19 | CI: version-drift guard fails build on disagreement across pyproject/lock/Dockerfile/CLAUDE.md/install.bat | ✓ VERIFIED | `.github/workflows/ci.yml` `drift-guard` job read in full; manually re-executed its exact grep/sed logic locally → `ALL DRIFT CHECKS PASSED` (project=1.5.0, fastmcp=3.4.4, all four files agree) |
| 20 | CI: clean-venv offline smoke test installs from vendor and imports | ✓ VERIFIED | `offline-smoke` job in `ci.yml` runs on `windows-latest`, uses `--no-index --find-links vendor`, correctly targeted at the win_amd64 wheelhouse |
| 21 | CI: pixi job runs `pixi install` without MATLAB and asserts engine-free import; matlabengine absent from pixi.toml deps (regression guard) | ✓ VERIFIED | `ci.yml` `pixi` job present with both the regression-guard grep step and the `pixi install` + engine-free import step; **independently reproduced locally**: `pixi run python -c "from matlab_mcp.server import main"` → `OK engine-free import` |
| 22 | Real mathworks/matlab Docker build gated behind license flag; `docker compose config` unconditional | ✓ VERIFIED | `ci.yml` `docker` job — `docker compose config` step has no `if:` guard; `docker build`/run steps guarded by `vars.MATLAB_LICENSE_AVAILABLE == 'true'` |
| 23 | conda-test-pypi published-wheel smoke re-homed onto pip | ✓ VERIFIED | `ci.yml` `pip-test-pypi` job uses plain `pip install matlab-mcp-python`, no conda dependency; explanatory comment confirms the re-home |

**Score:** 23/23 distinct truths verified across the 10 plans (46 lower-level must-have artifact/key-link checks folded in — see below), 0 present-but-behavior-unverified, 0 failed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/install_matlab_engine.py` | Engine detection/mapping/install (90+ lines, exports RELEASE_TO_ENGINE/detect_release/resolve_engine_spec/install_engine/main) | ✓ VERIFIED | 419 lines; all 5 exports present and read in full |
| `tests/test_install_matlab_engine.py` | Mocked-registry unit tests (60+ lines) | ✓ VERIFIED | 186 lines, 28 tests, all pass |
| `pyproject.toml` | fastmcp 3.4.4 pin, no plotly | ✓ VERIFIED | Contains exact string `fastmcp>=3.4.4,<4.0.0` |
| `CLAUDE.md` | Reconciled fastmcp version string | ✓ VERIFIED | References 3.4.4, no 2.14.5 |
| `src/matlab_mcp/middleware/timing.py` | TimingMiddleware (30+ lines) | ✓ VERIFIED | Full file read, wired |
| `tests/test_middleware_timing.py` | Middleware unit tests (40+ lines) | ✓ VERIFIED | Passing as part of 939-test run |
| `install.bat` | Slimmed installer delegating to shared script | ✓ VERIFIED | Contains `install_matlab_engine.py`, no junction/PowerShell hacks |
| `pixi.toml` | Workspace, deps, tasks, dev feature | ✓ VERIFIED | Contains `install-engine` task and all others |
| `pixi.lock` | Committed reproducible lockfile | ✓ VERIFIED | 225.7K, committed, resolves fastmcp 3.4.4 in dev env |
| `README.md` | Pixi quickstart + transport guidance | ✓ VERIFIED | Section present |
| `src/matlab_mcp/tools/core.py` | ExecuteResult/CheckResult models | ✓ VERIFIED | Both classes defined with full docstrings |
| `src/matlab_mcp/server.py` | execute_code/check_code wrappers | ✓ VERIFIED | Annotated `-> ExecuteResult` / `-> CheckResult`, wire dict built |
| `tests/test_structured_output.py` | Wire-compat + schema + error-path tests (40+ lines) | ✓ VERIFIED | Passing under fastmcp 3.4.4 |
| `Dockerfile` | mathworks/matlab image | ✓ VERIFIED | Contains `mathworks/matlab` |
| `docker-compose.yml` | Network-license compose | ✓ VERIFIED | Contains `MLM_LICENSE_FILE` |
| `docker-compose.test.yml` | CI remote-integration compose | ✓ VERIFIED | Aligned to new image, no python:slim assumptions |
| `update_vendor.bat` | Vendor refresh incl. project wheel/matlabengine sdist/dedup | ✓ VERIFIED | Contains `pip wheel` |
| `requirements-lock.txt` | Deprecated lockfile with notice | ✓ VERIFIED | Notice present at top |
| `.github/workflows/ci.yml` | Drift guard, offline smoke, pixi job, license-gated docker, pip-rehomed publish smoke | ✓ VERIFIED | Contains `--no-index --find-links`; all 5 sub-requirements present |
| `wiki/Installation.md` | Reconciled install docs (R2022b+, pixi-first) | ✓ VERIFIED | R2022b+ present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `scripts/install_matlab_engine.py` | `RELEASE_TO_ENGINE` map | `resolve_engine_spec` validates before pip spec | ✓ WIRED | Confirmed via test suite + manual read |
| `src/matlab_mcp/server.py create_server` | `TimingMiddleware` | `mcp.add_middleware(TimingMiddleware(state.collector))` | ✓ WIRED | Line 405, confirmed present |
| `src/matlab_mcp/middleware/timing.py` | `MetricsCollector.record_event` | `record_event(event_type, details_dict)` | ✓ WIRED | Exact signature used, no `duration=` kwarg misuse |
| `pixi.toml [tasks] install-engine` | `scripts/install_matlab_engine.py` | task cmd | ✓ WIRED | `install-engine = "python scripts/install_matlab_engine.py"` |
| `src/matlab_mcp/server.py execute_code` | `ExecuteResult` | return-type annotation drives output_schema | ✓ WIRED | Confirmed + behaviorally tested |
| `Dockerfile HEALTHCHECK` | `/health` on :8765 | urllib request | ✓ WIRED | Confirmed, comment explains why not :8766 |
| `update_vendor.bat` | `vendor/` wheelhouse | pip download/wheel/dedup | ✓ WIRED | vendor/ contents match expected shape |
| `wiki/Installation.md` | pixi quickstart | R2022b+ floor documented | ✓ WIRED | Confirmed |
| `.github/workflows/ci.yml offline-smoke job` | `vendor/` wheelhouse | `pip install --no-index --find-links vendor` | ✓ WIRED | Confirmed, correctly gated to `windows-latest` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green under the fastmcp 3.4.4 environment the phase targets | `pixi run -e dev pytest tests/ -q` | 939 passed, 3 skipped | ✓ PASS |
| Full test suite under the ambient macOS base Python (stale fastmcp 3.2.0, pre-existing/unmanaged) | `python3 -m pytest tests/ -q` | 937 passed, 2 failed (`ToolResult(is_error=...)` unsupported kwarg on fastmcp 3.2.0) | ℹ️ INFO — not a phase gap; see note below |
| Engine-free server import via pixi default env | `pixi run python -c "from matlab_mcp.server import main"` | `OK engine-free import` | ✓ PASS |
| Engine-detection unit tests | `pixi run -e dev pytest tests/test_install_matlab_engine.py -q` | 28 passed | ✓ PASS |
| Lint on phase-modified files | `pixi run -e dev ruff check src/ tests/ scripts/` | 9 pre-existing errors, all in files last touched by Phase 07 (`tests/conftest.py`, `tests/test_executor_extra.py`, `tests/test_monitoring_dashboard.py`) — none in phase 08's `files_modified` | ℹ️ INFO — pre-existing debt, out of phase 08 scope |
| `docker compose config` (license var set) | `MLM_LICENSE_FILE=27000@localhost docker compose config` | Resolves cleanly | ✓ PASS |
| `docker compose config` (license var unset) — fail-fast guard | `docker compose config` | `error: ... required variable MLM_LICENSE_FILE is missing a value` | ✓ PASS (guard fires as designed) |
| Version-drift guard logic (re-executed exactly, locally) | grep/sed checks from `ci.yml drift-guard` job | `ALL DRIFT CHECKS PASSED` | ✓ PASS |
| Offline vendor install on non-Windows host | `pip install --no-index --find-links vendor matlab-mcp-python` (macOS venv) | Fails at Pillow (win_amd64-only wheel, no macOS wheel vendored — by design) | ℹ️ EXPECTED FAILURE on this host — see human_verification |

**Note on the two macOS base-env test failures:** The ambient `python3`/anaconda environment on this host has fastmcp 3.2.0 installed (pre-existing, unrelated to this phase's dependency management — it is not managed by pixi.lock or pyproject.toml's `>=3.4.4` floor). Running the same suite through `pixi run -e dev pytest` — the environment that actually resolves the pinned `fastmcp==3.4.4` from `pixi.lock` — gives 939 passed, 3 skipped, 0 failed, matching the verification guidance's expected count. The 2 failures are an artifact of testing against the wrong (unpinned, stale) interpreter, not a defect in the delivered code.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| D-01 | PyPI matlabengine primary + local-build fallback | ✓ SATISFIED | `scripts/install_matlab_engine.py`, `install.bat`, `pixi.toml install-engine` task |
| D-02 | Real `mathworks/matlab` Docker + network license | ✓ SATISFIED | `Dockerfile`, `docker-compose.yml` |
| D-03 | Keep offline/air-gapped support | ✓ SATISFIED | `vendor/` retained, offline fallback branch in engine script, `update_vendor.bat` extended |
| D-04 | Adopt-now FastMCP features F5/F6/F12 | ✓ SATISFIED | TimingMiddleware, ExecuteResult/CheckResult, streamablehttp default |

No orphaned requirements found — all 4 locked decisions map to at least one plan's `requirements` field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `wiki/Architecture.md`, `wiki/FAQ.md`, `wiki/Home.md`, `wiki/Troubleshooting.md` | various | Stale "MATLAB 2020b+" floor (should be R2022b+) | ℹ️ Minor / non-blocking | 08-09-SUMMARY.md explicitly scoped its "reconcile version strings" work to `wiki/Installation.md` only (documented rationale: "scope is Installation.md's MATLAB floor + pixi-first + version-string reconciliation only, not a full doc rewrite"). This was not a declared must-have for 08-09 or any other plan, so it does not fail a must-have, but it does leave the ROADMAP-level goal text ("reconcile version strings") partially unmet across the wiki as a whole. Recommend a follow-up task in a later phase/cleanup pass. |

No debt markers (TBD/FIXME/XXX), no unresolved TODO/HACK/PLACEHOLDER strings, and no empty-implementation stubs found in any of the 21 files this phase modified.

### Human Verification Required

See frontmatter `human_verification:` — 4 items, all genuinely requiring a licensed Windows/MATLAB/Docker environment this sandbox cannot provide:

1. **`pixi run install-engine` / `install.bat` on real Win10 + licensed MATLAB** — the actual registry detection → matlabengine pip install → working engine path.
2. **Offline `pip install --no-index --find-links vendor` on Windows** — the win_amd64 wheelhouse can only be proven on a matching platform; correctly and expectedly fails here on macOS (Pillow has no macOS wheel vendored, by design).
3. **Real `mathworks/matlab` Docker image build + run against a live network license** — needs the licensed base image and an MLM license server.
4. **`install.bat` end-to-end on Win10** — cmd.exe/venv/registry behavior; CI's `test-windows-install-bat` job exercises this, but a human should confirm that CI job is green post-merge.

### Gaps Summary

No blocking gaps. Every must-have that is checkable without a licensed Windows/MATLAB/Docker environment passed verification against the actual codebase (not SUMMARY.md narrative) — including live re-execution of the version-drift guard logic, `docker compose config` (both the success and fail-fast paths), the full pixi-dev test suite (939 passed under the fastmcp 3.4.4 environment this phase targets), the 28 mocked-registry engine-detection tests, and an engine-free server import via pixi.

One minor, explicitly-scoped documentation gap is noted (stale "MATLAB 2020b+" in 4 of 5 wiki pages) — this was intentionally out of scope for 08-09 per its own SUMMARY and does not block phase completion, but is surfaced for a follow-up cleanup task.

Overall status is `human_needed` rather than `passed` because 4 genuinely Windows/license-gated behaviors cannot be exercised in this environment and must be confirmed by a human (or by observing green CI on `windows-latest` / a license-enabled runner) before the phase's Win10/Docker promises are fully proven end-to-end.

---

_Verified: 2026-07-12T23:35:28Z_
_Verifier: Claude (gsd-verifier)_
