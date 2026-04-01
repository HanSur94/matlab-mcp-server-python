---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: milestone
status: ready_for_verification
stopped_at: Completed 03-02-PLAN.md (streamablehttp transport and session routing)
last_updated: "2026-04-01T21:27:00.000Z"
last_activity: 2026-04-01
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 6
  completed_plans: 5
  percent: 67
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-01)

**Core value:** Any MCP-compatible coding agent can connect to MATLAB and run code securely — with minimal setup, proper authentication, and production-grade reliability.
**Current focus:** Phase 03 — streamable-http-transport-session-routing

## Current Position

Phase: 03 (streamable-http-transport-session-routing) — EXECUTING
Plan: 2 of 2
Status: Phase complete — ready for verification
Last activity: 2026-04-01

Progress: [███████░░░] 67%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 4 | 2 tasks | 4 files |
| Phase 01 P02 | 8 | 2 tasks | 2 files |
| Phase 02 P01 | 133 | 1 tasks | 3 files |
| Phase 02 P02 | 600 | 2 tasks | 4 files |
| Phase 03 P01 | 1 | 1 tasks | 2 files |
| Phase 03 P02 | 6 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Token-in-header auth over OAuth: Simple, works with all agents, no redirect flows needed
- FastMCP 3.0 upgrade: Gates all auth, transport, and HITL APIs — must be first
- Win10 no-admin as hard constraint: Default bind to 127.0.0.1 to avoid Firewall UAC
- [Phase 01]: Use await mcp.list_tools() instead of private _tool_manager.get_tools() for tool listing in tests (FastMCP 3.2.0 public API)
- [Phase 01]: Add show_banner=False to stdio run() call to prevent FastMCP 3.x startup banner from corrupting MCP stdio protocol stream
- [Phase 01]: Keep create_monitoring_app() intact alongside register_monitoring_routes() for test compatibility
- [Phase 01]: Use @mcp.custom_route() for monitoring routes with FileResponse static handler and path-traversal protection
- [Phase 02]: Pure ASGI class for BearerAuthMiddleware (not BaseHTTPMiddleware) to avoid Starlette streaming double-send bug
- [Phase 02]: Token read at middleware __init__ time from MATLAB_MCP_AUTH_TOKEN env var, not at module import or per-request
- [Phase 02]: hmac.compare_digest used for constant-time token comparison to prevent timing oracle attacks
- [Phase 02]: Middleware list order: BearerAuthMiddleware outermost, CORSMiddleware inner — auth checked before CORS headers
- [Phase 02]: _warn_if_token_in_config fires on raw YAML before env overrides to detect config file leaks
- [Phase 03]: No changes to _apply_env_overrides needed — existing bool coercion handles stateless_http automatically
- [Phase 03]: client_id fallback applies to both SSE and streamablehttp (both are HTTP transports)
- [Phase 03]: SSE deprecation warning placed in startup banner before server.run() for visibility
- [Phase 03]: config value 'streamablehttp' maps to FastMCP 'streamable-http' in server.run() call
- [Phase 03]: stateless_http only forwarded for streamablehttp; NOT passed to SSE (FastMCP raises ValueError)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3: `ctx.session_id` stability under streamable HTTP is a known open issue (#956). Needs Codex CLI end-to-end validation before phase is done. Mitigation: fall back to `ctx.client_id` when `ctx.session_id` is None.
- Phase 5: Windows 10 non-admin CI environment may need a dedicated VM or non-admin test account if GitHub Actions Windows runners run as admin.

## Session Continuity

Last session: 2026-04-01T21:27:00.000Z
Stopped at: Completed 03-02-PLAN.md (streamablehttp transport and session routing)
Resume file: None
