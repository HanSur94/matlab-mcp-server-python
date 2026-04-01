# Stack Research

**Domain:** Production MCP server — FastMCP 3.x upgrade + authentication
**Researched:** 2026-04-01
**Confidence:** HIGH (FastMCP 3.x via official docs + changelog; auth patterns via official docs)

---

## Current State vs Target State

| Area | Current (v1.x) | Target (v2.0) |
|------|---------------|---------------|
| FastMCP | 2.14.5 (`<3.0.0` pinned) | 3.2.0 |
| Transport | stdio / SSE | stdio / SSE (kept) + streamable-http (new) |
| Auth | `require_proxy_auth` flag only — no built-in auth | `StaticTokenVerifier` — bearer token checked in-process |
| Context import | `from fastmcp.server.context import Context` | `from fastmcp import Context` |
| Route mounting | `mcp._additional_http_routes.append(Mount(...))` | `@mcp.custom_route(path, methods=[...])` |
| Token dep | None | `authlib>=1.6.5` (pulled by FastMCP 3.x core — no manual add needed) |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastMCP | **3.2.0** | MCP server framework — tool registration, transport, auth | Latest stable as of 2026-03-30. v3 GA on 2026-02-18. Provides built-in `StaticTokenVerifier`/`JWTVerifier`, streamable-HTTP transport, `@mcp.custom_route()`. Provider/transform architecture is a full rebuild but surface API (decorators, `Context`) is backward-compatible. |
| mcp (python-sdk) | **1.x** (pulled transitively) | Protocol implementation layer under FastMCP | FastMCP 3.x depends on it; do not pin independently. |
| authlib | **>=1.6.5** (transitive via FastMCP 3.x) | JWT/OAuth token handling used by FastMCP auth providers | Pulled as a direct FastMCP 3 dependency. Already present in current `requirements-lock.txt` (1.6.9). No explicit add needed in `pyproject.toml`. |
| PyJWT | **>=2.12.0** (optional — only if Azure auth is needed) | JWT encode/decode for non-FastMCP token generation | FastMCP 3 includes it as an optional `azure` extra dep (CVE-2026-32597 floor). Not needed unless this project generates JWTs itself (it doesn't — it only verifies). |
| uvicorn | **>=0.20.0** (keep current 0.42.0) | ASGI server for HTTP transport and monitoring dashboard | No version change needed. FastMCP 3.x `run(transport="http")` wraps uvicorn internally. |
| Starlette | **>=0.40.0** (keep current 0.52.1) | Web framework for monitoring dashboard | FastMCP 3.x still uses Starlette under the hood. Current pinned version is compatible. |

### Supporting Libraries (unchanged from v1.x)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic | 2.12.5 | Config validation | All config models in `config.py`. No change. |
| pyyaml | 6.0.3 | YAML config loading | `load_config()`. No change. |
| aiosqlite | 0.22.1 | Async SQLite for metrics | Monitoring store. No change. |
| sse-starlette | 3.3.3 | SSE transport support | Still needed for legacy SSE transport. |
| websockets | 16.0 | WebSocket support | Transitive. No change. |
| plotly | 6.6.0 | Figure conversion | Output formatting. No change. |
| Pillow | 12.1.1 | Thumbnail generation | Image output. No change. |
| psutil | >=5.9.0 | System metrics | Monitoring collector. No change. |

### Development Tools (unchanged)

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest + pytest-asyncio | Testing | No change. |
| ruff | Linting/formatting | No change. |
| pip-audit | Security scanning | Run after upgrading to catch transitive CVEs. |
| hatchling | Build backend | No change. |

---

## Installation

```bash
# Upgrade FastMCP — the only required change to pyproject.toml
# Change: fastmcp>=2.0.0,<3.0.0  →  fastmcp>=3.2.0,<4.0.0

pip install "fastmcp>=3.2.0,<4.0.0"

# Everything else stays the same — no new packages needed for auth.
# authlib is a transitive dependency of fastmcp 3.x and is already
# present in requirements-lock.txt (1.6.9).

# After upgrading, regenerate the lockfile:
pip install -e ".[dev]" && pip freeze > requirements-lock.txt
```

---

## FastMCP 3.x Migration: Specific Code Changes Required

This section maps each breaking change against the actual server.py code.

### 1. Context import path (REQUIRED — will break at import time)

```python
# CURRENT (server.py line 16)
from fastmcp.server.context import Context

# FIXED
from fastmcp import Context
```

Confidence: HIGH — confirmed via official FastMCP 3.x docs. The old path is removed.

### 2. Transport kwargs moved from constructor to run() (REQUIRED)

```python
# CURRENT (server.py lines 792-798)
server.run(transport="sse", host=config.server.host, port=config.server.port)
server.run(transport="stdio")

# In v3 this is FINE — host/port still accepted by run(), NOT FastMCP().
# The removed params are only constructor kwargs, NOT run() kwargs.
# No change needed here.
```

The current code already passes host/port to `run()`, not to `FastMCP()`. No change needed.

Confidence: HIGH — confirmed via upgrade guide.

### 3. Monitoring route mounting — `_additional_http_routes` (REQUIRED)

The private `_additional_http_routes` list is an internal FastMCP 2.x detail and is NOT guaranteed to exist in 3.x. In fact, FastMCP 3.x replaced this pattern with `@mcp.custom_route()`.

```python
# CURRENT (server.py lines 374-385)
mcp._additional_http_routes.append(Mount("/", app=monitoring_sub_app))

# FIXED — use custom_route() for individual endpoints
@mcp.custom_route("/dashboard", methods=["GET"])
async def dashboard_route(request):
    return await monitoring_sub_app(request.scope, request.receive, request.send)

@mcp.custom_route("/health", methods=["GET"])
async def health_route(request):
    return await monitoring_sub_app(request.scope, request.receive, request.send)

# OR: mount as Starlette sub-application (preferred for complex apps):
mcp_app = mcp.http_app(path="/mcp")
app = Starlette(
    routes=[
        Mount("/monitoring", app=monitoring_sub_app),
        Mount("/", app=mcp_app),
    ],
    lifespan=mcp_app.lifespan,
)
# Then run with uvicorn.run(app, ...) directly instead of mcp.run().
```

IMPORTANT: FastMCP 3.x `@custom_route()` endpoints bypass auth middleware by design — which is correct for the health/dashboard use case.

Confidence: HIGH — confirmed via official docs (gofastmcp.com/deployment/http).

### 4. config.server.transport — add "http" as valid value (REQUIRED)

```python
# CURRENT (config.py line 28)
transport: Literal["stdio", "sse"] = "stdio"

# FIXED
transport: Literal["stdio", "sse", "http"] = "stdio"
```

The new transport value is `"http"` (not `"streamable-http"` — that was a beta name). In v3 stable, `mcp.run(transport="http")` starts streamable HTTP on `/mcp`.

Confidence: HIGH — confirmed via gofastmcp.com/deployment/running-server.

### 5. get_tools() / get_resources() renamed (LOW RISK — check usage)

If any code calls `await mcp.get_tools()`, rename to `await mcp.list_tools()`. The return type also changed from dict to list. Check monitoring tools and admin endpoints.

Confidence: HIGH — documented breaking change.

---

## Authentication Architecture

### Recommended: StaticTokenVerifier (no external dependency)

For this project, `StaticTokenVerifier` from FastMCP 3.x is the right choice:
- No JWKS endpoint, no OAuth server, no JWT signing infrastructure needed
- Works completely offline — important for corporate/academic air-gapped environments
- Static tokens loaded from config or environment variables
- Clients pass `Authorization: Bearer <token>` header
- Only applies to HTTP transports (streamable-http, SSE) — stdio is unaffected

```python
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

# Load tokens from config/env
verifier = StaticTokenVerifier(
    tokens={
        os.environ["MATLAB_MCP_API_KEY"]: {
            "client_id": "default-user",
            "scopes": ["execute", "read", "write"],
        }
    }
)

mcp = FastMCP(name="matlab-mcp-server", auth=verifier, lifespan=lifespan)
```

Key properties:
- Auth only activates when `transport="http"` or `transport="sse"` — stdio connections bypass auth (correct for local single-user)
- Multiple tokens can map to different client IDs (multi-user ready)
- Token exposed in tools via `ctx.client_id`

### Alternative: JWTVerifier with HMAC (if tokens need expiry)

If the project later needs token expiry without a full OAuth server:

```python
from fastmcp.server.auth.providers.jwt import JWTVerifier

verifier = JWTVerifier(
    public_key=os.environ["MATLAB_MCP_JWT_SECRET"],  # min 32 chars
    issuer="matlab-mcp-server",
    audience="mcp-clients",
    algorithm="HS256",
)
```

Generate tokens with any JWT library (PyJWT is already in the lockfile). No external auth server needed.

### What NOT to use for auth

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| OAuth 2.1 / PKCE full flow | Too complex for v2 scope; agents need redirect flows; PROJECT.md explicitly calls this out of scope | `StaticTokenVerifier` |
| `RemoteAuthProvider` / `OAuthProxy` | Requires external identity provider setup; overkill for internal/academic use | `StaticTokenVerifier` |
| `require_proxy_auth` flag (current) | Not auth — just a boolean that logs a warning; provides zero actual security | `StaticTokenVerifier` or `JWTVerifier` |
| Reverse proxy-only auth (nginx/Caddy) | Adds infrastructure requirement that conflicts with Win10 no-admin constraint | In-process `StaticTokenVerifier` |
| `python-jose` | Last release 2023, practically abandoned; FastAPI team recommends against it | `authlib` (already transitive in FastMCP 3.x) |

---

## Transport Strategy

### Keep SSE, Add HTTP — Do Not Remove SSE Yet

FastMCP 3.x marks SSE as "legacy" but it remains supported. Many existing MCP clients (Claude Desktop, some Cursor configurations) use the SSE protocol. Removing it in v2.0 would break existing users.

| Transport | Use Case | Auth Applied | Session ID Available |
|-----------|----------|--------------|---------------------|
| `stdio` | Single-user local (Claude Code via CLI) | No (correct) | No — use "default" fixed session |
| `sse` | Legacy remote/multi-user | Yes (with `auth=verifier`) | Yes — `ctx.session_id` |
| `http` (streamable-HTTP) | Modern remote/multi-user | Yes (with `auth=verifier`) | Yes — `ctx.session_id` |

IMPORTANT KNOWN ISSUE: There are documented problems with `ctx.session_id` being `None` on some streamable-HTTP client implementations when clients do not correctly send the `mcp-session-id` header on subsequent requests. This breaks the current `_get_session_id()` pattern. The mitigation is to fall back to a session derived from `ctx.client_id` (set by auth) rather than `ctx.session_id` alone.

### Streamable HTTP endpoint path

When `transport="http"`, the MCP endpoint is at `/mcp` (not `/sse`). Agent configs must be updated accordingly:

```
# Old SSE config
"url": "http://host:8765/sse"

# New HTTP config  
"url": "http://host:8765/mcp"
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FastMCP 3.x built-in `StaticTokenVerifier` | Custom Starlette middleware | If FastMCP's auth system proves too restrictive or has unresolved bugs — but then loses the clean `auth=` integration |
| FastMCP 3.x `@custom_route()` | Full Starlette app wrapping `mcp.http_app()` | When monitoring UI needs its own lifespan or complex routing — more code but more control |
| Upgrade to 3.2.0 now | Stay on 2.14.5 | Never — FastMCP 2.x has no built-in auth; the `require_proxy_auth` flag provides no real security; 3.x is the only path forward |
| `authlib` (transitive) | `PyJWT` for token generation | `PyJWT` is fine for generating tokens to hand to users; use `authlib` for server-side verification via FastMCP |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `fastmcp>=2.0.0,<3.0.0` (current pyproject.toml) | Pins out 3.x entirely; blocks all auth and HTTP transport features | `fastmcp>=3.2.0,<4.0.0` |
| `mcp._additional_http_routes` | Private attribute, removed/changed in 3.x | `@mcp.custom_route()` or Starlette app wrapping |
| `from fastmcp.server.context import Context` | Import path removed in 3.x | `from fastmcp import Context` |
| `WSTransport` | Removed in FastMCP 3.x | `StreamableHttpTransport` |
| `diskcache` (was in lock file) | CVE present — already removed per commit ee6117b | `aiosqlite` (already used) |
| OAuth 2.1 for v2.0 | Out of scope per PROJECT.md; adds redirect flows incompatible with CLI agents | `StaticTokenVerifier` |
| `fakeredis` / `redis` (in lock file) | These are FastMCP internal dependencies (for proxy/cache features) — do not depend on them directly | — |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| fastmcp 3.2.0 | Python 3.10–3.13 | Confirmed in pyproject.toml |
| fastmcp 3.2.0 | authlib >=1.6.5 | Direct dep — authlib 1.6.9 in current lockfile is compatible |
| fastmcp 3.2.0 | pydantic >=2.11.7 | Bumped floor vs FastMCP 2.x; current pydantic 2.12.5 satisfies this |
| fastmcp 3.2.0 | starlette 0.52.1 | No known incompatibility; starlette is a transitive dep of FastMCP |
| fastmcp 3.2.0 | uvicorn 0.42.0 | No known incompatibility |
| fastmcp 3.2.0 | PyJWT >=2.12.0 (optional) | Only needed for Azure OBO flows; current lockfile has 2.12.1 |
| mcp 1.26.0 | fastmcp 3.2.0 | FastMCP 3.x pulls mcp as transitive dep; do not pin `mcp` independently |

---

## Windows 10 No-Admin Compatibility Notes

All stack choices are compatible with Win10 without admin rights:

| Choice | Win10 No-Admin Status | Notes |
|--------|----------------------|-------|
| FastMCP 3.2.0 | Compatible | Pure Python, pip install, no OS hooks |
| `StaticTokenVerifier` | Compatible | In-process; no OS keyring required (keyring is only used for OAuth flows) |
| streamable-HTTP on port 8765 | Compatible | Unprivileged port (>1024) — no admin needed |
| uvicorn | Compatible | Pure Python ASGI server, no service installation |
| aiosqlite | Compatible | SQLite file in user-writable directory |
| authlib | Compatible | Pure Python cryptography |
| cryptography (transitive) | Compatible | Has wheels for Win10; no native compilation needed |

AVOID: Do not use OAuth flows that store tokens in the Windows system keyring — FastMCP 3.x does this for OAuth providers (GitHubProvider etc.) but `StaticTokenVerifier` uses in-memory storage only and is unaffected.

---

## Stack Patterns by Variant

**If deploying for single local user (Claude Code / stdio):**
- Use `transport="stdio"` — no auth needed, no port needed
- Keep `pool.min_engines=1`, `pool.max_engines=4` (Win10 macOS warning at >4 still applies)

**If deploying for multi-user remote (HTTP/SSE):**
- Use `transport="http"` (streamable-HTTP) for new deployments, `transport="sse"` for clients that don't yet support MCP HTTP
- Always set `MATLAB_MCP_API_KEY` env var and configure `StaticTokenVerifier`
- Set `pool.max_engines` to match available MATLAB licenses

**If tokens need per-user isolation:**
- Use `StaticTokenVerifier` with one token per user, each mapping to a unique `client_id`
- Use `ctx.client_id` (set by auth) as session key rather than `ctx.session_id` (can be None in some streamable-HTTP clients)

**If JWT tokens with expiry are needed (future):**
- Upgrade to `JWTVerifier` with HMAC secret — zero infrastructure change needed, only token generation logic added

---

## Sources

- [FastMCP Changelog — gofastmcp.com/changelog](https://gofastmcp.com/changelog) — version history, 3.2.0 release date confirmed HIGH
- [FastMCP v2→v3 Upgrade Guide — gofastmcp.com/development/upgrade-guide](https://gofastmcp.com/development/upgrade-guide) — all breaking changes HIGH
- [FastMCP HTTP Deployment — gofastmcp.com/deployment/http](https://gofastmcp.com/deployment/http) — custom_route, streamable-HTTP path HIGH
- [FastMCP Token Verification — gofastmcp.com/servers/auth/token-verification](https://gofastmcp.com/servers/auth/token-verification) — StaticTokenVerifier, JWTVerifier HIGH
- [FastMCP Authentication — gofastmcp.com/servers/auth/authentication](https://gofastmcp.com/servers/auth/authentication) — auth provider overview HIGH
- [FastMCP Context — gofastmcp.com/servers/context](https://gofastmcp.com/servers/context) — ctx.session_id, ctx.client_id, ctx.transport HIGH
- [FastMCP pyproject.toml (GitHub main)](https://raw.githubusercontent.com/jlowin/fastmcp/main/pyproject.toml) — authlib >=1.6.5, PyJWT optional HIGH
- [FastMCP PyPI page](https://pypi.org/project/fastmcp/) — 3.2.0 latest as of 2026-03-30 HIGH
- [What's New in FastMCP 3.0 — jlowin.dev](https://www.jlowin.dev/blog/fastmcp-3-whats-new) — architectural overview MEDIUM
- [MCP Authorization spec — modelcontextprotocol.io](https://modelcontextprotocol.io/specification/draft/basic/authorization) — OAuth 2.1 resource server spec MEDIUM
- [ctx.session_id None issue — GitHub PrefectHQ/fastmcp #956](https://github.com/jlowin/fastmcp/issues/956) — known session_id gap on streamable-HTTP MEDIUM
- [Authentication bypass on custom routes — winfunc.com](https://winfunc.com/hacktivity/anthropic-fastmcp-auth-bypass) — custom_route auth bypass (by design) MEDIUM

---

*Stack research for: MATLAB MCP Server v2.0 — FastMCP 3.x upgrade + authentication*
*Researched: 2026-04-01*
