# Roadmap: MATLAB MCP Server

## Milestones

- ✅ **v2.0** — Phases 1-6 (shipped 2026-04-03) — [Full details](milestones/v2.0-ROADMAP.md)

## Phases

<details>
<summary>✅ v2.0 (Phases 1-6) — SHIPPED 2026-04-03</summary>

- [x] Phase 1: FastMCP 3.0 Upgrade (2/2 plans) — completed 2026-04-01
- [x] Phase 2: Auth Config + Bearer Token Middleware (2/2 plans) — completed 2026-04-01
- [x] Phase 3: Streamable HTTP Transport + Session Routing (2/2 plans) — completed 2026-04-02
- [x] Phase 4: Human-in-the-Loop Approval (2/2 plans) — completed 2026-04-02
- [x] Phase 5: Windows 10 + Platform Hardening (2/2 plans) — completed 2026-04-02
- [x] Phase 6: Documentation + Agent Onboarding (2/2 plans) — completed 2026-04-03

</details>

### Phase 7: Fix all HIGH and MEDIUM issues from codebase review

**Goal:** Fix all HIGH and MEDIUM severity issues identified in the full codebase review — covering security (centralize validation, expand blocklist, fix injection vectors), pool/engine (resource leaks, timeout enforcement, race conditions), jobs/session (TOCTOU fixes, state machine guards, shutdown handling), server/config (deprecation fixes, Pydantic compat, YAML error handling), monitoring (query bounds, SQL limits, route dedup), and test quality (coverage gaps, flaky tests, shared fixtures).
**Requirements**: Codebase review findings (39 HIGH+MEDIUM issues)
**Depends on:** v2.0 (all 6 phases complete)
**Plans:** 7 plans

Plans:

- [x] 07-01-PLAN.md — Security: expand blocklist, fix empty-token auth, session ID sanitization
- [x] 07-02-PLAN.md — Security: centralize check_code in JobExecutor
- [x] 07-03-PLAN.md — Pool/Engine: release leak, start timeout, acquire race, workspace API
- [x] 07-04-PLAN.md — Jobs/Session: state machine guards, TOCTOU, background task tracking
- [x] 07-05-PLAN.md — Server/Config: deprecations, dead attrs, YAML errors, CORS
- [x] 07-06-PLAN.md — Monitoring: SQL limits, query clamping, path traversal, route dedup
- [x] 07-07-PLAN.md — Tests: async conversion, shared fixtures, scale-down coverage, assertions

### Phase 8: Friendly Win10 install (Pixi + Docker) + FastMCP 3.4.4

**Goal:** Make the Win10 install dead-simple and no-admin friendly, runnable via both **Pixi** (recommended desktop path) and **Docker** (Linux/server path), on the newest **FastMCP 3.4.4**, adopting the new-lib features that benefit this server. Core moves: (1) a shared `scripts/install_matlab_engine.py` that detects the local MATLAB release and pip-installs the matching **PyPI `matlabengine`** (primary), keeping the local `extern/engines` build only as an offline fallback — retiring `install.bat`'s fragile junction/PowerShell dance; (2) `pixi.toml` + committed `pixi.lock` with friendly tasks; (3) honest Docker `FROM mathworks/matlab` + network-license (`MLM_LICENSE_FILE`) compose, deleting the broken `python:slim` host-mount fiction; (4) bump fastmcp to `>=3.4.4,<4.0.0` everywhere and rebuild `vendor/`/lock/project-wheel to the 3.x closure + v1.5.0 — fixing the offline-runs-2.14.5/v1.4.1 drift left by Phase 1 — plus `update_vendor.bat` fixes (project wheel, matlabengine sdist, dedup) and CI drift-guard + offline smoke test; (5) adopt FastMCP 3.4.4 features F5 TimingMiddleware, F6 structured output (`ExecuteResult`/`CheckResult` + `ToolResult(is_error=True)`), F12 streamable-http default (keep `sse` alias); (6) cleanup: drop unused `plotly`, dedup `cryptography` wheel, reconcile version strings, deprecate `environment*.yml`/`requirements-lock.txt` in favor of `pixi.lock`. Air-gapped offline support is retained.

**Requirements**: Approved design spec `2026-07-12-friendly-win10-install-design.md` (in session scratchpad); 4 locked decisions — PyPI matlabengine + local-build fallback, full mathworks/matlab Docker, keep offline, adopt-now FastMCP features (F5/F6/F12).
**Depends on:** Phase 7 (complete)
**Plans:** 10 plans in 3 waves

Plans:

- [ ] 08-01-PLAN.md — WS1: shared MATLAB engine detection/install script (+ mocked-registry tests)
- [ ] 08-02-PLAN.md — WS4: bump fastmcp to 3.4.4 + drop plotly runtime dep (pyproject/CLAUDE.md)
- [ ] 08-03-PLAN.md — WS5-F5: TimingMiddleware (per-tool-call metrics) + create_server registration
- [ ] 08-04-PLAN.md — WS1: slim install.bat to call the shared engine script (drop junction/PowerShell)
- [ ] 08-05-PLAN.md — WS2: pixi.toml + committed pixi.lock + tasks + README quickstart
- [ ] 08-06-PLAN.md — WS5-F6: ExecuteResult/CheckResult structured output (schema-additive, wire-compat)
- [ ] 08-07-PLAN.md — WS3: rewrite Dockerfile/compose (mathworks/matlab + network license, streamablehttp)
- [ ] 08-08-PLAN.md — WS4: rebuild vendor to fastmcp 3.4.x closure + update_vendor fixes (offline)
- [ ] 08-09-PLAN.md — WS6: deprecate conda envs toward pixi + reconcile wiki version strings
- [ ] 08-10-PLAN.md — WS4/6: CI drift guard, offline smoke, pixi job, license-gated docker build
