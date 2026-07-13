---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 09
subsystem: docs
tags: [conda, pixi, wiki, deprecation, matlab-floor, fastmcp]

# Dependency graph
requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4 (08-02)
    provides: pixi.toml + committed pixi.lock with start/install-engine/dev tasks
provides:
  - Deprecation notices on environment.yml / environment-dev.yml pointing users to pixi
  - wiki/Installation.md reconciled to the R2022b+ MATLAB floor and pixi-first install flow
affects: [08-10 (conda-test-pypi CI job re-home onto pip)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deprecated-but-functional config files: prepend a DEPRECATED header pointing to the replacement, keep the file working for one release"

key-files:
  created: []
  modified:
    - environment.yml
    - environment-dev.yml
    - wiki/Installation.md

key-decisions:
  - "Deprecate environment.yml/environment-dev.yml in place (header notice) rather than delete — conda CI (08-10) and existing conda users get one release of runway"
  - "wiki/Installation.md: pixi promoted to the top recommended path; pip/install.bat/conda demoted to labeled manual/alternative options, each explicitly deprecated or cross-referenced"

patterns-established: []

requirements-completed: [D-03, D-04]

coverage:
  - id: D1
    description: "environment.yml and environment-dev.yml carry a deprecation notice pointing to pixi (pixi run start / install-engine), remain valid YAML, and are unchanged functionally"
    requirement: D-03
    verification:
      - kind: other
        ref: "grep -qiE 'deprecat' environment.yml && grep -qi pixi environment.yml && grep -qiE 'deprecat' environment-dev.yml && grep -qi pixi environment-dev.yml"
        status: pass
      - kind: other
        ref: "python3 -c \"import yaml; yaml.safe_load(open('environment.yml')); yaml.safe_load(open('environment-dev.yml'))\""
        status: pass
    human_judgment: false
  - id: D2
    description: "wiki/Installation.md advertises MATLAB R2022b+ (not 2020b), Python 3.10+, and documents the pixi path as the recommended no-admin install with the install-engine step"
    requirement: D-04
    verification:
      - kind: other
        ref: "grep -q R2022b wiki/Installation.md && ! grep -qi 'MATLAB 2020b' wiki/Installation.md && grep -qi pixi wiki/Installation.md"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-12
status: complete
---

# Phase 08 Plan 09: Deprecate conda envs toward pixi + reconcile wiki version strings Summary

**environment.yml/environment-dev.yml now carry pixi-pointing deprecation headers; wiki/Installation.md leads with the pixi quickstart and advertises the correct R2022b+/Python 3.10+ floor instead of the stale MATLAB 2020b+ claim.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-12T23:07:00Z
- **Completed:** 2026-07-12T23:15:28Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- Both conda env files (`environment.yml`, `environment-dev.yml`) now open with a `DEPRECATED` header explaining they're superseded by the pixi workflow (`pixi.toml` + committed `pixi.lock`), retained for one release, and pointing to `pixi run start` / `pixi run install-engine` (dev file also references `pixi run -e dev test`). Both remain fully functional/valid YAML — nothing was deleted or broken, so the conda CI job can transition in 08-10.
- `wiki/Installation.md` prerequisites now state **MATLAB R2022b+** (was "MATLAB 2020b+") and Python 3.10+ unchanged. A new "Recommended: Install with Pixi" section — mirroring the README quickstart (pixi install via PowerShell/winget, `pixi run start` → `pixi run install-engine` → `pixi run start`) — sits at the top of the doc, ahead of the manual paths.
- The pre-existing Step 1/Step 2 manual instructions were retitled "(manual path)" with a note that they're already satisfied if the pixi quickstart was used, and `install.bat` / conda were folded in as labeled "Option C" (one-click Windows installer) and "Option D: conda (deprecated)" alternatives, cross-referencing the pixi-first guidance.
- Verified no lingering "MATLAB 2020b" text and no stale FastMCP version strings remain in the wiki (the only FastMCP mention added is the correct `fastmcp==3.4.4`, matching pixi.toml's hard pin).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add deprecation notices to environment.yml and environment-dev.yml** - `a397499` (docs)
2. **Task 2: Reconcile the MATLAB floor and install guidance in the wiki** - `a67c151` (docs)

**Plan metadata:** (pending final commit by orchestrator per objective — STATE.md/ROADMAP.md not touched by this executor)

## Files Created/Modified
- `environment.yml` - Prepended DEPRECATED header pointing to pixi (`pixi run start` / `install-engine`); YAML unchanged and still valid/functional
- `environment-dev.yml` - Prepended DEPRECATED header pointing to pixi dev workflow (`pixi run -e dev test`); YAML unchanged and still valid/functional
- `wiki/Installation.md` - MATLAB floor corrected 2020b -> R2022b+; new pixi-first quickstart section added at top; manual pip/install.bat/conda paths relabeled as alternatives with cross-references to pixi and to the deprecated conda envs

## Decisions Made
- Deprecate rather than delete the conda env files this pass, per the plan's explicit prohibition (`MUST NOT delete environment.yml / environment-dev.yml this pass`) and CONTEXT §4 ("one release, then remove").
- Mirror the README's existing pixi quickstart wording verbatim in the wiki (same commands/task names: `pixi run start`, `pixi run install-engine`) so the two docs don't drift from each other.
- Left the Docker section, Claude/Cursor MCP client config, and transport (`--transport sse`) sections untouched — out of scope for this plan (scope is Installation.md's MATLAB floor + pixi-first + version-string reconciliation only, not a full doc rewrite).

## Deviations from Plan

None - plan executed exactly as written. No Rule 1/2/3 auto-fixes were needed; both files/verify greps passed on the first pass.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. Documentation-only change.

## Next Phase Readiness
- 08-10 (re-home the conda-test-pypi CI job onto pip) can proceed: the conda env files are still valid/functional so the existing CI job keeps working until 08-10 swaps its dependency source.
- No blockers for downstream plans in this phase.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-12*

## Self-Check: PASSED

- FOUND: environment.yml
- FOUND: environment-dev.yml
- FOUND: wiki/Installation.md
- FOUND: .planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-09-SUMMARY.md
- FOUND commit: a397499
- FOUND commit: a67c151
