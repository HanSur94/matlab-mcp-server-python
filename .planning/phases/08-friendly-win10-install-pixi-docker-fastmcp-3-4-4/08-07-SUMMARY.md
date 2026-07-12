---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 07
subsystem: infra
tags: [docker, docker-compose, mathworks-matlab, matlabengine, network-license, streamablehttp, healthcheck]

# Dependency graph
requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
    provides: "pyproject-driven fastmcp 3.4.x dependency closure (08-02) that the Dockerfile now installs as the single source of truth"
provides:
  - "Honest mathworks/matlab-based Dockerfile with matched matlabengine pin"
  - "Network-license docker-compose.yml (required MLM_LICENSE_FILE, shm_size, capped engines)"
  - "docker-compose.test.yml aligned to the new image for CI remote-integration testing"
affects: [08-10, docker-deployment, ci]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Docker base image matches the actual runtime dependency (mathworks/matlab) instead of a slim base with a fictional bind-mount"
    - "matlabengine version pin is coupled to MATLAB_RELEASE build ARG via a documented version map"
    - "Container installs the project via pyproject extras (single source of truth) instead of hardcoded pip pins in the Dockerfile"

key-files:
  created: []
  modified:
    - Dockerfile
    - docker-compose.yml
    - docker-compose.test.yml

key-decisions:
  - "Healthcheck targets :8765/health (main MCP app port), not :8766 — confirmed against server.py that register_monitoring_routes() mounts /health on the main FastMCP app only for sse/streamablehttp transports; the 8766 monitoring server is stdio-only and does not run under the streamablehttp default"
  - "docker-compose.test.yml python/pip invocations fixed to python3/pip3 since the mathworks/matlab base only provides the python3 toolchain (apt-installed), not bare python/pip symlinks"

requirements-completed: [D-02, D-04]

coverage:
  - id: D1
    description: "Dockerfile rebuilt FROM mathworks/matlab with matched matlabengine, pyproject-driven install, USER matlab, streamablehttp default, and healthcheck on the correct port"
    requirement: "D-02"
    verification:
      - kind: unit
        ref: "grep -q mathworks/matlab Dockerfile && grep -q matlabengine== Dockerfile && grep -q 'USER matlab' Dockerfile && grep -q streamablehttp Dockerfile && ! grep -q python:3.12-slim Dockerfile && ! grep -q 8766/health Dockerfile"
        status: pass
    human_judgment: false
  - id: D2
    description: "docker-compose.yml requires MLM_LICENSE_FILE, sets shm_size and POOL_MAX_ENGINES=2, deletes the host-MATLAB bind-mount fiction; docker-compose.test.yml aligned to the new image"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "docker compose config (with MLM_LICENSE_FILE set) && docker compose -f docker-compose.test.yml config"
        status: pass
    human_judgment: false
  - id: D3
    description: "Actual mathworks/matlab image build and MATLAB-engine runtime behavior (license-gated; cannot be built/run on this macOS host without a MATLAB license and Linux Docker host)"
    verification: []
    human_judgment: true
    rationale: "Requires a multi-GB MathWorks base image and a real/network MATLAB license to build and start_matlab() — gated behind CI's MATLAB-license-available flag and manual verification per 08-VALIDATION.md; not exercisable in this execution environment"

# Metrics
duration: 4min
completed: 2026-07-13
status: complete
---

# Phase 08 Plan 07: Docker rewrite to honest mathworks/matlab + network license Summary

**Replaced the fictional python:slim + host-MATLAB-bind-mount Docker story with a real FROM mathworks/matlab build using a network license manager, a release-matched matlabengine pin, pyproject-driven installs, and a healthcheck corrected to the port that actually serves /health under the streamablehttp default.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-13T00:50:00+02:00 (approx.)
- **Completed:** 2026-07-13T00:54:26+02:00
- **Tasks:** 2/2 completed
- **Files modified:** 3 (Dockerfile, docker-compose.yml, docker-compose.test.yml)

## Accomplishments
- Dockerfile now builds `FROM mathworks/matlab:${MATLAB_RELEASE}` (default `r2025a`), pins `matlabengine==25.1.*` to match the release, installs the project via `pip3 install ".[monitoring]"` (pyproject is the single source of truth — no hardcoded fastmcp/plotly pins), drops to `USER matlab`, and defaults `CMD` to `--transport streamablehttp` (F12).
- Healthcheck corrected: confirmed via `src/matlab_mcp/server.py` (lines ~408-417) that `register_monitoring_routes()` mounts `/health` on the **main MCP app** for `sse`/`streamablehttp` transports, while the separate uvicorn monitoring server on `config.monitoring.http_port` (8766) only starts for the `stdio` transport (lines ~259-283). The Dockerfile healthcheck now targets `http://localhost:8765/health`, not 8766.
- docker-compose.yml rewritten: build arg `MATLAB_RELEASE: r2025a`, `shm_size: "512m"`, `MLM_LICENSE_FILE` required via `${MLM_LICENSE_FILE:?set MLM_LICENSE_FILE=port@host}` fail-fast interpolation, `MATLAB_MCP_SERVER_TRANSPORT=streamablehttp`, `MATLAB_MCP_POOL_MAX_ENGINES=2` (1 engine = 1 license seat). Deleted the host-MATLAB bind-mount comment lines and the `MATLAB_MCP_POOL_MATLAB_ROOT` hint — that path is unsupported across the Docker Desktop boundary and was fiction.
- docker-compose.test.yml aligned to the new image: added explicit `MATLAB_RELEASE` build arg for the server service, kept the engine-free `--inspect` mode (generic CI has no MATLAB license), and fixed `python`/`pip` invocations to `python3`/`pip3` (the mathworks/matlab base only provides the apt-installed python3 toolchain, not bare symlinks).

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite the Dockerfile** - `42c5d1b` (feat)
2. **Task 2: Rewrite docker-compose.yml and align docker-compose.test.yml** - `0c0714a` (feat)

**Plan metadata:** pending final metadata commit (STATE.md/ROADMAP.md owned by orchestrator per objective)

## Files Created/Modified
- `Dockerfile` - `FROM mathworks/matlab`, matched matlabengine pin, pyproject install, USER matlab, streamablehttp default, corrected healthcheck port
- `docker-compose.yml` - required MLM_LICENSE_FILE, shm_size 512m, POOL_MAX_ENGINES=2, bind-mount fiction removed
- `docker-compose.test.yml` - aligned to the new image (build arg, python3/pip3 fixes), unchanged engine-free CI story

## Decisions Made
- Healthcheck port: 8765 (main app), confirmed against `server.py`/`dashboard.py` rather than trusting the RESEARCH.md draft's `:8766/health`, per the plan's explicit correction.
- Kept `docker-compose.test.yml`'s `--inspect` engine-free CI path unchanged in spirit (no MATLAB license available in generic CI); only fixed the base-image-driven `python`/`pip` command breakage and added the explicit build arg.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed python/pip invocations in docker-compose.test.yml**
- **Found during:** Task 2
- **Issue:** The mathworks/matlab base image (via `apt-get install python3 python3-pip python3-venv` in the new Dockerfile) provides `python3`/`pip3` binaries but not bare `python`/`pip` symlinks. `docker-compose.test.yml`'s healthcheck and client entrypoint used bare `python`/`pip`, which would fail once the base image changed from `python:3.12-slim` (which does provide `python`/`pip`) to `mathworks/matlab`.
- **Fix:** Changed the server healthcheck test and the client entrypoint command to use `python3`/`pip3`.
- **Files modified:** `docker-compose.test.yml`
- **Verification:** `docker compose -f docker-compose.test.yml config` validates the YAML/interpolation; actual command execution is gated behind CI building the real image (license-gated).
- **Committed in:** `0c0714a` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug directly caused by the base-image switch in this plan's own Task 1)
**Impact on plan:** Necessary for correctness given the base image change; no scope creep — confined to the file already in scope for Task 2.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required by this plan. Users deploying via Docker must supply `MLM_LICENSE_FILE=port@host` at `docker compose up` time (documented via the compose file's fail-fast `:?` message); this is expected end-user configuration, not a setup step this plan performs.

## Verification Performed

Both compose files were validated with the real `docker` CLI (v5.1.3) present in this environment:

```
$ MLM_LICENSE_FILE=27000@license.example.com docker compose config
# ... resolves cleanly: build.args.MATLAB_RELEASE=r2025a, shm_size: "536870912",
#     environment.MLM_LICENSE_FILE=27000@license.example.com,
#     environment.MATLAB_MCP_POOL_MAX_ENGINES="2", ports 8765:8765,
#     no "opt/matlab" bind-mount volumes present

$ unset MLM_LICENSE_FILE; docker compose config
error while interpolating services.matlab-mcp.environment.[]: required variable
MLM_LICENSE_FILE is missing a value: set MLM_LICENSE_FILE=port@host
# confirms the fail-fast guard actually fires when the license var is absent

$ docker compose -f docker-compose.test.yml config
# resolves cleanly: build.args.MATLAB_RELEASE=r2025a on the server service,
# healthcheck test uses python3, client entrypoint uses pip3/python3
```

Static grep checks (per plan's `<verify>` blocks) also confirmed:
- `Dockerfile`: contains `mathworks/matlab`, `matlabengine==`, `USER matlab`, `streamablehttp`; does NOT contain `python:3.12-slim` or `8766/health`.
- `docker-compose.yml`: contains `MLM_LICENSE_FILE`, `shm_size`; does NOT contain `opt/matlab` (case-insensitive).

**Not performed in this environment (by design, per the plan's environment note):** actual `docker build`/`docker run` of the `mathworks/matlab`-based image. This host cannot build the multi-GB MathWorks base image or exercise a real/network MATLAB license. That verification is gated behind CI's MATLAB-license-available flag (08-10) and manual verification per `08-VALIDATION.md` — consistent with the plan's own verification section ("Image build gated behind MATLAB_LICENSE_AVAILABLE in CI (08-10)").

## Next Phase Readiness
The Docker deployment path now reflects the real, honest architecture (mathworks/matlab + network license). 08-10 (CI) can build on the `MATLAB_RELEASE` build arg and the `MLM_LICENSE_FILE`-gated compose file to implement the license-available CI flag referenced in this plan's verification section. No blockers.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: Dockerfile
- FOUND: docker-compose.yml
- FOUND: docker-compose.test.yml
- FOUND: .planning/phases/08-friendly-win10-install-pixi-docker-fastmcp-3-4-4/08-07-SUMMARY.md
- FOUND commit: 42c5d1b
- FOUND commit: 0c0714a
