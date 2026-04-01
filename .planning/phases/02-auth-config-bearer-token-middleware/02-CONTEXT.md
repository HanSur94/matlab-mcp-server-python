# Phase 2: Auth Config + Bearer Token Middleware - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Bearer token authentication enforced on HTTP/SSE transports via ASGI middleware. Tokens sourced exclusively from environment variables. stdio transport bypasses auth. CORS enabled for browser-based agent UIs. CLI flag generates ready-to-use tokens.

</domain>

<decisions>
## Implementation Decisions

### Token Format & Generation
- Opaque random hex tokens (32 bytes / 64 hex chars) — no JWT, no expiry semantics
- No token expiry — static tokens, rotate by generating new token and restarting server
- Constant-time comparison via `hmac.compare_digest` to prevent timing attacks
- Single token from `MATLAB_MCP_AUTH_TOKEN` env var — no multi-token support

### CORS Configuration
- Default CORS allowed origins: `*` (any origin) — agents connect from various hosts
- CORS methods: `GET, POST, OPTIONS` — standard for MCP protocol
- CORS headers: `Authorization, Content-Type, Accept` — minimum needed for bearer auth + JSON
- Skip CORS entirely on stdio transport — no HTTP layer

### Middleware Architecture
- Starlette ASGI middleware — intercepts before FastMCP, clean separation of concerns
- Log `WARNING` at startup if any token-like key (e.g. `security.auth_token`) exists in loaded config.yaml
- Allow `/health` without auth — load balancers need unauthenticated health checks
- Error responses: JSON body `{"error": "unauthorized", "message": "..."}` with `WWW-Authenticate: Bearer` header

### Claude's Discretion
- Internal module organization (single file vs split auth/cors modules)
- Test structure and fixtures
- Exact CLI output format for `--generate-token`

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/matlab_mcp/config.py` — Pydantic config models with `SecurityConfig` (line 78), already has `require_proxy_auth` flag
- `src/matlab_mcp/server.py` — Server factory with transport selection, CLI arg parsing, `main()` entry point
- `src/matlab_mcp/monitoring/dashboard.py` — `register_monitoring_routes()` using `@mcp.custom_route()` (Phase 1 migration)
- Existing SSE security warning at `server.py:170-177`

### Established Patterns
- Config via Pydantic BaseModel classes in `config.py`
- Environment variable overrides via `MATLAB_MCP_*` prefix in `_apply_env_overrides()`
- CLI args parsed in `main()` with argparse
- FastMCP `mcp.run()` for transport selection
- Monitoring routes registered via `@mcp.custom_route()`

### Integration Points
- `config.py` — Add auth-related config fields (for warnings, not token storage)
- `server.py::create_server()` — Wire middleware before `mcp.run()`
- `server.py::main()` — Add `--generate-token` CLI flag
- `config.yaml` — No auth token fields (env var only) but auth section for toggles

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

- Per-tool scope enforcement (AUTH scopes) — tracked as AAUTH-01 in v2 requirements
- Token rotation without restart — tracked as AAUTH-02 in v2 requirements
- Agent-readable 401 JSON with docs URL — tracked as AAUTH-03 in v2 requirements

</deferred>
