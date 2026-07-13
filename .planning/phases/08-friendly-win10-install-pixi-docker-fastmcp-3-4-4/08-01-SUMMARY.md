---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 01
subsystem: infra
tags: [matlabengine, pip, windows-registry, install, pixi, offline-fallback, security]

# Dependency graph
requires: []
provides:
  - "scripts/install_matlab_engine.py — single source of truth for MATLAB engine acquisition"
  - "RELEASE_TO_ENGINE whitelist mapping every supported release (R2022b..R2026a) to its matlabengine pin"
  - "detect_release() / resolve_engine_spec() / install_engine() / main() public API"
affects: ["08-04 (install.bat slimming)", "08-05 (pixi install-engine task)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single injectable subprocess seam (_run_pip_install) so pip invocation is fully mockable in tests"
    - "Whitelist-before-interpolation gate (resolve_engine_spec) as the injection guard for env/registry-derived tokens"
    - "Lazily-imported, platform-guarded winreg so the module always imports cleanly on non-Windows hosts"

key-files:
  created:
    - scripts/install_matlab_engine.py
    - tests/test_install_matlab_engine.py
  modified: []

key-decisions:
  - "Both the 'R20XXx' token and its numeric registry-style equivalent (e.g. '24.2') are whitelisted to the same matlabengine pin, since MATLAB's registry subkeys and install directory names use different conventions"
  - "install_engine() automatically falls back to the offline local-tree install on any online pip failure (not just when MATLAB_MCP_VENDOR is set), matching the plan's 'PyPI unreachable' offline-fallback trigger"
  - "_discover_releases() is a single patchable seam combining registry + glob results, so tests can inject arbitrary discovered-release sets without touching the real filesystem/registry"

patterns-established:
  - "Environment -> subprocess trust boundary: resolve untrusted tokens against a static whitelist dict before they can be interpolated into any shell-facing command"

requirements-completed: [D-01]

coverage:
  - id: D1
    description: "Every supported MATLAB release (R2022b..R2026a), by both R-token and numeric registry token, resolves to the correct matlabengine==<maj>.<min>.* pip pin"
    requirement: D-01
    verification:
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestResolveEngineSpecReleaseTokens::test_r_token_resolves_to_expected_pin"
        status: pass
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestResolveEngineSpecNumericTokens::test_numeric_token_resolves_to_expected_pin"
        status: pass
    human_judgment: false
  - id: D2
    description: "Unknown/garbage release tokens (e.g. spoofed MATLAB_RELEASE, tampered registry value) are rejected with ValueError before any pip spec is built, and the pip seam is never invoked"
    requirement: D-01
    verification:
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestResolveEngineSpecRejectsUnknownTokens::test_unknown_token_raises_value_error"
        status: pass
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestResolveEngineSpecRejectsUnknownTokens::test_unknown_token_never_reaches_pip_seam"
        status: pass
    human_judgment: false
  - id: D3
    description: "detect_release() picks the newest release when multiple are discovered, and MATLAB_RELEASE env var overrides on-disk detection"
    requirement: D-01
    verification:
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestDetectRelease::test_newest_wins_when_multiple_releases_discovered"
        status: pass
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestDetectRelease::test_env_override_forces_release_even_when_different_on_disk"
        status: pass
    human_judgment: false
  - id: D4
    description: "Offline fallback: MATLAB_MCP_VENDOR set, or an online pip failure, installs from <MATLABROOT>/extern/engines/python instead of a matlabengine== spec"
    requirement: D-01
    verification:
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestInstallEngineOffline::test_vendor_env_forces_local_tree_install"
        status: pass
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestInstallEngineOffline::test_online_pip_failure_falls_back_to_local_tree"
        status: pass
    human_judgment: false
  - id: D5
    description: "scripts/install_matlab_engine.py imports cleanly on non-Windows hosts (winreg guarded) and matlabengine is never listed as a static dependency in pyproject.toml/pixi.toml"
    verification:
      - kind: unit
        ref: "tests/test_install_matlab_engine.py::TestModuleImportSafety::test_module_imports_without_winreg_on_this_platform"
        status: pass
      - kind: other
        ref: "grep -rnE 'matlabengine[[:space:]]*=' pyproject.toml pixi.toml (no matches)"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-07-13
status: complete
---

# Phase 8 Plan 1: MATLAB Engine Install Script Summary

**`scripts/install_matlab_engine.py` — a fully unit-tested, whitelist-gated MATLAB-release-to-`matlabengine` installer with online PyPI + offline local-tree fallback, and zero static dependency footprint.**

## Performance

- **Duration:** 26 min (2026-07-12T23:45 -> 2026-07-13T00:11, per commit timestamps)
- **Tasks:** 2 (TDD RED/GREEN)
- **Files modified:** 2 (both new)

## Accomplishments
- `RELEASE_TO_ENGINE` whitelist maps every supported release (R2022b..R2026a), by both the human "R20XXx" token and MathWorks' numeric registry token, to its `matlabengine==<maj>.<min>.*` pip pin.
- `detect_release()` discovers installed MATLAB via the Windows registry (guarded `winreg` import, non-admin `HKLM`/`HKCU` read) or filesystem globs (Windows Program Files/LocalAppData, POSIX `/usr/local/MATLAB`, macOS `/Applications`), picks the newest when multiple are found, and honors a `MATLAB_RELEASE` env override.
- `resolve_engine_spec()` is the injection-guard security gate: it rejects any token not in the whitelist with `ValueError` — a spoofed `MATLAB_RELEASE`/registry value can never reach a pip command.
- `install_engine()` routes all pip invocation through one injectable seam (`_run_pip_install`), installs the resolved online spec by default, and falls back to the local `<MATLABROOT>/extern/engines/python` tree when `MATLAB_MCP_VENDOR` is set or the online install raises.
- `matlabengine` remains absent from every dependency manifest — confirmed by `grep` (no `pyproject.toml`/`pixi.toml` match).

## Task Commits

Each task was committed atomically (TDD RED -> GREEN):

1. **Task 1: Write failing unit tests (RED)** - `ff868a0` (test)
2. **Task 2: Implement scripts/install_matlab_engine.py (GREEN)** - `c2594e5` (feat)

**Plan metadata:** committed separately after this SUMMARY (see final commit below).

## Files Created/Modified
- `scripts/install_matlab_engine.py` - New. `RELEASE_TO_ENGINE`/`_RELEASE_RANK` maps, `detect_release`, `resolve_engine_spec`, `install_engine`, `main`, plus the registry/glob discovery and pip-seam helpers.
- `tests/test_install_matlab_engine.py` - New. 28 tests covering the full whitelist map, unknown-token rejection, newest-wins detection, env override, online install, offline fallback (vendor-forced and pip-failure-triggered), and cross-platform import safety.

## Decisions Made
- Whitelisted both release-token forms (R-token and numeric) to the same pin, since detection sources (registry vs. directory names) surface different token styles for the same MATLAB install.
- Treated "online pip install raises" as an automatic trigger for the offline fallback (in addition to the explicit `MATLAB_MCP_VENDOR` flag), matching the plan's "PyPI unreachable" language literally rather than requiring the caller to pre-detect connectivity.
- Kept `_discover_releases()` as one combined (registry + glob) seam rather than two separately-mocked functions, since the plan's acceptance criteria only requires the *combined* newest-wins behavior to be testable.

## Deviations from Plan

None - plan executed exactly as written. The runtime `engine.py` lazy-import path was read (per `<read_first>`) but not touched, as required.

One environment-only adjustment (not a code deviation): the pre-existing editable `matlab-mcp-python` install in this Python environment pointed at a different checkout (`/Users/hannessuhr/matlab-mcp-server-python`) rather than this worktree, which caused `ModuleNotFoundError: matlab_mcp` for every test in `tests/`, including pre-existing ones unrelated to this plan. Ran `pip install -e . --no-deps` from this worktree to repoint the editable install at the current tree so the test suite (and this plan's new tests) could actually execute here. This is a local dev-environment fix, not a repository change, and required no commit.

## Issues Encountered
None beyond the environment repoint noted above.

## User Setup Required

None - no external service configuration required. This script is a developer/CI tool invoked by future plans (08-04 `install.bat`, 08-05 pixi task); it makes no runtime server changes.

## Next Phase Readiness

- `scripts/install_matlab_engine.py` is ready to be called by 08-04 (slimmed `install.bat`) and 08-05 (pixi `install-engine` task) exactly as designed in `08-CONTEXT.md` §1 and `08-RESEARCH.md` §1.
- Verification commands specified in the plan all pass:
  - `python -m pytest tests/test_install_matlab_engine.py -q --timeout=30` -> 28 passed.
  - `python -m pytest tests/ -x -q --timeout=30` (full suite) -> 917 passed, 0 failed, 3 skipped.
  - `grep -rnE "matlabengine[[:space:]]*=" pyproject.toml pixi.toml` -> no matches (pixi.toml does not exist yet; that's expected, it lands in 08-05/WS2).
  - `ruff check scripts/install_matlab_engine.py tests/test_install_matlab_engine.py` -> no issues.
- No blockers for downstream plans in this phase.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED
- FOUND: scripts/install_matlab_engine.py
- FOUND: tests/test_install_matlab_engine.py
- FOUND: .planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-01-SUMMARY.md
- FOUND: ff868a0 (test commit)
- FOUND: c2594e5 (feat commit)
