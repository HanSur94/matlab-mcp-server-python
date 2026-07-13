---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 02
subsystem: infra
tags: [fastmcp, pyproject, dependencies, plotly, packaging]

# Dependency graph
requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4 (plan 01)
    provides: scripts/install_matlab_engine.py (matlabengine acquisition, unrelated to this plan's dep pins)
provides:
  - "pyproject.toml pins fastmcp>=3.4.4,<4.0.0 (newest 3.x)"
  - "plotly runtime dependency removed from pyproject.toml (unused PyPI package)"
  - "CLAUDE.md FastMCP version string reconciled to 3.4.4"
affects: [08-05-pixi-pin, 08-07-docker, 08-08-vendor-rebuild, 08-10-drift-guard]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - pyproject.toml
    - CLAUDE.md

key-decisions:
  - "Left src/matlab_mcp/config.py OutputConfig.plotly_conversion flag untouched — it is a config toggle name, not an import of the plotly package"
  - "Only reconciled the FastMCP version string in CLAUDE.md; left the CLAUDE.md 'plotly>=5.9.0' Key Dependencies bullet and 'Plotly 6.6.0' Frameworks bullet as-is since Task 2's scope was explicitly the FastMCP string only and the plan's verify command did not require touching those lines"

patterns-established: []

requirements-completed: [D-04]

coverage:
  - id: D1
    description: "pyproject.toml pins fastmcp to >=3.4.4,<4.0.0 and removes the plotly>=5.9.0 runtime dependency (plus the stale 'plotly' keywords entry)"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "python -c \"import tomllib...\" (plan Task 1 automated verify) — confirmed fastmcp>=3.4.4 present, no plotly/matlabengine deps"
        status: pass
    human_judgment: false
  - id: D2
    description: "CLAUDE.md FastMCP version string reconciled to 3.4.4; package still imports (matlab_mcp.server, matlab_mcp.output.plotly_convert) with the plotly PyPI package absent from dependencies"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "grep -q 3.4.4 CLAUDE.md && ! grep -q 'FastMCP 2.14.5' CLAUDE.md && python -c import checks (plan Task 2 automated verify)"
        status: pass
      - kind: unit
        ref: "python -m pytest tests/ -x -q --timeout=30 (full suite, post dep changes)"
        status: pass
    human_judgment: false

# Metrics
duration: ~10min
completed: 2026-07-12
status: complete
---

# Phase 08 Plan 02: FastMCP 3.4.4 bump + plotly runtime-dep cleanup Summary

**Bumped the canonical `fastmcp` pin to `>=3.4.4,<4.0.0`, dropped the unused `plotly` PyPI runtime dependency from `pyproject.toml`, and reconciled the stale "FastMCP 2.14.5" string in CLAUDE.md.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-12 (session start)
- **Completed:** 2026-07-12T22:15:20Z
- **Tasks:** 2/2 completed
- **Files modified:** 2 (`pyproject.toml`, `CLAUDE.md`)

## Accomplishments
- `pyproject.toml [project.dependencies]` now reads `fastmcp>=3.4.4,<4.0.0` (was `>=3.2.0,<4.0.0`); `plotly>=5.9.0` line removed entirely; stale `"plotly"` entry dropped from the `keywords` list.
- `CLAUDE.md` Technology Stack ("Frameworks" and "Key Dependencies" sections) now reads "FastMCP 3.4.4" / `fastmcp>=3.4.4,<4.0.0` instead of the stale "FastMCP 2.14.5" / `fastmcp>=2.0.0,<3.0.0` strings — unblocks the 08-10 drift guard.
- Confirmed via `grep -rnE "^\s*(import|from)\s+plotly" src tests` that the plotly PyPI package is imported nowhere (empty result, both before and after the dependency removal) — the internal `matlab_mcp.output.plotly_convert` / `plotly_style_mapper` modules build JSON dicts by hand and the dashboard ships its own bundled `plotly.min.js`.
- Verified `matlab_mcp.server` and `matlab_mcp.output.plotly_convert` both still import cleanly with the plotly package absent from dependencies.
- Full test suite run post-change: `python -m pytest tests/ -x -q --timeout=30` → **917 passed, 0 failed, 3 skipped**.

## Task Commits

Each task was committed atomically:

1. **Task 1: Bump fastmcp to 3.4.4 and drop the plotly runtime dependency in pyproject.toml** - `1d3e5c6` (feat)
2. **Task 2: Reconcile the FastMCP version string in CLAUDE.md and confirm the package still imports with the plotly package absent** - `2d64dcc` (docs)

_Note: no test/refactor commits needed — this plan is a scoped dependency-manifest + docs-string change, not a TDD plan._

## Files Created/Modified
- `pyproject.toml` - `fastmcp` pin raised to `>=3.4.4,<4.0.0`; `plotly>=5.9.0` runtime dependency removed; stale `plotly` keyword dropped
- `CLAUDE.md` - FastMCP version string reconciled from "2.14.5" / `fastmcp>=2.0.0,<3.0.0` to "3.4.4" / `fastmcp>=3.4.4,<4.0.0` in both the Frameworks and Key Dependencies bullets

## Decisions Made
- Left `src/matlab_mcp/config.py`'s `OutputConfig.plotly_conversion` field completely untouched, per plan instruction — it is a config toggle name describing hand-built-JSON figure conversion, not an import of the `plotly` package, and removing/renaming it was explicitly out of scope.
- Scoped the CLAUDE.md edit strictly to the FastMCP version string (Task 2's stated scope) and did not touch the still-present `plotly>=5.9.0` / `Plotly 6.6.0` bullets elsewhere in CLAUDE.md's Technology Stack section — those describe the (now-removed) runtime dependency's former version but reconciling them was not part of this plan's acceptance criteria or verify command. Flagging here for whoever runs a broader CLAUDE.md dependency-drift pass later.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' automated verify commands passed on the first attempt with no auto-fixes required.

## Issues Encountered

None. Ran the required extra checks from the environment note:
- `grep -rnE "^\s*(import|from)\s+plotly" src tests` → empty (confirmed before making the pyproject.toml change).
- `grep -rnE "^\s*(import|from)\s+plotly(\s|\.)" src/` → empty (re-confirmed per plan's acceptance criteria after the change).
- `python -m pytest tests/ -x -q --timeout=30` → 917 passed, 0 failed, 3 skipped (full suite green after dropping the plotly dependency).
- `python -m ruff check src tests` → 9 pre-existing F401/F841 findings, all in test files (`tests/conftest.py`, `tests/test_executor_extra.py`, `tests/test_monitoring_dashboard.py`) that this plan's tasks did not touch (this plan only modified `pyproject.toml` and `CLAUDE.md`, no Python source). Out of scope per the executor's scope-boundary rule — not fixed, noted here for visibility rather than added to a separate deferred-items file since these predate this plan and are unrelated to fastmcp/plotly.

## User Setup Required

None - no external service configuration required. This is a dependency-manifest edit; the effect (fastmcp 3.4.4, no plotly) applies on the next `pip install` / `pixi install` of the package, not to this already-running environment (installed fastmcp here remains 3.2.0, as expected — see environment note).

## Next Phase Readiness
- pyproject.toml is now the correct canonical source (`fastmcp>=3.4.4,<4.0.0`, no plotly) for downstream plans that read it: 08-05 (pixi pin), 08-07 (Docker `pip install .[monitoring]`), 08-08 (vendor/lock rebuild), and 08-10 (CLAUDE.md/pyproject drift guard — CLAUDE.md's FastMCP string now matches).
- No blockers. The remaining stale `plotly` mentions in CLAUDE.md's Frameworks/Key Dependencies bullets (version numbers for the now-removed dependency) are a minor follow-up candidate for whichever later plan does the broader CLAUDE.md/docs consolidation pass (08-10 or a docs cleanup plan), since this plan's scope and verify command were limited to the FastMCP string only.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-12*

## Self-Check: PASSED

- FOUND: pyproject.toml
- FOUND: CLAUDE.md
- FOUND: .planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-02-SUMMARY.md
- FOUND commit: 1d3e5c6
- FOUND commit: 2d64dcc
