# Architecture Research

**Domain:** MATLAB MCP Server — v2.0 auth + FastMCP 3.0 upgrade
**Researched:** 2026-04-01
**Confidence:** HIGH (FastMCP 3.0 API verified against official docs; architecture impact inferred from code reading)

## Standard Architecture

### System Overview — Current State (FastMCP 2.x)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Transports (current)                        │
│   stdio (single-user)          SSE (multi-user, no built-in auth)│
├─────────────────────────────────────────────────────────────────┤
│                      server.py                                  │
│   FastMCP(lifespan=lifespan) + @mcp.tool decorators             │
│   MatlabMCPServer (state container, session routing)            │
├────────────┬──────────────┬──────────────┬──────────────────────┤
│  Job Layer │ Session Mgr  │ Security     │ Monitoring           │
│  Executor  │ SessionMgr   │ Validator    │ Collector+Store      │
│  Tracker   │ (per-session │ (blocked fns,│ SQLite, Dashboard    │
│  Job model │  temp dirs)  │  filename)   │                      │
├────────────┴──────────────┴──────────────┴──────────────────────┤
│                     Engine Pool Layer                           │
│   EnginePoolManager  ←→  MatlabEngineWrapper (state machine)    │
├─────────────────────────────────────────────────────────────────┤
│                  MATLAB Engine API (external)                   │
└─────────────────────────────────────────────────────────────────┘
```

### System Overview — Target State (FastMCP 3.0 + Auth)

```
┌─────────────────────────────────────────────────────────────────┐
│               Transports (target)                               │
│  stdio (unchanged)   SSE (compat)   HTTP/streamable (new)       │
├─────────────────────────────────────────────────────────────────┤
│                  Auth Middleware Layer  (NEW)                   │
│   BearerTokenMiddleware — validates Authorization header        │
│   Starlette Middleware — wraps http_app() before MCP layer      │
│   Bypassed for stdio transport                                  │
├─────────────────────────────────────────────────────────────────┤
│                      server.py  (MODIFIED)                      │
│   FastMCP 3.0 constructor (no deprecated kwargs)                │
│   transport="http" run path added alongside stdio/sse           │
│   @mcp.tool decorators return functions (3.0 behavior)          │
│   ctx state methods now async (await ctx.get_state())           │
├──────────────────┬──────────────┬──────────────┬────────────────┤
│  Config Layer    │ Session Mgr  │ Security     │ Monitoring     │
│  (MODIFIED:      │ (unchanged)  │ Validator    │ (unchanged)    │
│   auth section   │              │ + auth audit │                │
│   added)         │              │ logging      │                │
├──────────────────┴──────────────┴──────────────┴────────────────┤
│                     Job / Pool / Output Layers                  │
│                   (unchanged — no auth dependency)              │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Change in v2.0 |
|-----------|----------------|----------------|
| `BearerTokenMiddleware` | Validates `Authorization: Bearer <token>` on every HTTP request before MCP layer | New |
| `server.py / create_server()` | FastMCP 3.0 construction, transport selection, tool registration | Modified |
| `config.py / SecurityConfig` | Auth config: `auth_enabled`, `auth_tokens` list, `require_auth` flag | Modified |
| `config.py / ServerConfig` | Add `"http"` as valid transport literal alongside `"stdio"` and `"sse"` | Modified |
| `MatlabMCPServer` | State container — unchanged; auth state does not belong here | Unchanged |
| `SessionManager` | Per-session workspace isolation — unchanged | Unchanged |
| `EnginePoolManager` | MATLAB engine lifecycle — unchanged | Unchanged |
| `JobExecutor / JobTracker` | Job orchestration — unchanged | Unchanged |
| `SecurityValidator` | MATLAB code safety — unchanged | Unchanged |
| Monitoring layer | Metrics, SQLite, dashboard — should log auth failures | Minor |

## Recommended Project Structure Changes

```
src/matlab_mcp/
├── server.py                  # Modified: FastMCP 3.0 API, http transport, auth wiring
├── config.py                  # Modified: auth section in SecurityConfig + ServerConfig
├── auth/                      # New package
│   ├── __init__.py
│   └── middleware.py          # BearerTokenMiddleware (Starlette BaseHTTPMiddleware)
├── pool/                      # Unchanged
├── jobs/                      # Unchanged
├── session/                   # Unchanged
├── security/                  # Unchanged (MATLAB code validation, not HTTP auth)
├── tools/                     # Unchanged
├── output/                    # Unchanged
└── monitoring/                # Minor: log auth failures as events
```

Keep auth in a dedicated `auth/` package rather than inside `security/`. The existing `security/` package is about MATLAB code safety — mixing HTTP authentication into it would create conceptual confusion and complicate future changes.

## Architectural Patterns

### Pattern 1: Starlette Middleware for HTTP Auth

**What:** Wrap the FastMCP ASGI app with a `BaseHTTPMiddleware` that checks the `Authorization` header before any MCP processing. Reject with HTTP 401 if missing or invalid.

**When to use:** HTTP and SSE transports. Must bypass for stdio (no HTTP layer exists).

**Trade-offs:** Clean separation — auth logic never touches tool handlers or session routing. Health-check endpoints can be exempted. Does add ~1 dict lookup per request.

**Example:**
```python
# src/matlab_mcp/auth/middleware.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, valid_tokens: set[str], exempt_paths: set[str] = frozenset()):
        super().__init__(app)
        self._tokens = valid_tokens
        self._exempt = exempt_paths

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self._exempt:
            return await call_next(request)
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            return JSONResponse({"error": "Missing or invalid Authorization header"}, status_code=401)
        token = header.removeprefix("Bearer ").strip()
        if token not in self._tokens:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
        return await call_next(request)
```

**Wired in server.py:**
```python
# Inside create_server(), after mcp = FastMCP(...)
if config.server.transport in ("http", "sse") and config.security.auth_enabled:
    from starlette.middleware import Middleware
    from matlab_mcp.auth.middleware import BearerTokenMiddleware
    valid_tokens = set(config.security.auth_tokens)
    middleware = [Middleware(BearerTokenMiddleware,
                             valid_tokens=valid_tokens,
                             exempt_paths={"/health", "/dashboard"})]
    app = mcp.http_app(middleware=middleware)
    # run via uvicorn directly instead of mcp.run()
```

**Confidence:** HIGH — `http_app(middleware=[...])` is documented in FastMCP 3.0 official docs. `BaseHTTPMiddleware` pattern confirmed working.

### Pattern 2: FastMCP 3.0 `mcp.run(transport="http")` for Main Loop

**What:** Replace the current transport dispatch in `main()` with `transport="http"` for the new streamable HTTP path. Keep `"stdio"` and `"sse"` paths working unchanged.

**When to use:** New transport option added to the CLI and config.

**Trade-offs:** `mcp.run(transport="http")` starts Uvicorn internally and does not support injecting Starlette middleware. Use `mcp.http_app(middleware=...)` + explicit Uvicorn for the auth case. See anti-pattern below.

**Example:**
```python
# In main() — simplified dispatch
if config.server.transport == "stdio":
    mcp.run(transport="stdio")
elif config.server.transport == "sse":
    if config.security.auth_enabled:
        app = mcp.http_app(middleware=auth_middleware, ...)
        uvicorn.run(app, host=..., port=...)
    else:
        mcp.run(transport="sse", host=..., port=...)
elif config.server.transport == "http":
    if config.security.auth_enabled:
        app = mcp.http_app(middleware=auth_middleware, ...)
        uvicorn.run(app, host=..., port=...)
    else:
        mcp.run(transport="http", host=..., port=...)
```

**Confidence:** HIGH — `mcp.run(transport="http")` and `mcp.http_app()` both confirmed in official FastMCP 3.0 deployment docs.

### Pattern 3: Config-Driven Auth Token Management

**What:** Store auth tokens as a list in `config.yaml` under `security.auth_tokens`. Support `MATLAB_MCP_SECURITY_AUTH_TOKENS` env var for single-token override (comma-separated for multiple). Never log tokens.

**When to use:** Always, for any deployment exposing HTTP transport.

**Trade-offs:** Simple and works without admin rights on Windows (no service, no OS credential store). Tokens are in the config file — operators must secure the file. Rotation requires config reload (restart). Acceptable for v2 scope; full token rotation API is out of scope.

**Config change to `SecurityConfig`:**
```python
class SecurityConfig(BaseModel):
    # ... existing fields ...
    auth_enabled: bool = False
    auth_tokens: List[str] = Field(default_factory=list)
    # existing require_proxy_auth kept for backward compat
```

Backward compatible: `auth_enabled=False` by default, existing deployments unaffected.

## Data Flow

### Auth Request Flow (HTTP transport)

```
MCP Client (Claude Code / Codex CLI)
    │  HTTP POST /mcp  Authorization: Bearer <token>
    ▼
BearerTokenMiddleware.dispatch()
    ├─ path in exempt_paths? → pass through (health, dashboard)
    ├─ header missing or not "Bearer ..."? → 401 immediately
    ├─ token not in valid_tokens set? → 401 immediately
    └─ valid token → call_next(request)
                          ▼
                   FastMCP 3.0 MCP handler
                          ▼
                   Tool handler (@mcp.tool)
                          ▼
                   MatlabMCPServer._get_session_id(ctx)
                          ▼
                   SessionManager / EnginePool / JobExecutor
                          ▼
                   MATLAB Engine API
```

### FastMCP 3.0 Tool Registration Flow

The decorator change in 3.0 (decorators return functions, not component objects) affects tools defined with `@mcp.tool` inside `create_server()`. The handlers in `server.py` are async functions that close over `state` and `config` — this pattern is unaffected because the handlers are called as regular async functions regardless.

The monitoring tool imports at the bottom of `create_server()` (`from matlab_mcp.tools.monitoring import ...`) are defined inline inside the function body and must remain there because they capture `state` via closure.

One adjustment is required: `ctx.get_state()` / `ctx.set_state()` are now async in FastMCP 3.0. The current codebase does not appear to use these methods (session routing uses `ctx.session_id` directly), so this breaking change likely has zero impact. Verify during migration.

### Session ID Routing (unchanged)

```
Request arrives (HTTP transport)
    ▼
MatlabMCPServer._get_session_id(ctx)
    ├─ transport == "http" or "sse" → ctx.session_id (from FastMCP session)
    └─ transport == "stdio" → fixed "default" session
                          ▼
                   SessionManager.get_or_create(session_id)
                          ▼
                   Session.temp_dir used for file operations
```

The `_get_session_id` method checks `config.server.transport == "sse"`. This condition must be broadened to include `"http"` so that HTTP transport also gets proper per-client session routing rather than falling back to the shared `"default"` session.

## Component Boundaries — What Talks to What After Changes

```
CLI / main()
    │ reads config.server.transport
    │ reads config.security.auth_enabled, config.security.auth_tokens
    ▼
create_server(config)
    │ creates FastMCP instance (unchanged interface)
    │ if HTTP transport AND auth_enabled:
    │     builds Starlette middleware list from auth tokens
    │     returns http_app(middleware=...) + uvicorn handle
    │ else:
    │     returns FastMCP instance (mcp.run() path, unchanged)
    ▼
BearerTokenMiddleware  ←→  SecurityConfig.auth_tokens
    │ (only on HTTP/SSE requests, never on stdio)
    ▼
FastMCP 3.0 tool dispatch (unchanged tool signatures)
    ▼
MatlabMCPServer (unchanged state container)
    ├──► SessionManager (unchanged)
    ├──► SecurityValidator (MATLAB code, unchanged)
    ├──► JobExecutor → EnginePoolManager → MATLAB Engine API
    └──► MetricsCollector (minor: record auth failures)
```

**Auth does NOT flow into:** JobExecutor, EnginePoolManager, SessionManager, SecurityValidator. These components have no knowledge of HTTP authentication. Auth is enforced at the transport boundary, not inside business logic.

## Build Order (Dependencies Between New Components)

```
Phase A: Config changes (no external dependencies)
    1. Add auth_enabled + auth_tokens to SecurityConfig
    2. Add "http" to ServerConfig.transport Literal
    3. Update _apply_env_overrides to handle comma-separated token list
    4. Backward compat: defaults leave existing behavior unchanged

Phase B: Auth middleware (depends on Phase A config)
    5. Create src/matlab_mcp/auth/__init__.py
    6. Implement BearerTokenMiddleware
    7. Write tests: valid token passes, invalid returns 401, exempt paths bypass

Phase C: FastMCP 3.0 upgrade (depends on Phase A config, independent of Phase B)
    8. Update pyproject.toml: fastmcp>=3.0.0,<4.0.0
    9. Audit for breaking changes in server.py:
       - Verify no ctx.get_state() / ctx.set_state() calls (likely none)
       - Remove any deprecated FastMCP constructor kwargs
       - Check @mcp.tool decorators still work (they do — returns function now)
    10. Run existing test suite to surface regressions

Phase D: HTTP transport wiring (depends on Phase B + Phase C)
    11. Update _get_session_id() to treat "http" same as "sse"
    12. Update _get_temp_dir() similarly
    13. Add HTTP transport run path in main() using http_app() + uvicorn
    14. Wire BearerTokenMiddleware into http_app(middleware=...) when auth_enabled
    15. Update lifespan auth warning to cover "http" transport

Phase E: Integration + hardening
    16. Cross-platform test on Win10 (no-admin)
    17. Update docs / config examples
    18. Add auth failure event to MetricsCollector
```

## Scaling Considerations

| Scale | Architecture Impact |
|-------|---------------------|
| 1-5 agents | Current design sufficient; single process, in-memory state |
| 5-20 agents | Engine pool max_engines becomes bottleneck; auth overhead negligible |
| 20+ agents | SessionManager.max_sessions (default 50) needs review; MATLAB engine count is the real ceiling |

The MATLAB Engine API imposes a hard ceiling: each engine is a full MATLAB process. This is the primary scalability constraint and is unrelated to the auth changes.

## Anti-Patterns

### Anti-Pattern 1: Auth Logic Inside Tool Handlers

**What people do:** Check tokens inside `@mcp.tool` handlers using `ctx` or injected headers.

**Why it's wrong:** FastMCP middleware (`on_call_tool`) is invoked after the HTTP connection is accepted and authenticated. Putting auth checks inside tools means an unauthenticated client can still establish the MCP session and discover tool schemas before being rejected.

**Do this instead:** HTTP-level Starlette middleware rejects unauthenticated requests before FastMCP even parses the MCP message. Auth happens at the transport boundary.

### Anti-Pattern 2: Using `mcp.run(transport="http")` When Auth Is Required

**What people do:** Call `mcp.run(transport="http")` and try to add middleware afterward.

**Why it's wrong:** `mcp.run()` starts Uvicorn internally and does not expose a middleware injection point. You cannot add Starlette middleware to it.

**Do this instead:** Use `app = mcp.http_app(middleware=[...])` and then `uvicorn.run(app, ...)`. The existing codebase already does this pattern for the monitoring app in SSE mode — reuse that structure.

### Anti-Pattern 3: Sharing Auth State via MatlabMCPServer

**What people do:** Store validated token or user identity in `MatlabMCPServer` state so tools can check it.

**Why it's wrong:** `MatlabMCPServer` is a shared singleton. Storing per-request auth state there creates race conditions in concurrent multi-agent scenarios.

**Do this instead:** Auth is stateless — each request is independently validated by the middleware. If per-request user identity is needed inside tools in a future phase, use FastMCP 3.0's `await ctx.set_state()` (session-scoped) or pass via request context, not shared server state.

### Anti-Pattern 4: Broadening `_get_session_id` Condition Without Testing

**What people do:** Add `"http"` to the transport check in `_get_session_id` and assume it works.

**Why it's wrong:** FastMCP 3.0 streamable HTTP sessions are stateful by default (each connection gets a session ID via `mcp-session-id` header). If the session ID is not propagated correctly between requests in the same agent conversation, each tool call lands in a different MATLAB workspace.

**Do this instead:** Verify `ctx.session_id` is non-None and stable across multiple tool calls in the same agent session under HTTP transport before shipping. Add an integration test that calls `execute_code` twice in the same session and checks workspace persistence.

## Win10 No-Admin Implications

All auth and transport changes are compatible with Win10 no-admin because:

- `BearerTokenMiddleware` is pure Python, no OS integration
- `mcp.http_app()` + `uvicorn.run()` binds to user-space ports (>1024 by default, port 8765)
- No Windows service installation required — server runs as a user process
- Token storage in config.yaml is a flat file, no credential store or registry access
- FastMCP 3.0 upgrade is a `pip install` change, no admin required

One thing to watch: Windows Firewall may block the new HTTP port on first bind. Document that users may need to allow the port through the Windows Firewall (which does prompt even without admin rights in some Win10 configurations).

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| MCP agents (Claude Code, Codex) | HTTP with `Authorization: Bearer <token>` header | Agents must be configured with the token in their MCP server config |
| FastMCP 3.0 | pip upgrade, API migration | Backward compat for stdio/SSE clients confirmed |
| Uvicorn | Direct `uvicorn.run(app)` call | Already a dependency; no new package needed |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `BearerTokenMiddleware` ↔ `SecurityConfig` | Config object passed at middleware construction | Tokens loaded once at startup; restart required to rotate |
| `http_app(middleware=[...])` ↔ `lifespan` | FastMCP lifespan must be passed through when mounting | See FastMCP 3.0 docs: lifespan context required for session manager |
| `_get_session_id()` ↔ `ctx.session_id` | FastMCP 3.0 Context API | Verify property is still `ctx.session_id` (not renamed) in 3.0 |

## Sources

- [FastMCP HTTP Deployment](https://gofastmcp.com/deployment/http) — http_app() middleware pattern, BearerTokenAuth, lifespan requirement (HIGH confidence)
- [FastMCP Authentication](https://gofastmcp.com/servers/auth/authentication) — Auth provider overview, HTTP-only constraint (HIGH confidence)
- [FastMCP Bearer Token Client](https://gofastmcp.com/clients/auth/bearer) — Client-side bearer token configuration (HIGH confidence)
- [FastMCP 3.0: What's New](https://www.jlowin.dev/blog/fastmcp-3-whats-new) — Breaking changes, decorator behavior, async state methods (HIGH confidence)
- [FastMCP Changelog](https://gofastmcp.com/changelog) — Version-specific changes, transport removals, constructor kwarg removals (HIGH confidence)
- [Implementing Auth in Remote MCP Server](https://gelembjuk.com/blog/post/authentication-remote-mcp-server-python/) — BearerTokenMiddleware pattern with `get_http_headers()` (MEDIUM confidence — blog post, not official docs)
- [FastMCP Custom Auth Middleware Discussion](https://github.com/jlowin/fastmcp/discussions/1799) — Distinction between Starlette middleware (HTTP level) and MCP middleware (post-auth); confirmed HTTP middleware is correct approach (MEDIUM confidence)

---
*Architecture research for: MATLAB MCP Server v2.0 — auth + FastMCP 3.0*
*Researched: 2026-04-01*
