# Project Research Summary

**Project:** MATLAB MCP Server v2.0 — FastMCP 3.x Upgrade + Authentication
**Domain:** Production MCP server — Python, AI agent connectivity, bearer token auth
**Researched:** 2026-04-01
**Confidence:** HIGH

## Executive Summary

This project is a targeted upgrade of an already-working MATLAB MCP server. The core motivation is concrete: Codex CLI fails to connect because it does not support the legacy SSE transport (only streamable HTTP), and the current server has no real authentication — only a boolean flag that provides zero actual security. The recommended path is a FastMCP 2.x → 3.x upgrade that unlocks built-in auth and streamable HTTP transport in one coordinated change. All other server components (engine pool, session management, job execution, monitoring) are unaffected by this migration and should not be touched.

The recommended approach is: upgrade FastMCP to 3.2.0, wire `StaticTokenVerifier` (or `JWTVerifier` with HS256) for bearer token auth on HTTP transports via `BearerTokenMiddleware`, add streamable HTTP as the primary remote transport at `/mcp`, keep SSE for backward compatibility, and add a `--generate-token` CLI flag to eliminate onboarding friction. The entire auth change is confined to a new `auth/` package and small additions to `config.py` and `server.py`. Existing stdio deployments and the full downstream layer (engine pool, session manager, tools) are fully unaffected.

The two key risks are: (1) silent FastMCP 3.0 breaking changes — constructor kwargs that were deprecated in 2.x now raise `TypeError` in 3.x, and several methods were renamed or made async — and (2) Windows 10 no-admin complications (Windows Firewall blocks inbound connections from remote agents; MATLAB engine startup can hang on network-mapped drives). Both risks are well-understood and have documented mitigations. Migrating in disciplined phases (config → auth middleware → FastMCP upgrade → transport wiring → integration/hardening) eliminates the risk of breaking the working server mid-migration.

---

## Key Findings

### Recommended Stack

The stack change is minimal: the only required `pyproject.toml` change is the FastMCP pin from `fastmcp>=2.0.0,<3.0.0` to `fastmcp>=3.2.0,<4.0.0`. FastMCP 3.2.0 (released 2026-02-18, GA stable) pulls `authlib>=1.6.5` transitively — already present in the lockfile at 1.6.9 — so no new packages are needed. All other dependencies (uvicorn 0.42.0, starlette 0.52.1, pydantic 2.12.5, aiosqlite, plotly, Pillow, psutil) are unchanged and compatible.

**Core technologies:**
- **FastMCP 3.2.0**: MCP server framework — provides `StaticTokenVerifier`, `JWTVerifier`, streamable HTTP transport, `@mcp.custom_route()`, and the `http_app(middleware=[...])` ASGI hook needed for auth injection
- **BearerTokenMiddleware (custom, Starlette `BaseHTTPMiddleware`)**: HTTP-level auth enforcement — validates `Authorization: Bearer <token>` before FastMCP processes any MCP message; bypassed for stdio
- **authlib >=1.6.5** (transitive): JWT/token handling — pulled by FastMCP 3.x, no manual dependency addition needed
- **uvicorn 0.42.0**: ASGI server — used directly via `uvicorn.run(app, ...)` when auth is enabled (because `mcp.run()` does not expose a middleware injection point)

**Required code changes** (beyond pyproject.toml):
- `from fastmcp.server.context import Context` → `from fastmcp import Context` (import removed in 3.x)
- `mcp._additional_http_routes.append(...)` → `@mcp.custom_route()` or Starlette app wrapping
- `transport: Literal["stdio", "sse"]` → add `"http"` in `config.py`
- `_get_session_id()` must treat `"http"` the same as `"sse"`
- Any `get_tools()` / `get_resources()` calls → `list_tools()` / `list_resources()`

### Expected Features

**Must have (table stakes) — v2.0 Core:**
- FastMCP 3.0 upgrade — gate for all other v2.0 features
- Streamable HTTP transport at `/mcp` — Codex CLI only supports this; SSE gives a 404
- Bearer token auth via `MCP_AUTH_TOKEN` env var — solves the direct Codex CLI auth failure
- Token rejection returns HTTP 401 with `WWW-Authenticate` header — agents expect exactly 401, not 403 or 500
- `--generate-token` CLI helper — eliminates the #1 onboarding friction point
- Backward compatibility for stdio (zero change) and SSE (keep running)

**Should have (competitive) — v2.0 Polish:**
- Per-tool scope enforcement (`execute` vs `admin`) — security posture for shared deployments
- Stateless HTTP mode (`stateless_http=True`) — enables multi-instance / corporate cluster use
- Windows 10 no-admin deployment guide and default loopback binding — validated and documented

**Defer to v2.1+:**
- Token rotation without server restart — conflicts with static verifier; no agent use case blocked
- Agent-readable 401 JSON body — UX polish, not a connectivity requirement
- Full OAuth 2.1 / PKCE — explicitly out of scope; incompatible with CLI agent flows

**Anti-features to avoid:**
- Full OAuth 2.1 — requires browser redirect, incompatible with CLI agents, overkill for internal use
- Per-user MATLAB workspace mapped to OAuth identity — way beyond v2 scope
- GUI token management dashboard — agents use env vars, not dashboards
- mTLS — coding agents do not support client certificates

### Architecture Approach

The architecture change is deliberately shallow: a new `auth/` package containing `BearerTokenMiddleware` is added, `config.py` gains `auth_enabled` and `auth_tokens` fields in `SecurityConfig`, and `server.py` gains the HTTP transport run path. Everything below the transport boundary — `MatlabMCPServer`, `SessionManager`, `EnginePoolManager`, `JobExecutor`, `SecurityValidator`, and the monitoring layer — is completely unchanged. Auth is enforced at the Starlette middleware layer before FastMCP processes any MCP message; it never flows into business logic.

**Major components and their change status:**
1. **`BearerTokenMiddleware`** (new) — validates `Authorization: Bearer <token>` on every HTTP/SSE request; exempt paths bypass it (health, dashboard)
2. **`server.py / create_server()`** (modified) — FastMCP 3.0 construction, adds HTTP transport path, wires `BearerTokenMiddleware` into `mcp.http_app(middleware=[...])`
3. **`config.py / SecurityConfig`** (modified) — adds `auth_enabled: bool` and `auth_tokens: List[str]` with backward-compatible defaults
4. **`config.py / ServerConfig`** (modified) — adds `"http"` as valid transport literal
5. **All downstream layers** (unchanged) — `MatlabMCPServer`, `SessionManager`, `EnginePoolManager`, `JobExecutor`, `SecurityValidator`, monitoring

**Key architectural constraint:** `mcp.run(transport="http")` does not expose middleware injection. When auth is enabled, use `app = mcp.http_app(middleware=[...])` + `uvicorn.run(app, ...)` instead. The codebase already uses this pattern for the monitoring app in SSE mode.

### Critical Pitfalls

1. **FastMCP 3.0 constructor kwargs raise TypeError on startup** — audit every `FastMCP(...)` call before upgrading; move `host`, `port`, `log_level`, `debug`, `sse_path`, `stateless_http` to `mcp.run()` or `http_app()`. Failure mode: server never starts after upgrade.

2. **`ctx.get_state()` / `ctx.set_state()` are now async — silent wrong behavior without await** — run `grep -r "ctx\.set_state\|ctx\.get_state"` across all tool files; add `await` to every call. No exception is raised; tools silently return `None`.

3. **Bearer token committed to git via config.yaml** — never read tokens from `config.yaml`; use only `MATLAB_MCP_AUTH_TOKEN` env var. Add a startup check that warns if a token value appears in config. Add to `.gitignore` any `.env` files.

4. **Windows Firewall blocks inbound connections without admin** — default bind address must be `127.0.0.1` (loopback), not `0.0.0.0`. Remote access requires an admin-created firewall rule; document the PowerShell one-liner. For the primary use case (co-located agent + server), loopback binding avoids this entirely.

5. **Codex CLI only supports streamable HTTP, not SSE** — the motivating bug. Do not debug Codex CLI SSE connectivity; it is a known Codex limitation. Implement streamable HTTP at `/mcp` as the primary new transport.

6. **`_get_session_id()` must be broadened to include `"http"` transport** — without this, HTTP-transport requests fall back to the shared `"default"` session, mixing MATLAB workspaces across agents. Verify `ctx.session_id` is non-None and stable across multiple calls in the same session before shipping.

---

## Implications for Roadmap

Based on the dependency graph in FEATURES.md and the build order in ARCHITECTURE.md, four well-defined phases emerge. Each phase is independently testable and has a clear definition of done.

### Phase 1: FastMCP 3.0 Upgrade + Breaking Change Audit

**Rationale:** Everything else in v2.0 depends on FastMCP 3.x APIs (`StaticTokenVerifier`, `http_app(middleware=[...])`, `@mcp.custom_route()`). This must be first. The upgrade is a concrete checklist of known breaking changes — all well-documented — making it low uncertainty.

**Delivers:** A working FastMCP 3.x server that passes all existing tests; no behavioral change visible to end users.

**Addresses:** All FastMCP 3.0 migration pitfalls (Pitfalls 1, 2, 3, 7, 9, 10 from PITFALLS.md).

**Avoids:** Decorator return value breakage (Pitfall 10), `get_tools()` → `list_tools()` regressions (Pitfall 2), silent async state bugs (Pitfall 3).

**Checklist before phase is done:**
- `FastMCP(...)` constructor has no transport/runtime kwargs
- `from fastmcp import Context` import path updated
- `get_tools()` → `list_tools()` everywhere
- `mcp._additional_http_routes` → `@mcp.custom_route()` or Starlette wrapping
- All existing tests pass under FastMCP 3.2.0

**Research flag:** Standard patterns — FastMCP 3.0 upgrade guide is comprehensive and HIGH confidence. No additional research needed during planning.

---

### Phase 2: Auth Config + BearerTokenMiddleware

**Rationale:** Config changes have no external dependencies (Phase A in ARCHITECTURE.md build order). Auth middleware depends only on config. Establishing the env-var-only token pattern before writing any validation code prevents the token-in-git pitfall from the start.

**Delivers:** `SecurityConfig.auth_enabled` + `auth_tokens`, `BearerTokenMiddleware` implementation with tests, `MATLAB_MCP_AUTH_TOKEN` env var pattern.

**Addresses:** Bearer token auth (FEATURES.md table stakes), token-in-git security pitfall (Pitfall 6), auth provider auto-loading pitfall (Pitfall 9).

**Avoids:** Token committed to git (establish env-var-only pattern from day one), auth logic inside tool handlers (anti-pattern 1 in ARCHITECTURE.md).

**Key implementation decisions:**
- `StaticTokenVerifier` (FastMCP built-in) for simple static tokens, or custom `BearerTokenMiddleware` (Starlette `BaseHTTPMiddleware`) for full control — architecture research supports both; custom middleware is more transparent
- Auth applied only to HTTP/SSE transports; stdio bypasses auth by design
- Exempt paths: `/health`, `/dashboard`
- 401 (missing token) vs 403 (invalid token) semantics matter for Codex CLI retry behavior

**Research flag:** Standard patterns — `BaseHTTPMiddleware` is well-documented; bearer token validation is straightforward. No additional research needed.

---

### Phase 3: Streamable HTTP Transport + Session Routing Fix

**Rationale:** Depends on Phase 1 (FastMCP 3.x) and Phase 2 (auth middleware to wire in). This is the phase that directly fixes the Codex CLI connectivity failure.

**Delivers:** `transport="http"` run path, `_get_session_id()` broadened to include `"http"`, `BearerTokenMiddleware` wired into `mcp.http_app(middleware=[...])`, SSE deprecation warning in logs, `--generate-token` CLI flag.

**Addresses:** Streamable HTTP table stake (FEATURES.md), Codex CLI SSE pitfall (Pitfall 5), session routing bug for HTTP transport (ARCHITECTURE.md anti-pattern 4).

**Avoids:** Using `mcp.run(transport="http")` when auth is required (anti-pattern 2 — must use `http_app() + uvicorn.run()` instead).

**Critical test:** Verify `ctx.session_id` is non-None and stable across multiple tool calls in the same agent session under HTTP transport before shipping.

**Research flag:** Needs validation during implementation — the `ctx.session_id` None issue on some streamable-HTTP clients (GitHub issue #956) is a known but not fully resolved gap. The mitigation (fall back to `ctx.client_id` when `ctx.session_id` is None) should be validated with a real Codex CLI end-to-end test.

---

### Phase 4: Polish, Windows Compatibility, Hardening

**Rationale:** Comes last because it validates and documents what was built, and cross-platform testing requires a working Phase 3 implementation.

**Delivers:** Per-tool scope enforcement (`execute` vs `admin`), stateless HTTP mode, Windows 10 no-admin validation (loopback default binding, MATLAB engine on local drive), firewall documentation + PowerShell snippet, Windows CI test, auth failure events in MetricsCollector, final README/docs update.

**Addresses:** Windows Firewall pitfall (Pitfall 4), MATLAB engine on network drive (Pitfall 8), per-tool scopes differentiator (FEATURES.md), stateless HTTP differentiator (FEATURES.md).

**Research flag:** Windows compatibility testing needs a non-admin Windows 10 VM in CI — if CI infrastructure does not already support this, it requires setup work before this phase can be verified. Flag for planning.

---

### Phase Ordering Rationale

- **FastMCP 3.x first** because all auth and transport APIs are 3.x-only; upgrading first avoids writing code against a deprecated API surface.
- **Auth config and middleware before transport wiring** because `BearerTokenMiddleware` is wired into `http_app(middleware=[...])` during Phase 3; it must exist first.
- **Transport as its own phase** because session routing correctness (the `ctx.session_id` stability issue) is the highest-risk item and deserves focused integration testing.
- **Polish last** because scope enforcement and stateless mode build on a working auth system, and Windows validation requires the full stack.

### Research Flags

Phases likely needing deeper research or validation during planning:
- **Phase 3:** `ctx.session_id` stability under streamable HTTP — known open issue (#956). Validate with Codex CLI end-to-end test before declaring done. May need fallback to `ctx.client_id`-based session keying.
- **Phase 4:** Windows 10 non-admin CI environment — needs infrastructure decision (VM, GitHub Actions Windows runner without admin, etc.) before the phase can be reliably verified.

Phases with standard patterns (research not needed):
- **Phase 1:** FastMCP 3.0 upgrade guide is HIGH confidence and comprehensive. All breaking changes are enumerated.
- **Phase 2:** Bearer token middleware is a standard Starlette pattern. Multiple HIGH confidence sources confirm the approach.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | FastMCP 3.2.0 verified against official docs and PyPI. All version compatibility confirmed. Only the `ctx.session_id` None issue (MEDIUM) introduces any uncertainty. |
| Features | HIGH | FastMCP 3.x docs directly consulted. Codex CLI SSE limitation confirmed via official GitHub issue. MCP spec transport deprecation confirmed. |
| Architecture | HIGH | `http_app(middleware=[...])` pattern confirmed in official FastMCP 3.0 deployment docs. `BaseHTTPMiddleware` is standard Starlette. Session routing concern is documented and has a known mitigation. |
| Pitfalls | HIGH | FastMCP 3.0 breaking changes verified from official upgrade guide. Windows behavior from Microsoft docs and community reports. Security mistakes from multiple independent sources. |

**Overall confidence:** HIGH

### Gaps to Address

- **`ctx.session_id` stability under streamable HTTP:** Known issue (#956) where some clients do not send `mcp-session-id` on subsequent requests. Mitigation is to fall back to `ctx.client_id` (set by auth). Must be validated end-to-end before Phase 3 is complete. If the issue proves wider than documented, this could require a custom session-tracking layer.
- **Windows CI environment:** Research confirms Windows no-admin behavior patterns, but real-machine validation is needed. If GitHub Actions Windows runners run as admin (common), a dedicated non-admin test account or VM may be needed.
- **YAML custom tool loader behavior after decorator change:** PITFALLS.md calls this out explicitly. The codebase has a custom YAML-based tool registration path; whether it introspects `@mcp.tool` return values needs verification during Phase 1.

---

## Sources

### Primary (HIGH confidence)
- [FastMCP Changelog](https://gofastmcp.com/changelog) — 3.2.0 release date, version history
- [FastMCP v2→v3 Upgrade Guide](https://gofastmcp.com/development/upgrade-guide) — all breaking changes enumerated
- [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http) — `custom_route`, streamable-HTTP, `http_app(middleware=[...])`
- [FastMCP Token Verification](https://gofastmcp.com/servers/auth/token-verification) — `StaticTokenVerifier`, `JWTVerifier`
- [FastMCP Authentication](https://gofastmcp.com/servers/auth/authentication) — auth provider overview, HTTP-only constraint
- [FastMCP Context](https://gofastmcp.com/servers/context) — `ctx.session_id`, `ctx.client_id`, `ctx.transport`
- [FastMCP pyproject.toml (GitHub main)](https://raw.githubusercontent.com/jlowin/fastmcp/main/pyproject.toml) — dependency floors
- [MCP Streamable HTTP transport spec (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — transport protocol
- [Codex CLI MCP config reference](https://developers.openai.com/codex/config-reference) — `bearer_token_env_var` config key

### Secondary (MEDIUM confidence)
- [What's New in FastMCP 3.0 — jlowin.dev](https://www.jlowin.dev/blog/fastmcp-3-whats-new) — architectural overview, breaking changes summary
- [ctx.session_id None issue — GitHub #956](https://github.com/jlowin/fastmcp/issues/956) — known session_id gap on streamable-HTTP
- [Codex CLI SSE support bug — GitHub openai/codex #5634](https://github.com/openai/codex/issues/5634) — SSE not supported by Codex CLI
- [FastMCP Custom Auth Middleware Discussion — GitHub #1799](https://github.com/jlowin/fastmcp/discussions/1799) — middleware placement confirmed
- [Windows firewall admin requirement — Microsoft docs](https://learn.microsoft.com/en-us/answers/questions/292450) — inbound rule behavior
- [MCP auth best practices](https://toolradar.com/blog/mcp-server-security-best-practices) — security guidance

### Tertiary (LOW confidence — needs validation)
- `ctx.session_id` fallback behavior when client omits `mcp-session-id` header — needs end-to-end test with real Codex CLI
- MATLAB engine startup behavior on Windows 10 non-admin with network-mapped home drive — documented in community reports but project-specific validation needed

---
*Research completed: 2026-04-01*
*Ready for roadmap: yes*
