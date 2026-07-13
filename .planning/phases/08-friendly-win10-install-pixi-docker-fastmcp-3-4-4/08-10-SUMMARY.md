---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 10
subsystem: infra
tags: [ci, github-actions, pixi, docker, fastmcp, version-drift, offline-install]

requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4 (08-01..08-09)
    provides: >
      Final-state pyproject.toml/Dockerfile/CLAUDE.md/install.bat/pixi.toml/vendor
      that this plan's CI guards grep against and exercise
provides:
  - CI version-drift guard across pyproject.toml/requirements-lock.txt/CLAUDE.md/install.bat
  - CI clean-venv offline smoke test against the vendor/ win_amd64 wheelhouse
  - CI pixi job proving engine-free `pixi install` + matlabengine-absent regression guard
  - License-gated mathworks/matlab Docker image build with unconditional compose-config validation
  - Published-wheel smoke test re-homed from conda onto pip
affects: [ci-pipeline, release-process]

tech-stack:
  added: [prefix-dev/setup-pixi GitHub Action]
  patterns:
    - "Version-drift grep guard: sed-based (POSIX BRE) extraction of version strings, comment-stripped before comparison, to avoid GNU-only grep -P dependence"
    - "License-gated CI step via repository variable (vars.MATLAB_LICENSE_AVAILABLE) rather than unconditional execution"

key-files:
  created: []
  modified:
    - .github/workflows/ci.yml

key-decisions:
  - "offline-smoke runs on windows-latest (not ubuntu-latest) because vendor/ is a win_amd64-only wheelhouse (confirmed by inspecting vendor/ contents — pillow, cffi, pydantic_core, watchfiles, websockets, rpds_py, pywin32 all ship only win_amd64 wheels); a Linux runner cannot resolve --no-index --find-links vendor"
  - "drift-guard uses sed (POSIX BRE) instead of grep -oP to avoid depending on GNU grep's PCRE extension being present on the runner shell"
  - "docker job: only the standalone build+pool-start smoke test is gated behind vars.MATLAB_LICENSE_AVAILABLE; remote-integration-test (docker compose -f docker-compose.test.yml, --inspect mode) is left unchanged per plan instruction since mathworks/matlab is a public Docker Hub image (verified: HEAD https://hub.docker.com/v2/repositories/mathworks/matlab/ -> 200) and --inspect mode never starts a licensed engine"
  - "docker compose config / docker compose -f docker-compose.test.yml config both need MLM_LICENSE_FILE merely *set* (not real) to pass the docker-compose.yml fail-fast `:?` guard — used a placeholder value (27000@ci-placeholder) for config validation only, never used to contact a license server"
  - "conda-test-pypi renamed to pip-test-pypi and re-homed onto plain pip install matlab-mcp-python; conda-test-dev left unchanged (still using environment-dev.yml) per the plan's 'may stay or be dropped' allowance"

requirements-completed: [D-01, D-02, D-03, D-04]

coverage:
  - id: D1
    description: "drift-guard CI job fails the build on fastmcp/project version disagreement across pyproject.toml, requirements-lock.txt, CLAUDE.md, install.bat"
    requirement: "D-01"
    verification:
      - kind: other
        ref: "python3 -c \"import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); assert 'drift-guard' in d['jobs']\" — ran locally, passes"
        status: pass
      - kind: other
        ref: "Extracted the exact embedded drift-guard script and ran it standalone with a portable /bin/bash (bypassing shell aliases): green on the clean tree, and confirmed it fails (exit 1, correct error message) when CLAUDE.md was mutated to reintroduce '2.14.5' in a scratch copy"
        status: pass
    human_judgment: false
  - id: D2
    description: "offline-smoke CI job installs matlab-mcp-python from vendor/ with --no-index --find-links and imports matlab_mcp.server, on a Windows runner matching the win_amd64 wheelhouse"
    requirement: "D-03"
    verification:
      - kind: other
        ref: "grep -q find-links .github/workflows/ci.yml — passes; job targets windows-latest / python 3.12 matching vendor/'s cp312-win_amd64 wheels"
        status: pass
      - kind: manual_procedural
        ref: "Job only truly executes on a GitHub-hosted windows-latest runner (not available in this environment) — could not run the exact CI job end-to-end locally"
        status: unknown
    human_judgment: true
    rationale: "Local macOS sandbox has no win_amd64 Python; the actual --no-index --find-links resolution against vendor/ can only be proven on the real windows-latest CI runner. Local validation confirmed the vendor/ wheelhouse itself is win_amd64-complete for the base install (pyyaml, pydantic, aiosqlite, pillow, fastmcp, mcp all present as win_amd64/py3-none-any wheels) and that an equivalent --no-index --find-links install succeeds when platform-matched wheels exist (verified base logic on macOS arm64 fails only due to platform mismatch, not a wheelhouse gap)."
  - id: D3
    description: "pixi CI job runs pixi install engine-free on a MATLAB-less runner and asserts matlabengine is absent from pixi.toml"
    requirement: "D-02"
    verification:
      - kind: other
        ref: "Ran the exact commands locally with the real pixi 0.72.2 binary: `pixi install` succeeded, `pixi run python -c \"from matlab_mcp.server import main\"` printed OK, and `grep -v '^\\s*#' pixi.toml | grep -qi matlabengine` found no live reference (only comments)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Real mathworks/matlab Docker image build is gated behind a MATLAB-license-available flag; docker compose config validates unconditionally"
    requirement: "D-04"
    verification:
      - kind: other
        ref: "grep -qi MATLAB_LICENSE_AVAILABLE .github/workflows/ci.yml && grep -q 'docker compose config' .github/workflows/ci.yml — both pass; locally ran `MLM_LICENSE_FILE=27000@ci-placeholder docker compose config` and `... -f docker-compose.test.yml config`, both exit 0"
        status: pass
    human_judgment: false
  - id: D5
    description: "conda-test-pypi published-wheel smoke re-homed onto pip (no longer depends on deprecated conda environment.yml)"
    verification:
      - kind: other
        ref: "python3 -c \"import yaml; d=yaml.safe_load(open('.github/workflows/ci.yml')); j=d['jobs']; assert 'pip-test-pypi' in j and 'conda-incubator' not in str(j['pip-test-pypi'])\" — passes"
        status: pass
    human_judgment: false

duration: 28min
completed: 2026-07-12
status: complete
---

# Phase 08 Plan 10: CI Drift Guard + Offline Smoke + Pixi Job + License-Gated Docker Build Summary

**Added four new/changed CI jobs (drift-guard, offline-smoke, pixi, gated docker) that continuously lock in every invariant this phase established — version agreement, air-gapped resolvability, engine-free pixi installs, and safe (never-unlicensed) Docker builds.**

## Performance

- **Duration:** 28 min
- **Started:** 2026-07-12T22:58:00Z
- **Completed:** 2026-07-12T23:26:25Z
- **Tasks:** 2 completed
- **Files modified:** 1 (`.github/workflows/ci.yml`)

## Accomplishments

- Added a `drift-guard` CI job that fails the build if the fastmcp version floor or project version string disagree across `pyproject.toml`, `requirements-lock.txt`, `CLAUDE.md`, and `install.bat` — proven to actually catch drift by injecting a stale `2.14.5` string into a scratch copy and confirming the guard's exit code flips to 1.
- Added an `offline-smoke` CI job (correctly targeted at `windows-latest`, not `ubuntu-latest`, after discovering the vendored wheelhouse is win_amd64-only) that installs `matlab-mcp-python` with `pip install --no-index --find-links vendor` in a fresh venv and imports `matlab_mcp.server`.
- Added a `pixi` CI job that installs pixi, runs `pixi install` on a MATLAB-less runner, asserts the server imports engine-free, and greps `pixi.toml` (comment-aware) to guarantee `matlabengine` never becomes a static dependency — validated against the real pixi 0.72.2 binary locally.
- Gated the real `mathworks/matlab` image build + pool-start smoke test in the `docker` job behind a new `vars.MATLAB_LICENSE_AVAILABLE` repository-variable check, while making `docker compose config` / `docker compose -f docker-compose.test.yml config` run unconditionally (verified locally with a placeholder `MLM_LICENSE_FILE` that satisfies the compose file's fail-fast guard without needing a real license).
- Re-homed the published-wheel smoke test off conda (`conda-test-pypi` → `pip-test-pypi`), now a plain `pip install matlab-mcp-python` + import + `matlab-mcp --help`; left `conda-test-dev` unchanged per the plan's explicit allowance.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the version-drift grep guard and the clean-venv offline smoke test jobs** - `a9e7e78` (feat)
2. **Task 2: Add the pixi engine-free job, gate the mathworks/matlab image build behind a license flag, and re-home the conda published-wheel smoke onto pip** - `1730bd8` (feat)

_No TDD tasks in this plan (CI-config-only, type=auto)._

## Files Created/Modified

- `.github/workflows/ci.yml` - Added `drift-guard`, `offline-smoke`, `pixi` jobs; renamed/re-homed `conda-test-pypi` → `pip-test-pypi`; gated the `docker` job's real image build+smoke steps behind `vars.MATLAB_LICENSE_AVAILABLE` with an unconditional `docker compose config` validation step added ahead of them.

## Decisions Made

- **offline-smoke targets `windows-latest`, not `ubuntu-latest`.** The plan text didn't specify an OS, but the environment note flagged this needs a Windows runner, and local inspection of `vendor/` confirmed every platform-specific wheel (`pillow`, `cffi`, `cryptography`, `pydantic_core`, `pywin32`, `rpds_py`, `watchfiles`, `websockets`) is `win_amd64`-only — a Linux runner cannot resolve `--no-index --find-links vendor`. Fixing this before committing was a Rule 1 auto-fix (the job as literally described in the plan text would have failed on CI).
- **`drift-guard` uses `sed` (POSIX BRE) instead of `grep -oP`.** Local testing surfaced that the interactive shell's `grep` is a wrapper around `ugrep`, masking that plain `/bin/bash` + BSD grep (macOS default) doesn't support `-P`. Since GitHub's `ubuntu-latest` runner *does* ship GNU grep, `-P` would have worked in the actual CI environment — but `sed` is fully portable across GNU/BSD and was verified end-to-end with `env -i /bin/bash` (no shell function shims), so it was used for robustness rather than relying on an environment-specific grep flavor.
- **`docker compose config` validation uses a placeholder `MLM_LICENSE_FILE=27000@ci-placeholder`.** `docker-compose.yml` has a fail-fast `${MLM_LICENSE_FILE:?...}` guard that fails `docker compose config` if the variable is unset at all — even for pure YAML-resolution validation. A non-functional placeholder satisfies the guard without ever attempting to contact a license server (nothing in the `config` subcommand starts a container).
- **Only the standalone `docker` job's build+run smoke is gated behind `MATLAB_LICENSE_AVAILABLE`; `remote-integration-test` is left untouched.** The plan explicitly said to keep `remote-integration-test` as-is because it runs the image in `--inspect` mode (engine-free, no license needed to *run*), and confirmed via `curl -I https://hub.docker.com/v2/repositories/mathworks/matlab/` (200 response) that the base image itself is a public, unauthenticated Docker Hub pull — building it doesn't require a license, only starting a real engine inside it does.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] offline-smoke job would have failed on ubuntu-latest**
- **Found during:** Task 1
- **Issue:** The plan's action text didn't pin an OS for the offline-smoke job. A first draft targeted `ubuntu-latest`, which fails immediately because `vendor/` contains only `win_amd64` wheels for every platform-specific dependency (confirmed by attempting `pip install --no-index --find-links vendor matlab-mcp-python` in a macOS venv, which failed on `pillow>=9.0.0` with "No matching distribution found").
- **Fix:** Changed `runs-on: ubuntu-latest` to `runs-on: windows-latest` and switched the install/import steps to PowerShell (`pwsh`) with Windows venv paths (`.\offline-venv\Scripts\pip.exe`, `.\offline-venv\Scripts\python.exe`).
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** Confirmed vendor/ is a complete win_amd64 wheelhouse for the base install by listing its contents (96 wheels, all `win_amd64`/`py3-none-any`/`any` tagged, none `linux`/`macosx`).
- **Committed in:** `a9e7e78` (part of Task 1 commit — this was fixed before the first commit, not a follow-up patch)

**2. [Rule 1 - Bug] `grep -oP` would silently behave differently across grep implementations**
- **Found during:** Task 1 (local validation of the drift-guard script)
- **Issue:** Initial draft used `grep -oP '...\K...'` for version extraction. Testing standalone (`env -i /bin/bash`, bypassing the interactive shell's `ugrep`-backed `grep` function wrapper) showed BSD grep 2.6.0-FreeBSD (the real `grep` binary underneath) doesn't support `-P`/`\K`, exiting 2. GNU grep on `ubuntu-latest` does support it, so the job as first drafted would likely have worked in CI — but relying on a GNU-specific extension without being able to prove it locally was a correctness risk worth removing before commit.
- **Fix:** Rewrote all four extraction/comparison expressions using `sed -n 's/.../\1/p'` (POSIX Basic Regular Expressions), which is portable across GNU and BSD sed/grep.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** Ran the exact extracted script with `env -i /bin/bash /tmp/drift_guard_extracted.sh` (real BSD grep/sed on this machine, no shell aliasing) — passed cleanly, and separately verified it correctly fails (exit 1) when `2.14.5` is reintroduced into a scratch copy of `CLAUDE.md`.
- **Committed in:** `a9e7e78` (part of Task 1 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs in the initial draft that would have produced an incorrect or environment-fragile CI job).
**Impact on plan:** Both fixes were necessary for the jobs to actually work as the plan's `must_haves` truths require (a Windows-targeted offline smoke test that resolves the win_amd64 wheelhouse; a drift guard that runs correctly regardless of grep flavor). No scope creep — both fixes stayed within `.github/workflows/ci.yml`, the plan's sole `files_modified` entry.

## Issues Encountered

None beyond the two auto-fixed items above.

## User Setup Required

None for CI to run in its default (unlicensed) mode. **Optional, for maintainers who want the licensed Docker build to actually run in CI:** set a repository variable `MATLAB_LICENSE_AVAILABLE=true` (Settings → Secrets and variables → Actions → Variables) on a self-hosted runner that has network access to a MathWorks network license manager (`MLM_LICENSE_FILE=port@host`). Until that variable is set, the `docker` job's real image build/run steps are skipped by design — only `docker compose config` validation runs.

## Next Phase Readiness

This is the final plan (08-10) of phase 08. All D-01 through D-04 requirements are now continuously enforced by CI:
- D-01 (version drift): `drift-guard` job.
- D-02 (pixi engine-free): `pixi` job.
- D-03 (offline resolvability): `offline-smoke` job.
- D-04 (license-gated Docker): gated `docker` job + unconditional compose-config validation.

No blockers. The two verification items marked `human_judgment: true` (D2's actual windows-latest CI run, and the eventual licensed Docker build on a self-hosted runner) can only be confirmed once this branch's CI actually executes on GitHub Actions infrastructure — both are environment-scoped limitations of local execution, not open implementation gaps.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-12*

## Self-Check: PASSED

- FOUND: `.github/workflows/ci.yml`
- FOUND: `.planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-10-SUMMARY.md`
- FOUND commit: `a9e7e78`
- FOUND commit: `1730bd8`
