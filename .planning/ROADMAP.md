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
- [ ] 07-01-PLAN.md — Security: expand blocklist, fix empty-token auth, session ID sanitization
- [ ] 07-02-PLAN.md — Security: centralize check_code in JobExecutor
- [ ] 07-03-PLAN.md — Pool/Engine: release leak, start timeout, acquire race, workspace API
- [ ] 07-04-PLAN.md — Jobs/Session: state machine guards, TOCTOU, background task tracking
- [ ] 07-05-PLAN.md — Server/Config: deprecations, dead attrs, YAML errors, CORS
- [x] 07-06-PLAN.md — Monitoring: SQL limits, query clamping, path traversal, route dedup
- [ ] 07-07-PLAN.md — Tests: async conversion, shared fixtures, scale-down coverage, assertions
