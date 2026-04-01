# Phase 3: Streamable HTTP Transport + Session Routing - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Agents connect via streamable HTTP at /mcp with correct per-session workspace isolation. SSE kept working but marked deprecated. Stateless HTTP mode available for load-balancer deployments. stdio unchanged.

</domain>

<decisions>
## Implementation Decisions

### Transport Configuration
- New transport value `"streamablehttp"` in config — FastMCP 3.x `run(transport="streamable-http")` maps to `/mcp`
- SSE deprecation: log WARNING at startup "SSE transport is deprecated, use streamable-http", keep working
- Default transport remains `"stdio"` — backward compatible
- Stateless mode via `server.stateless_http: true/false` config key (default false)

### Session Routing on HTTP
- Session ID source: `ctx.session_id` with fallback to `ctx.client_id` when None — matches STATE.md known issue (#956)
- Stateless mode: each request gets its own ephemeral temp dir — no state between requests
- Session cleanup: same idle timeout as SSE (1hr default) — reuse existing SessionManager
- Max sessions: reuse existing `sessions.max_sessions` config (default 10)

### Middleware & Auth Wiring
- Auth: same BearerAuthMiddleware from Phase 2 — already ASGI, works for any HTTP transport
- CORS: same CORSMiddleware config as SSE
- Monitoring routes: register same routes — dashboard works on both SSE and streamable HTTP
- `/mcp` endpoint: hardcoded path per MCP spec standard

### Claude's Discretion
- Internal refactoring of transport selection logic in `main()`
- Test structure for session isolation tests
- Exact deprecation warning text

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/matlab_mcp/server.py` — Transport selection in `main()` (~line 819), `_get_session_id()` method on MatlabMCPServer
- `src/matlab_mcp/session/manager.py` — SessionManager with create/get/cleanup
- `src/matlab_mcp/auth/middleware.py` — BearerAuthMiddleware (Phase 2)
- `src/matlab_mcp/config.py` — ServerConfig with `transport`, `host`, `port` fields

### Established Patterns
- `server.run(transport=..., host=..., port=..., middleware=...)` for transport selection
- `MatlabMCPServer._get_session_id(ctx)` for session routing per transport
- `MatlabMCPServer._get_temp_dir(session_id)` for workspace isolation
- Middleware wired as `list[Middleware]` in `main()` for SSE transport

### Integration Points
- `config.py::ServerConfig` — Add `stateless_http` field
- `server.py::main()` — Add `"streamablehttp"` transport path with middleware
- `server.py::_get_session_id()` — Add HTTP session routing with ctx.client_id fallback
- `server.py` — SSE deprecation warning at startup

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
