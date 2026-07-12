---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 05
subsystem: infra
tags: [pixi, packaging, install, fastmcp, readme, win10]

# Dependency graph
requires:
  - phase: 08-01
    provides: "scripts/install_matlab_engine.py (single source of truth for matlabengine acquisition, whitelisted release->spec map)"
  - phase: 08-02
    provides: "fastmcp>=3.4.4,<4.0.0 pin in pyproject.toml"
provides:
  - "pixi.toml workspace manifest (editable self + fastmcp==3.4.4, matlabengine deliberately absent)"
  - "Friendly pixi tasks: start, inspect, http, sse, dashboard, generate-token, install-engine, install-engine-offline"
  - "dev feature (pytest/ruff/build/pip-audit) with test/lint/audit tasks"
  - "Committed, solver-generated pixi.lock covering win-64/linux-64/osx-64/osx-arm64"
  - "README pixi quickstart + streamablehttp (preferred) vs sse (legacy alias) transport guidance"
affects: [08-10, docs, ci]

# Tech tracking
tech-stack:
  added: [pixi]
  patterns:
    - "matlabengine is NEVER a static dependency in any manifest (pip, pixi) — only installed by scripts/install_matlab_engine.py via a task/step"
    - "Friendly one-word pixi tasks map 1:1 onto existing matlab-mcp CLI flags (--transport, --inspect, --generate-token)"

key-files:
  created: [pixi.toml, pixi.lock]
  modified: [README.md]

key-decisions:
  - "Used pixi's current [workspace] table (pixi 0.72.2 schema) rather than the older [project] alias, matching what `pixi init` itself generates"
  - "pixi.lock generated with the real pixi binary (installed user-locally via the official install script, no admin) rather than fabricated by hand"
  - "dashboard task opens the dashboard URL via `python -c \"import webbrowser...\"` rather than a shell-specific opener, so it works identically on Windows/macOS/Linux"

requirements-completed: [D-01, D-04]

coverage:
  - id: D1
    description: "pixi.toml defines the workspace (python 3.10-3.12, editable-self + monitoring extra, fastmcp==3.4.4) with matlabengine absent from all dependency tables, plus friendly tasks including install-engine wired to scripts/install_matlab_engine.py"
    requirement: "D-01"
    verification:
      - kind: unit
        ref: "python -c \"import tomllib; ...\" tomllib parse + key assertions (pixi.toml)"
        status: pass
      - kind: other
        ref: "grep -qE 'matlabengine[[:space:]]*=' pixi.toml (must find nothing)"
        status: pass
    human_judgment: false
  - id: D2
    description: "pixi.lock is solver-generated (via real pixi 0.72.2 binary) and committed, referencing the fastmcp 3.x closure with no matlabengine entry"
    requirement: "D-01"
    verification:
      - kind: other
        ref: "pixi install (writes pixi.lock); grep -qi fastmcp pixi.lock; ! grep -qiE '^[[:space:]]*matlabengine:' pixi.lock"
        status: pass
      - kind: manual_procedural
        ref: "pixi run inspect started the server headlessly without MATLAB present (sanity check from environment_note)"
        status: pass
    human_judgment: false
  - id: D3
    description: "README documents the pixi no-admin Win10 quickstart (install pixi -> pixi run start -> pixi run install-engine -> pixi run start) and states streamablehttp is preferred with sse kept as a legacy alias"
    requirement: "D-04"
    verification:
      - kind: other
        ref: "grep -qi 'pixi run install-engine' README.md && grep -qi 'streamablehttp' README.md"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-07-13
status: complete
---

# Phase 08 Plan 05: Pixi Manifest + Committed Lock + README Quickstart Summary

**Repo-root `pixi.toml` (matlabengine deliberately excluded from every dependency table) with a real solver-generated `pixi.lock` and a README pixi quickstart positioning it as the recommended no-admin Win10 desktop path.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-13T00:20:00Z
- **Completed:** 2026-07-13T00:45:00Z
- **Tasks:** 3
- **Files modified:** 3 (2 created: pixi.toml, pixi.lock; 1 modified: README.md)

## Accomplishments
- Authored `pixi.toml`: workspace name `matlab-mcp-python`, channels `conda-forge`, platforms win-64/linux-64/osx-64/osx-arm64, python `>=3.10,<3.13`, editable self (`extras=["monitoring"]`) + `fastmcp==3.4.4`, with `matlabengine` deliberately absent and documented as such
- Added friendly tasks: `start`, `inspect`, `http` (streamablehttp, preferred), `sse` (legacy alias), `dashboard`, `generate-token`, `install-engine`, `install-engine-offline`; plus a `dev` feature with `test`/`lint`/`audit` tasks and a shared `default` solve-group
- Installed the real `pixi` binary (0.72.2) user-locally (no admin) and ran `pixi install`, generating a genuine solver-resolved `pixi.lock` covering all 4 platforms for both the `default` and `dev` environments; committed verbatim
- Sanity-checked headlessly: `pixi run inspect` started the MCP server without MATLAB present (confirms the editable install + dependency closure actually works, not just parses)
- Added a "Pixi (recommended, no admin needed)" quickstart section to README (install pixi -> `pixi run start` -> `pixi run install-engine` -> `pixi run start`) ahead of the existing `install.bat` section, and updated the "Run it" section to document `streamablehttp` as the preferred HTTP transport with `sse` retained as a legacy alias

## Task Commits

Each task was committed atomically:

1. **Task 1: Author pixi.toml (deps, tasks, dev feature) with matlabengine deliberately absent** - `7b4e04f` (feat)
2. **Task 2: Generate and commit pixi.lock** - `7523652` (feat)
3. **Task 3: Add the Pixi quickstart and transport guidance to README** - `5753efc` (docs)

_No TDD tasks in this plan — all three were config/docs authoring._

## Files Created/Modified
- `pixi.toml` - Pixi workspace manifest: dependencies, pypi-dependencies (editable self + fastmcp pin, matlabengine intentionally omitted), tasks, dev feature, environments
- `pixi.lock` - Solver-generated, committed lockfile (3534 lines) covering 4 platforms x 2 environments
- `README.md` - New "Pixi (recommended, no admin needed)" quickstart subsection under Install the server; "Run it" section updated with streamablehttp/sse guidance

## Decisions Made
- Used the current pixi schema (`[workspace]` table, as produced by `pixi init` on pixi 0.72.2) rather than the deprecated `[project]` alias — both parse, but `[workspace]` is what a user installing pixi today will see generated and is what the tool itself considers canonical.
- Verified the real pixi binary could be installed and run in this sandbox (network was available), so the environment note's "preferred path" (generate a real lock) was followed in full rather than falling back to the deferred-lock path.
- Kept `install.bat` / pip instructions completely unchanged in README — pixi is additive and positioned first as the recommended path, per the plan's prohibition on removing existing install methods.

## Deviations from Plan

None - plan executed exactly as written. The environment note anticipated pixi might not be installable in this sandbox; it was (network access to pixi.sh and conda-forge/PyPI indexes was available), so the preferred (real-lock) path was taken rather than the fallback (deferred-lock) path.

## Issues Encountered

None. `pixi install` completed in ~12s on the first attempt; `pixi run inspect` started the server headlessly and was manually killed via `pkill` after confirming clean startup logs (pool config printed correctly, no MATLAB required in inspect mode). No orphan processes remained afterward (confirmed via `ps aux`).

## User Setup Required

None - no external service configuration required. Users on Win10 will install pixi themselves via the documented PowerShell one-liner or `winget`; no secrets or manual dashboard config involved.

## Next Phase Readiness

`pixi.toml` + `pixi.lock` + README are in place and verified (tomllib parse, grep guards, full `pytest tests/ -x -q --timeout=30` suite: 923 passed / 0 failed / 3 skipped, unaffected by this plan). Ready for 08-10 (CI pixi job), which is expected to exercise `pixi install` / `pixi run test` against this exact manifest+lock pair in a clean CI environment — worth confirming there that the committed lock resolves identically on Linux CI runners (this plan validated osx-arm64 execution locally; the lock's linux-64/win-64 sections were solver-generated but not execution-tested in this sandbox).

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: pixi.toml
- FOUND: pixi.lock
- FOUND: README.md
- FOUND: 7b4e04f
- FOUND: 7523652
- FOUND: 5753efc
