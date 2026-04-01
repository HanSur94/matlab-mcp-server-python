# Feature Research

**Domain:** MCP server for AI coding agents — auth + FastMCP 3.0 upgrade milestone
**Researched:** 2026-04-01
**Confidence:** HIGH (FastMCP 3.x docs directly consulted; MCP spec and agent behavior verified from multiple official sources)

---

## Feature Landscape

### Table Stakes (Agents Can't Connect Without These)

Features where absence means the agent either refuses to connect, gets a 401, or gives up during setup.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Bearer token auth via `Authorization` header | Claude Code, Codex CLI, Cursor all send headers natively. Without it Codex CLI fails silently over SSE. | LOW | FastMCP 3.x `JWTVerifier` with HS256 shared secret covers this — no OAuth server needed. Clients configure `bearer_token_env_var` or `--header "Authorization: Bearer <token>"`. |
| Streamable HTTP transport at `/mcp` | SSE transport is officially deprecated as of April 1 2026. Claude Code, Cursor, and Codex CLI all recommend streamable HTTP as the remote transport default for new setups. | MEDIUM | FastMCP 3.x `transport="streamable-http"` gives a single `POST /mcp` + `GET /mcp` endpoint. Must replace legacy SSE endpoint. Keep stdio path untouched. |
| Token rejection returns HTTP 401 | Agents treat anything other than 401 on a bad token as a misconfiguration. 403 or 500 will cause confusing failures. | LOW | FastMCP 3.x `JWTVerifier` / `AuthMiddleware` emit 401 automatically on invalid token. |
| Correct CORS headers for browser-based agent UIs | Cursor's web panel and similar UIs make cross-origin requests. Missing CORS = silent connection drop. | LOW | FastMCP 3.x HTTP deployment exposes CORS config directly. Allow `*` or explicit origins. |
| Static token config stays out of code | Codex CLI reads bearer token from env var (`bearer_token_env_var = "MCP_TOKEN"`). Any hardcoded token in config.yaml is a security debt that blocks corporate adoption. | LOW | Implement via `MCP_AUTH_TOKEN` env var override on `config.yaml`. Document this pattern explicitly for agents. |
| Backward compat for stdio (single-user) | Corporate users already configured with stdio must not break on upgrade. Any migration must be additive. | LOW | stdio path has no auth in MCP spec (by design). FastMCP 3.x keeps stdio working with zero config changes. |

---

### Differentiators (Competitive Advantage)

Features that set this server apart from generic MCP stubs. Aligned with Core Value: "any MCP-compatible coding agent connects with minimal setup."

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Env-var-first token config (`MCP_AUTH_TOKEN`) | One env var, no config file edits — any agent or CI/CD pipeline works without touching YAML. The Codex CLI auth failure was caused by complex reverse-proxy setup; this eliminates that entirely. | LOW | Wire `MCP_AUTH_TOKEN` into `AppConfig` as an override that sets the shared secret for `JWTVerifier`. Document a `--generate-token` CLI flag that prints a ready-to-use HS256 token. |
| `--generate-token` CLI helper | Eliminates the #1 onboarding friction point: generating a valid signed token. Codex users shouldn't need `python-jose` installed locally just to connect. | LOW | Print base64-encoded HS256 JWT + the matching env var snippet. One command = ready to paste. |
| Streamable HTTP + stateless mode | Enables horizontal scale and load-balancing without sticky sessions. Relevant for academic clusters and corporate shared infra. Claude Code and Codex CLI both have a limitation where they don't forward cookies, so sticky sessions break silently — stateless mode sidesteps this entirely. | MEDIUM | FastMCP 3.x `stateless_http=True` on `run()`. No session affinity needed. Each request is self-contained. |
| Per-tool scope enforcement | Admin tools (`get_pool_status`, engine control) should require an `admin` scope. Execution tools need only `execute`. This matters in shared/multi-user deployments. | MEDIUM | FastMCP 3.x `@mcp.tool(auth=require_scopes("admin"))`. Map existing tool categories to two scopes: `execute` and `admin`. Include scope claims in the generated token. |
| Windows 10 no-admin HTTP deployment guide | Corporate MATLAB users run on locked-down machines. Ports ≥1024 work without elevation. The server should default to port 8000, document user-space startup, and provide a one-liner startup script. | LOW | No code change needed. Ensure default port is 8000 (already likely), add Win10 note to docs/README, verify `python -m matlab_mcp --transport http` works without elevated permissions on Win10. |
| Token rotation without restart | A shared server used by multiple agents needs the ability to invalidate old tokens without restarting (and draining MATLAB engine pool). | MEDIUM | Implement a token set (list of valid tokens) loaded from env var list or file, with a hot-reload endpoint (`POST /admin/reload-tokens`). Medium complexity because it requires a mutable auth state object alongside FastMCP's verifier. |
| Agent-readable connection instructions in `/mcp` response | When a client hits `/mcp` with no auth header, return a 401 with a `WWW-Authenticate` hint and a JSON body pointing to the docs URL. Makes onboarding self-documenting for AI agents that read HTTP responses. | LOW | Custom 401 response body via FastMCP middleware. Non-breaking. |

---

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full OAuth 2.1 + PKCE flow | "The spec requires it for remote servers" | OAuth requires an authorization server, a browser redirect, a token endpoint, and PKCE exchange — none of which work in CLI/agent contexts without a browser. Corporate firewalls block callback URLs. Adds a dependency on an external OAuth provider. For internal team tools the spec explicitly carves out static bearer tokens as sufficient. | Static bearer token with `JWTVerifier(algorithm="HS256")` — signed, expirable, no auth server needed. |
| Per-user MATLAB workspace mapped to OAuth identity | Clean multi-tenancy story | Requires an identity provider, token introspection, and mapping OAuth sub to session_id. Way beyond v2 scope and the existing `SessionManager` already handles workspace isolation by session_id. | Let the agent pass a `session_id` parameter (already supported). Document the convention: each agent instance uses a unique session_id. |
| Dynamic Client Registration (DCR) | FastMCP 3.x supports CIMD (the successor) | CIMD requires the client to host an HTTPS metadata document. Coding agents (Claude Code, Codex CLI) don't host HTTPS endpoints — they're CLIs. CIMD is for server-to-server OAuth, not CLI agents. | Static pre-shared tokens. |
| Persistent SSE transport (legacy) | Some older tooling still uses SSE | SSE is officially deprecated in the MCP spec (effective April 1 2026). Building new features on SSE incurs future migration debt. Existing SSE users should migrate to streamable HTTP. | Keep existing SSE support running unmodified for backward compat, but add a deprecation warning in logs when SSE transport is selected. Don't add new auth features to SSE path. |
| GUI token management dashboard | Non-technical users | Adds frontend complexity with no benefit for the agent-first use case. Agents read tokens from env vars, not dashboards. | CLI `--generate-token` + plain-text README instructions. |
| mTLS (mutual TLS) | Enterprise security posture | Requires client certificate infrastructure that coding agents (Claude Code, Codex) don't support. Any agent would need custom TLS configuration, defeating the "minimal setup" core value. | Bearer token over HTTPS. Use a reverse proxy (nginx/Caddy) for TLS termination if TLS is required. |

---

## Feature Dependencies

```
[Streamable HTTP transport]
    └──requires──> [FastMCP 3.0 upgrade]
                       └──requires──> [Breaking change audit: constructor params, async state, renamed methods]

[Bearer token auth]
    └──requires──> [Streamable HTTP transport]  (auth is not supported on stdio by design)
    └──requires──> [FastMCP 3.0 upgrade]        (JWTVerifier / AuthMiddleware are 3.x APIs)

[Per-tool scope enforcement]
    └──requires──> [Bearer token auth]
    └──requires──> [Token generation with scope claims]

[--generate-token CLI helper]
    └──requires──> [Bearer token auth]           (needs to know which algorithm and secret to use)
    └──enhances──> [Env-var-first token config]

[Stateless HTTP mode]
    └──requires──> [Streamable HTTP transport]
    └──enhances──> [Windows 10 no-admin deployment] (no session affinity = simpler single-machine setup)

[Token rotation without restart]
    └──requires──> [Bearer token auth]
    └──conflicts──> [Static StaticTokenVerifier]  (static verifier is immutable; need mutable token store)

[Deprecation warning for SSE]
    └──requires──> [Streamable HTTP transport]   (must have the replacement before deprecating)
```

### Dependency Notes

- **Streamable HTTP requires FastMCP 3.0:** The `streamable-http` transport mode and `JWTVerifier` auth provider are v3.x-only APIs. The `<3.0.0` pin in pyproject.toml must be removed first.
- **Bearer token auth requires HTTP transport:** The MCP spec explicitly states stdio bypasses auth (the transport has no OAuth capability). Auth features are meaningless on stdio and must not be applied there.
- **Per-tool scopes require token generation to include scope claims:** If `--generate-token` doesn't embed `scopes: ["execute"]` in the JWT payload, `require_scopes("execute")` will reject every request.
- **Token rotation conflicts with static verifier:** `JWTVerifier` with a single shared secret can't support rotation. Need a `MultiKeyVerifier` pattern or a custom callable that reads from a mutable token set. Treat token rotation as a v2.1+ feature unless a simple approach is found.

---

## MVP Definition

This is a subsequent milestone — the server already ships. "MVP" here means the minimum needed so that Codex CLI (and other agents) connect without failure.

### Ship With (v2.0 Core)

- [ ] FastMCP 3.0 upgrade (remove `<3.0.0` pin, audit breaking changes, migrate constructor params and async ctx) — gate for everything else
- [ ] Streamable HTTP transport (`--transport streamable-http`) — SSE is deprecated, agents expect this
- [ ] Bearer token auth via `MCP_AUTH_TOKEN` env var with `JWTVerifier` HS256 — solves the Codex CLI auth failure directly
- [ ] `--generate-token` CLI helper — eliminates the onboarding friction that caused the original failure
- [ ] 401 response with `WWW-Authenticate` hint — self-documenting for agents
- [ ] Deprecation log warning when SSE transport is used — manage the migration

### Add After Core Is Stable (v2.0 Polish)

- [ ] Per-tool scope enforcement (`execute` vs `admin`) — adds security posture without blocking basic connectivity
- [ ] Stateless HTTP mode documentation and default — needed for multi-instance / corporate cluster deployments
- [ ] Windows 10 no-admin deployment guide — existing port 8000 default likely already works; needs validation and docs

### Defer to v2.1+

- [ ] Token rotation without restart — requires a mutable verifier design; not blocking any agent use case at launch
- [ ] Agent-readable 401 JSON body — nice-to-have UX polish, not a connectivity blocker

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| FastMCP 3.0 upgrade | HIGH | MEDIUM (breaking change audit required) | P1 |
| Streamable HTTP transport | HIGH | LOW (one transport flag change) | P1 |
| Bearer token auth (env var + JWTVerifier) | HIGH | LOW | P1 |
| `--generate-token` CLI flag | HIGH | LOW | P1 |
| SSE deprecation warning | MEDIUM | LOW | P1 |
| Per-tool scope enforcement | MEDIUM | LOW (once auth is wired) | P2 |
| Stateless HTTP mode | MEDIUM | LOW (one flag in run()) | P2 |
| Windows 10 no-admin guide | MEDIUM | LOW (docs + port verification) | P2 |
| Token rotation without restart | LOW | MEDIUM | P3 |
| Agent-readable 401 JSON body | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for v2.0 — directly solves the Codex CLI auth failure and SSE deprecation
- P2: Should have — adds robustness for multi-user and corporate deployments
- P3: Nice to have — polish, defer until P1+P2 are stable

---

## Competitor / Ecosystem Feature Analysis

| Feature | Generic MCP stubs | FastMCP 2.x (current) | Our v2.0 target |
|---------|-------------------|----------------------|-----------------|
| Auth transport | None / reverse proxy only | `require_proxy_auth` flag (no built-in) | Built-in HS256 JWT via `MCP_AUTH_TOKEN` |
| HTTP transport | Varies | SSE (deprecated) | Streamable HTTP (spec current) |
| Token generation | Manual / openssl | None | `--generate-token` CLI flag |
| Per-tool scopes | None | None | `require_scopes("execute"/"admin")` |
| Multi-agent sessions | None | Session isolation exists | Session isolation + stateless HTTP |
| Windows no-admin | Not documented | Not documented | Validated + documented |

---

## Sources

- FastMCP 3.0 release blog: https://www.jlowin.dev/blog/fastmcp-3-whats-new
- FastMCP HTTP deployment docs: https://gofastmcp.com/deployment/http
- FastMCP token verification docs: https://gofastmcp.com/servers/auth/token-verification
- FastMCP authorization docs: https://gofastmcp.com/servers/authorization
- FastMCP v2 to v3 upgrade guide: https://gofastmcp.com/getting-started/upgrading/from-fastmcp-2
- FastMCP 3.2.0 on PyPI (latest as of 2026-04-01): https://pypi.org/project/fastmcp/
- MCP auth spec (draft): https://modelcontextprotocol.io/specification/draft/basic/authorization
- MCP streamable HTTP transport spec (2025-03-26): https://modelcontextprotocol.io/specification/2025-03-26/basic/transports
- SSE deprecation announcement: https://changelog.keboola.com/deprecation-of-sse-transport-in-mcp-server-upgrade-to-streamable-http/
- Claude Code MCP auth guide: https://www.truefoundry.com/blog/mcp-authentication-in-claude-code
- Claude Code MCP docs: https://code.claude.com/docs/en/mcp
- Codex CLI MCP config reference: https://developers.openai.com/codex/config-reference
- MCP auth spec explainer (Stack Overflow blog, 2026-01): https://stackoverflow.blog/2026/01/21/is-that-allowed-authentication-and-authorization-in-model-context-protocol/
- MCP auth guide (what spec actually requires): https://mcpplaygroundonline.com/blog/mcp-server-oauth-authentication-guide

---

*Feature research for: MATLAB MCP Server v2.0 — auth + FastMCP 3.0 upgrade*
*Researched: 2026-04-01*
