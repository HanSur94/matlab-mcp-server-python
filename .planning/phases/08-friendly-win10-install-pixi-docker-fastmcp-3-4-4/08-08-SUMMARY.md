---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 08
subsystem: infra
tags: [pip, offline-install, vendor, wheelhouse, fastmcp, matlabengine, requirements-lock]

# Dependency graph
requires:
  - phase: 08-02
    provides: "pyproject.toml bumped to fastmcp>=3.4.4,<4.0.0, plotly dropped as a dependency"
provides:
  - "update_vendor.bat that builds the project wheel, fetches the matlabengine sdist, dedups cryptography, and fetches the pip/setuptools/wheel bootstrap wheels"
  - "requirements-lock.txt regenerated to the fastmcp 3.4.4 runtime+monitoring closure (plotly and the fastmcp-2.x Docket/CLI extras removed), deprecated in favor of pixi.lock"
  - "vendor/ wheelhouse rebuilt to that closure: fastmcp 3.4.4, matlab_mcp_python 1.5.0 project wheel, matlabengine 25.1.2 sdist, single deduped cryptography wheel"
affects: ["08-10"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "requirements-lock.txt is a pip-download-only artifact consumed exclusively by update_vendor.bat; pixi.lock is canonical for reproducible dev/CI environments"
    - "Windows-only transitive deps (colorama, pywin32, pywin32-ctypes) must be added explicitly to requirements-lock.txt because a same-platform pip resolve on macOS/Linux silently drops markers like platform_system=='Windows'"

key-files:
  created: []
  modified:
    - update_vendor.bat
    - requirements-lock.txt
    - vendor/ (96 files, full closure rebuild)

key-decisions:
  - "aiofile pinned to 3.9.0 (not the latest 3.11.1) because 3.10.0+ requires Python >=3.11 and would break the py3.10 leg of the win_amd64 download loop"
  - "rpds-py pinned to 0.30.0 (not the latest calendar-versioned 2026.6.3) because that release ships no cp310-win_amd64 wheel"
  - "matlabengine sdist vendored at 25.1.* (R2025a), matching the Dockerfile's default MATLAB_RELEASE ARG"
  - "cryptography dedup keeps the higher abi3 tag (cp39-abi3) via a generic 'sort descending, keep first' batch step rather than hardcoding a version number, so the script survives future PyPI wheel-tag changes"
  - "added pip/setuptools/wheel bootstrap wheels to update_vendor.bat's fetch list — install.bat's fully offline path self-upgrades pip via --no-index --find-links vendor, and these three were present in the old vendor/ but were never actually fetched by the old script (manually added at some point, silently unreproducible)"

requirements-completed: [D-03, D-04]

coverage:
  - id: D1
    description: "update_vendor.bat builds the project wheel (pip wheel .), fetches the matlabengine sdist via --no-binary :all:, and dedups redundant cryptography wheels"
    requirement: "D-03"
    verification:
      - kind: other
        ref: "grep -q 'pip wheel' update_vendor.bat && grep -q 'no-binary' update_vendor.bat && grep -qi matlabengine update_vendor.bat"
        status: pass
    human_judgment: false
  - id: D2
    description: "requirements-lock.txt carries a deprecation notice pointing to pixi.lock and reflects the fastmcp 3.4.4 closure (no plotly, no fastmcp 2.x, no Docket task-queue extras)"
    requirement: "D-04"
    verification:
      - kind: other
        ref: "grep -qiE 'deprecat|superseded|pixi.lock' requirements-lock.txt"
        status: pass
    human_judgment: false
  - id: D3
    description: "vendor/ wheelhouse rebuilt to the fastmcp 3.4.4 closure: exactly one cryptography wheel, no plotly, no fastmcp 2.x, project wheel + matlabengine sdist present"
    requirement: "D-03"
    verification:
      - kind: other
        ref: "test $(ls vendor/ | grep -ci '^cryptography-.*\\.whl$') = 1 && ! ls vendor/ | grep -qi '^plotly-' && ! ls vendor/ | grep -qi '^fastmcp-2\\.'"
        status: pass
      - kind: other
        ref: "pip download --no-index --find-links vendor --platform win_amd64 --python-version {310,311,312} --only-binary=:all: 'matlab-mcp-python[monitoring]' (full dependency resolution from vendor/ alone) — succeeded for all three Python versions"
        status: pass
  - id: D4
    description: "Real Windows install-time execution of the vendored win_amd64 wheels (pip install --no-index --find-links vendor matlab-mcp-python) — cannot execute on this macOS sandbox"
    verification: []
    human_judgment: true
    rationale: "win_amd64 wheels cannot be installed/imported on macOS; the offline smoke test is wired into CI in 08-10 and must run on a Windows runner (or equivalent) to close the loop."

# Metrics
duration: 55min
completed: 2026-07-13
status: complete
---

# Phase 08 Plan 08: Rebuild offline vendor/ to the FastMCP 3.4.4 closure Summary

**update_vendor.bat now builds the project wheel and fetches the matlabengine sdist with `--no-binary`; requirements-lock.txt and vendor/ are regenerated to the fastmcp 3.4.4 closure (plotly and the 2.x Docket/CLI extras dropped, cryptography deduped, pip/setuptools/wheel bootstrap wheels added), verified by a full offline dependency resolution from vendor/ alone across py3.10/3.11/3.12.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-12T23:10:57Z
- **Completed:** 2026-07-13T00:06Z (approx)
- **Tasks:** 2
- **Files modified:** update_vendor.bat, requirements-lock.txt, vendor/ (96 files after rebuild; 111 before)

## Accomplishments
- Fixed `update_vendor.bat`: added the project wheel build (`pip wheel .`), the matlabengine sdist fetch (`--no-binary :all:`, since the prior `--only-binary` loop silently skipped it), a generic cryptography dedup step, and — discovered as a Rule 2 gap during the rebuild — the pip/setuptools/wheel bootstrap wheels that `install.bat`'s air-gapped path needs but the old script never actually fetched.
- Regenerated `requirements-lock.txt` from a clean `pip install ".[monitoring]"` resolve against `fastmcp>=3.4.4,<4.0.0`: the fastmcp-2.x Docket/task-queue extras (redis, fakeredis, lupa, cronsim, pydocket, diskcache, py-key-value-shared) and the 2.x CLI stack (typer, shellingham, docutils) are gone; plotly and its narwhals dependency are gone; three Windows-only transitive deps (colorama, pywin32, pywin32-ctypes) were added explicitly since a same-platform pip resolve on macOS silently drops `platform_system=='Windows'`/`sys_platform=='win32'` markers.
- Rebuilt `vendor/` end-to-end by actually running the win_amd64/py310+311+312 download loop, building the project wheel, and fetching the matlabengine sdist — not by hand-editing file lists. 111 files (88M) -> 96 files (64M).
- Verified the closure is internally consistent with a real, network-backed check: `pip download --no-index --find-links vendor --platform win_amd64 --python-version {310,311,312} --only-binary=:all: matlab-mcp-python[monitoring]` performs a **full dependency resolution using only vendor/ as the source** and succeeds for all three Python versions (73 packages resolved each time, zero unresolved requirements).

## Task Commits

1. **Task 1: Extend update_vendor.bat and deprecate requirements-lock.txt** - `f50705e` (feat)
2. **Task 2: Regenerate the vendor wheelhouse to the fastmcp 3.4.x closure** - `1c01821` (feat)

_Note: requirements-lock.txt received two further corrections (aiofile, rpds-py version pins) inside the Task 2 commit, discovered while actually running the download loop against the win_amd64 target — see Deviations below._

## Files Created/Modified
- `update_vendor.bat` - Adds project wheel build, matlabengine sdist fetch (`--no-binary`), cryptography dedup, and pip/setuptools/wheel bootstrap fetch
- `requirements-lock.txt` - Regenerated to the fastmcp 3.4.4 closure with a deprecation notice pointing to pixi.lock
- `vendor/` - 96 files: full win_amd64 closure (py310/311/312) + project wheel + matlabengine sdist, deduped

## Decisions Made
- Used a fresh `pip install ".[monitoring]"` resolve on this macOS sandbox (permitted per the plan's environment note) rather than hand-editing the old lock, then cross-checked the fastmcp/pydantic/mcp/starlette versions against the already-resolved `.pixi/envs/dev` (via pixi.lock) — both independent resolves agreed (fastmcp==3.4.4, cryptography==49.0.0, etc.), giving confidence in the closure.
- `aiofile` pinned to 3.9.0 and `rpds-py` pinned to 0.30.0 instead of their absolute latest releases, because the latest releases of each dropped Python 3.10 support (aiofile 3.10.0+ requires >=3.11; rpds-py's calendar-versioned 2026.6.3/2026.5.1 ship no cp310-win_amd64 wheel). Since `pyproject.toml` floors at Python 3.10, the lock must stay resolvable there too.
- Added `colorama`, `pywin32`, and `pywin32-ctypes` as explicit top-level entries in requirements-lock.txt. These are real, non-optional Windows-conditional dependencies (click requires colorama on `platform_system=='Windows'`; mcp 1.28.1 requires `pywin32>=310` unconditionally on `sys_platform=='win32'`; keyring requires `pywin32-ctypes` on `sys_platform=='win32'`) that a `pip download --platform win_amd64` run from macOS/Linux cannot discover on its own, because PEP 508 marker evaluation uses the *host* environment, not the `--platform` target. Verified empirically: `pip download click --platform win_amd64 ...` from this macOS sandbox does NOT pull colorama.
- Cryptography dedup logic in update_vendor.bat is written generically (`dir /b /o-n`, keep first, delete rest) rather than hardcoding a specific ABI tag like the plan's example (`cp38-abi3`) — the actual current release (cryptography 49.0.0) ships `cp39-abi3` now, not `cp38-abi3`, confirming the hardcoded-tag approach from the plan text would already be stale on day one.
- matlabengine sdist vendored at version 25.1.2 (the `25.1.*` release map entry for R2025a), matching the Dockerfile's `ARG MATLAB_RELEASE=r2025a` default from the 08-07 plan.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] requirements-lock.txt's initial aiofile/rpds-py pins broke the py3.10 download leg**
- **Found during:** Task 2, first run of the actual win_amd64/py310 download loop
- **Issue:** The initial requirements-lock.txt regeneration (Task 1's commit) pinned `aiofile==3.11.1` and `rpds-py==2026.6.3`, both resolved from a py3.11 host environment. `aiofile>=3.10.0` requires Python >=3.11, and `rpds-py` dropped its cp310-win_amd64 wheel starting with its 2026.x calendar-versioned releases — the py3.10 leg of `pip download -r requirements-lock.txt --platform win_amd64 --python-version 310` failed outright.
- **Fix:** Re-pinned to `aiofile==3.9.0` (last release supporting Python 3.10) and `rpds-py==0.30.0` (last release shipping a cp310-win_amd64 wheel), both still satisfying every other package's version constraints on these two libraries.
- **Files modified:** requirements-lock.txt
- **Verification:** All three python-version legs of the win_amd64 download loop now succeed with exit code 0; a full offline dependency resolution from vendor/ alone also succeeds for py310/311/312.
- **Committed in:** 1c01821 (Task 2 commit)

**2. [Rule 2 - Missing Critical] update_vendor.bat never fetched the pip/setuptools/wheel bootstrap wheels install.bat needs**
- **Found during:** Task 2, while diffing the old vendor/ contents against the freshly rebuilt closure
- **Issue:** `install.bat` runs `python -m pip install --upgrade pip setuptools wheel --no-index --find-links vendor` as its first offline-bootstrap step (line 225), and the old vendor/ did contain pip-26.0.1, setuptools-82.0.1, and wheel-0.46.3 wheels — but neither the old nor my first-draft update_vendor.bat ever fetched them; they must have been added by hand at some point. A straight rebuild driven only by requirements-lock.txt + project wheel + matlabengine sdist would have silently dropped this and broken the air-gapped bootstrap path.
- **Fix:** Added an explicit `pip download pip setuptools wheel --only-binary=:all:` step to update_vendor.bat and re-fetched them into vendor/ (now pip-26.1.2, setuptools-83.0.0, wheel-0.47.0).
- **Files modified:** update_vendor.bat, vendor/
- **Verification:** `ls vendor/ | grep -iE '^(pip|setuptools|wheel)-'` shows all three present; install.bat's bootstrap step (line 225) has its required inputs.
- **Committed in:** 1c01821 (Task 2 commit)

**3. [Rule 1 - Bug] Old vendor/ was silently missing psutil and watchfiles despite both being in requirements-lock.txt**
- **Found during:** Task 2, diffing old vs. new vendor package lists
- **Issue:** `psutil` and `watchfiles` are both required by the `monitoring` extra (pyproject.toml) and were both listed in the *old* requirements-lock.txt, but neither wheel was present in the old vendor/ directory — meaning any fully offline install with `pip install --no-index --find-links vendor "matlab-mcp-python[monitoring]"` would have failed to resolve, silently breaking the monitoring dashboard for air-gapped users. Root cause unclear (likely an incomplete prior manual vendor update), but it predates this plan.
- **Fix:** The full rebuild in Task 2 naturally re-fetches every entry in requirements-lock.txt, including psutil-7.2.2 and watchfiles-1.2.0 (3 per-Python-version wheels each), closing this gap.
- **Files modified:** vendor/
- **Verification:** `ls vendor/ | grep -iE "psutil|watchfiles"` now lists all expected wheels; the offline dependency resolution check (`pip download --no-index --find-links vendor ... matlab-mcp-python[monitoring]`) includes psutil and watchfiles in its "Successfully downloaded" list for all three Python versions.
- **Committed in:** 1c01821 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 bug in the just-regenerated lock, 1 missing critical bootstrap dependency, 1 pre-existing bug in the old vendor bundle)
**Impact on plan:** All three were necessary corrections directly on the plan's critical path (a broken lock cannot drive a correct vendor rebuild; a vendor missing pip/setuptools/wheel or psutil/watchfiles is not actually offline-installable). No scope creep — no new features, transports, or unrelated packages were touched.

## Issues Encountered

- **Cross-platform marker evaluation gap (informational, not a bug in this deliverable):** `pip download --platform win_amd64 ...` run from macOS/Linux evaluates PEP 508 environment markers (e.g. `platform_system == 'Windows'`) against the *host* OS, not the target platform. This is a pip limitation, not something update_vendor.bat can work around from within the script — it only matters when *regenerating* requirements-lock.txt from a non-Windows machine (as was done here), which is why colorama/pywin32/pywin32-ctypes had to be added explicitly and are called out in a comment at the top of requirements-lock.txt for the next person who regenerates it. Running update_vendor.bat itself on an actual Windows machine (its documented use case) is unaffected — the download loop just consumes the fixed requirements-lock.txt as-is.
- **Honest scope of the offline smoke test:** `pip install --no-index --find-links vendor matlab-mcp-python` cannot execute on this macOS sandbox (the vendored wheels are win_amd64-tagged; pip correctly refuses to install foreign-platform wheels via plain `install`). What *was* run and passed: a full offline **dependency resolution** (`pip download --no-index --find-links vendor --platform win_amd64 --python-version {310,311,312} --only-binary=:all: matlab-mcp-python[monitoring]`), which proves the wheel *set* is complete and mutually consistent for all three target Python versions, but does not prove the wheels actually import/run on Windows. The real install-and-import smoke test is out of scope for this sandbox and is wired into CI by plan 08-10, which must run on a Windows (or win_amd64-capable) runner to close the loop.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `vendor/` and `update_vendor.bat` are ready for 08-10's CI offline smoke test (`pip install --no-index --find-links vendor`), which will be the first real win_amd64 execution of these wheels.
- `requirements-lock.txt`'s deprecation notice and the version-drift facts here (fastmcp 2.14.5 -> 3.4.4 gone from vendor) are inputs for 08-10's version-drift CI guard.
- No blockers identified for 08-10.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: update_vendor.bat
- FOUND: requirements-lock.txt
- FOUND: vendor/
- FOUND: f50705e (Task 1 commit)
- FOUND: 1c01821 (Task 2 commit)
