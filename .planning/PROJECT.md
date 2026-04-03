# MATLAB MCP Server

## What This Is

A Python-based MCP server that lets AI coding agents (Claude Code, Codex CLI, Cursor, etc.) execute MATLAB code, inspect workspaces, manage files, and monitor server health. It bridges the Model Context Protocol to MATLAB's Engine API with elastic pooling, session isolation, async job orchestration, bearer token authentication, human-in-the-loop approval gates, and streamable HTTP transport.

## Core Value

Any MCP-compatible coding agent can connect to MATLAB and run code securely — with minimal setup, proper authentication, and production-grade reliability.

## Requirements

### Validated

- MATLAB code execution via MCP tools (execute_code, check_code) — existing
- Elastic MATLAB engine pool with auto-scaling and health checks — existing
- Session isolation with per-session workspaces and idle cleanup — existing
- Security validation (blocked functions, filename sanitization) — existing
- Async job orchestration with sync/async execution paths — existing
- File operations (upload, download, list, read scripts/data/images) — existing
- MATLAB discovery tools (list toolboxes, functions, get help) — existing
- Output formatting with Plotly figure conversion and thumbnails — existing
- Monitoring with metrics collection, SQLite persistence, and HTML dashboard — existing
- Custom tool loading from YAML definitions — existing
- stdio and SSE transport support — existing
- Configuration via YAML with environment variable overrides — existing
- Inspect mode for starting without MATLAB — existing
- ✓ FastMCP 3.2.0 upgrade with all breaking changes resolved — v2.0
- ✓ Bearer token authentication on HTTP transports via ASGI middleware — v2.0
- ✓ Streamable HTTP transport at /mcp with session routing — v2.0
- ✓ Human-in-the-loop approval gates using elicitation API — v2.0
- ✓ Windows 10 no-admin compatibility (127.0.0.1 default, cross-platform CI) — v2.0
- ✓ Agent onboarding docs for Claude Code, Codex CLI, Cursor — v2.0
- ✓ Windows 10 deployment guide — v2.0

### Active

(No active requirements — next milestone not yet defined)

### Out of Scope

- OAuth2/OpenID Connect flows — too complex, token auth is sufficient
- GUI installer — users install via pip, no admin needed
- Mobile/web client — this is a server for AI coding agents
- MATLAB Online/MATLAB Web integration — desktop MATLAB only
- Per-tool scope enforcement — deferred to future version (AAUTH-01)
- Token rotation without restart — deferred to future version (AAUTH-02)

## Context

- Running on FastMCP 3.2.0 with streamable HTTP transport at /mcp
- Bearer token auth via MATLAB_MCP_AUTH_TOKEN env var, BearerAuthMiddleware (ASGI)
- HITL approval gates configurable via config.yaml hitl section (disabled by default)
- Default bind address 127.0.0.1 — avoids Windows Firewall UAC prompts
- Cross-platform CI: Linux, Windows, macOS
- 6,259 LOC Python, 840 unit tests, 1 integration test
- SSE transport deprecated but still functional

## Constraints

- **Tech stack**: Python 3.10+, backward compat with existing config.yaml format
- **Platform**: Works on Windows 10 without admin rights
- **MATLAB**: Requires MATLAB R2022b+ with Engine API

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Token-in-header auth over OAuth | Simple, works with all agents, no redirect flows | ✓ Good — works with Claude Code, Codex CLI, Cursor |
| FastMCP 3.0 upgrade first | Gates auth, transport, and HITL APIs | ✓ Good — 752/755 tests passed on first try |
| Win10 no-admin as hard constraint | Primary user base is corporate/academic | ✓ Good — 127.0.0.1 default avoids UAC |
| Opaque hex tokens over JWT | Simpler, no expiry semantics, static rotation | ✓ Good — 64-char hex via --generate-token |
| ASGI middleware for auth | Clean separation, works before FastMCP | ✓ Good — pure ASGI, no BaseHTTPMiddleware |
| Elicitation API for HITL | FastMCP 3.x native, agent-compatible | ✓ Good — ctx.elicit() works across transports |
| Config "streamablehttp" → FastMCP "streamable-http" | YAML-friendly config value, mapped at call site | ✓ Good — transparent to operators |

---
*Last updated: 2026-04-03 after v2.0 milestone*
