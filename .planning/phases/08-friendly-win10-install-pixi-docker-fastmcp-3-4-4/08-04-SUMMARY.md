---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 04
subsystem: infra
tags: [install.bat, windows, matlabengine, pip, offline-fallback, tls]

# Dependency graph
requires:
  - phase: 08-01
    provides: "scripts/install_matlab_engine.py — single source of truth for MATLAB engine acquisition"
provides:
  - "install.bat delegates MATLAB engine acquisition to scripts/install_matlab_engine.py"
  - "Removal of the mklink junction / robocopy / PowerShell path-fixup engine-build machinery"
  - "install.bat no longer applies an unconditional --trusted-host override on the online pip path"
  - "LocalAppData writability fallback echoes resolved install and venv directories"
  - "Installer banner version reconciled to the current project version (1.5.0)"
affects: ["08-10 (version-drift CI guard depends on install.bat banner matching pyproject)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "install.bat now shells out to the shared, tested Python script (scripts/install_matlab_engine.py) for engine acquisition instead of duplicating fragile batch-level build logic"

key-files:
  created: []
  modified:
    - install.bat

key-decisions:
  - "MATLABROOT is set from the batch file's own MATLAB detection (!MATLAB_ROOT!) before every call to install_matlab_engine.py, not just on the offline branch — this lets the shared script's own automatic online-failure fallback (install_engine()) use it even when OFFLINE wasn't forced"
  - "The offline/vendor branch sets MATLAB_MCP_VENDOR=%VENDOR_DIR% to force the shared script down its local-tree fallback path, per the plan's explicit instruction"
  - "Kept the pre-existing HAS_ENGINE_API gate (based on install.bat's own MATLAB detection at extern\\engines\\python) so the engine step is skipped cleanly when no MATLAB was found, rather than always invoking the script and parsing its no-MATLAB error"

requirements-completed: [D-01, D-03]

coverage:
  - id: D1
    description: "install.bat calls scripts/install_matlab_engine.py for engine acquisition and the mklink/robocopy/PowerShell junction dance is fully removed"
    requirement: D-01
    verification:
      - kind: other
        ref: "grep -q install_matlab_engine.py install.bat && ! grep -qiE 'mklink|robocopy .*extern|Get-ChildItem' install.bat"
        status: pass
    human_judgment: true
    rationale: "Static grep confirms the code is gone and the new call is present, but install.bat cannot be executed on this macOS host — end-to-end behavior (does the engine actually install on a Windows box) is validated by the phase's test-windows-install-bat CI job / a human on Windows per 08-VALIDATION.md."
  - id: D2
    description: "Offline/air-gapped vendor branch sets MATLAB_MCP_VENDOR (and MATLABROOT) so the shared script builds from the local MATLAB tree instead of PyPI, preserving the air-gapped install path"
    requirement: D-03
    verification:
      - kind: other
        ref: "grep -n MATLAB_MCP_VENDOR install.bat (3 occurrences: set on offline branch, passed to script, cleared after)"
        status: pass
    human_judgment: true
    rationale: "Cannot execute a real offline install on this host; the wiring is statically verified, real air-gapped behavior needs a Windows box with no PyPI access."
  - id: D3
    description: "Unconditional --trusted-host pypi.org/files.pythonhosted.org is removed from every online pip install command in install.bat"
    requirement: D-01
    verification:
      - kind: other
        ref: "! grep -q trusted-host install.bat"
        status: pass
    human_judgment: false
  - id: D4
    description: "LocalAppData writability fallback echoes the resolved install directory and, once created, the resolved venv directory"
    verification:
      - kind: other
        ref: "grep -n 'Resolved install directory\\|Resolved virtual environment directory' install.bat"
        status: pass
    human_judgment: false
  - id: D5
    description: "Installer banner version string matches the current release (pyproject.toml version = 1.5.0), not the stale v1.3.0"
    verification:
      - kind: other
        ref: "grep -n 'Windows Installer v1.5.0' install.bat"
        status: pass
    human_judgment: false

# Metrics
duration: 12min
completed: 2026-07-13
status: complete
---

# Phase 08 Plan 04: Slim install.bat to delegate MATLAB-engine install Summary

**install.bat now delegates MATLAB engine acquisition to `scripts/install_matlab_engine.py`, deleting the fragile mklink/robocopy/PowerShell build dance while preserving the air-gapped offline branch; the blanket `--trusted-host` override is gone and the LocalAppData fallback is more transparent.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2/2 completed
- **Files modified:** 1 (`install.bat`)

## Accomplishments

- Deleted the entire `mklink /J` junction build, the `robocopy` copy of `extern\engines\python`, the `--no-build-isolation` local build, and the PowerShell `Get-ChildItem`/`Set-Content` path-fixup — replaced with a single `python "%~dp0scripts\install_matlab_engine.py"` call.
- Offline/vendor branch now sets `MATLAB_MCP_VENDOR=%VENDOR_DIR%` (and `MATLABROOT`) before calling the shared script, so an air-gapped install still builds from the local `<MATLABROOT>\extern\engines\python` tree instead of reaching PyPI.
- Removed the unconditional `PIP_TRUST=--trusted-host ...` variable and all four of its usages (pip upgrade, source install, PyPI install) — TLS verification is now restored on the online path (RESEARCH.md §5, threat T-08-04-TH).
- LocalAppData writability fallback now echoes the resolved install directory immediately, and the resolved venv directory once it's created, so the user can see where the installer landed.
- Reconciled the installer banner from the stale "v1.3.0" to "v1.5.0", matching `pyproject.toml`'s `version = "1.5.0"` (feeds the 08-10 version-drift CI guard).

## Task Commits

1. **Task 1: Replace the MATLAB Engine install section with a call to scripts/install_matlab_engine.py** - `4608b77` (feat)
2. **Task 2: Drop unconditional --trusted-host, echo resolved dirs on LocalAppData fallback, reconcile banner version** - `dd2547d` (fix)

_Note: both commits touch `install.bat`; they were split via hunk-level patch application so each commit maps to exactly one plan task._

## Files Created/Modified

- `install.bat` - Engine-install section now delegates to `scripts/install_matlab_engine.py`; junction/robocopy/PowerShell machinery removed; `--trusted-host` dropped from all pip invocations; LocalAppData fallback echoes resolved dirs; banner version reconciled to 1.5.0.

## Decisions Made

- `MATLABROOT` is set from the batch file's own MATLAB detection unconditionally (both online and offline branches) rather than only on the offline path, so the shared script's built-in "online pip failed -> fall back to local tree" behavior (`install_engine()` in `scripts/install_matlab_engine.py`) has a root to fall back to even when the user didn't force `MATLAB_MCP_VENDOR`.
- Left the pre-existing `HAS_ENGINE_API` gate (set during the batch file's own MATLAB detection, based on whether `extern\engines\python` exists) in place as a cheap short-circuit — if no MATLAB with an Engine API directory was found, the whole engine-install block is skipped with a clear message rather than invoking the Python script only to have it report "no MATLAB installation detected."

## Deviations from Plan

None — plan executed exactly as written. Both tasks matched their `<action>` and `<verify>` blocks with no additional fixes required.

## Issues Encountered

Verification greps ran cleanly on the first pass; no debugging needed. The only non-trivial step was splitting the single-file diff into two hunk-level patches (via `git apply --cached` on extracted diff hunks) so each plan task landed as its own atomic commit despite both tasks modifying `install.bat`.

## User Setup Required

None - no external service configuration required.

## Verification

Static checks (run on this macOS host; `install.bat` itself cannot execute here):

```
$ grep -q "install_matlab_engine.py" install.bat && ! grep -qiE "mklink|robocopy .*extern|Get-ChildItem" install.bat && echo "engine section slimmed"
engine section slimmed

$ ! grep -q "trusted-host" install.bat && ! grep -q "v1.3.0" install.bat && echo "trusted-host removed and banner reconciled"
trusted-host removed and banner reconciled

$ grep -n "MATLAB_MCP_VENDOR" install.bat
259:        set "MATLAB_MCP_VENDOR=%VENDOR_DIR%"
263:    python "%~dp0scripts\install_matlab_engine.py"
279:    set "MATLAB_MCP_VENDOR="

$ grep -n "Resolved install directory\|Resolved virtual environment directory" install.bat
33:    echo  [INFO] Resolved install directory: !INSTALL_DIR!
202:    echo  [INFO] Resolved virtual environment directory: %VENV_DIR%

$ grep -n "Windows Installer v1.5.0" install.bat
13:echo   MATLAB MCP Server - Windows Installer v1.5.0

$ grep -n "ENGINE_TEMP\|PIP_TRUST\|--no-build-isolation\|powershell" install.bat
(no output — all removed)
```

Runtime execution of `install.bat` (Python detection, venv creation, actual engine install, launch) is Windows-only and cannot be exercised on this macOS host. Per `08-VALIDATION.md` and this plan's `<verification>` block, end-to-end behavior is validated by the phase's `test-windows-install-bat` CI job, which exercises the real install path on Windows.

## Next Phase Readiness

`install.bat` is ready for the 08-10 version-drift CI guard (banner now matches `pyproject.toml`). No blockers for downstream phase-08 plans; this plan's changes are self-contained to `install.bat`.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED
- FOUND: install.bat
- FOUND: .planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-04-SUMMARY.md
- FOUND commit: 4608b77
- FOUND commit: dd2547d
