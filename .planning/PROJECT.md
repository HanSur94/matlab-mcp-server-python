# MATLAB MCP Server — v2.0 Milestone

## What This Is

A Python-based MCP server that lets AI coding agents (Claude Code, Codex CLI, etc.) execute MATLAB code, inspect workspaces, manage files, and monitor server health. It bridges the Model Context Protocol to MATLAB's Engine API with elastic pooling, session isolation, and async job orchestration.

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

### Active

- [ ] Built-in token/API-key authentication for SSE/HTTP transport
- [ ] Upgrade from FastMCP 2.x to FastMCP 3.0
- [ ] Streamable HTTP transport (FastMCP 3.0 feature)
- [ ] Easy agent onboarding — any MCP-compatible agent connects with minimal config
- [ ] Windows 10 no-admin compatibility for all features
- [ ] Production-hardened multi-user deployment
- [ ] Cross-platform testing (Win10, macOS, Linux)

### Out of Scope

- OAuth2/OpenID Connect flows — too complex for v2, token auth is sufficient
- GUI installer — users install via pip, no admin needed
- Mobile/web client — this is a server for AI coding agents
- MATLAB Online/MATLAB Web integration — desktop MATLAB only

## Context

- Currently on FastMCP 2.14.5 with `<3.0.0` upper bound
- SSE transport has a `require_proxy_auth` flag but no built-in auth — relies entirely on reverse proxy
- Codex CLI had authentication failures trying to connect over SSE — the setup was too complex
- stdio works for single-user but doesn't support multi-agent or remote scenarios
- Docker support exists via docker-compose.yml
- The server targets corporate/academic environments where users often lack admin rights on Windows

## Constraints

- **Tech stack**: Python 3.10+, must keep backward compat with existing config.yaml format
- **Platform**: Must work on Windows 10 without admin rights (no service installation, no elevated ports)
- **Dependency**: FastMCP 3.0 migration must not break existing stdio/SSE clients
- **MATLAB**: Requires MATLAB R2022b+ with Engine API — this is an external user dependency

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Token-in-header auth over OAuth | Simple, works with all agents, no redirect flows needed | — Pending |
| FastMCP 3.0 upgrade | Access to streamable HTTP, built-in auth support, modern protocol features | — Pending |
| Win10 no-admin as hard constraint | Primary user base is corporate/academic with restricted machines | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? Move to Out of Scope with reason
2. Requirements validated? Move to Validated with phase reference
3. New requirements emerged? Add to Active
4. Decisions to log? Add to Key Decisions
5. "What This Is" still accurate? Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-01 after initialization*
