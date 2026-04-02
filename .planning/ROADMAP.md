# Roadmap: MATLAB MCP Server v2.0

## Overview

This milestone upgrades a working MATLAB MCP server from FastMCP 2.x to 3.x, adds bearer token authentication, introduces streamable HTTP transport (fixing Codex CLI connectivity), adds human-in-the-loop approval gates, and hardens the server for Windows 10 no-admin deployment. Phases follow a strict dependency chain: the FastMCP upgrade unblocks auth and transport APIs, auth middleware must exist before it can be wired into transport, HITL uses the elicitation API available only after both are in place, and platform hardening validates the full stack end-to-end before docs ship.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: FastMCP 3.0 Upgrade** - Migrate the server to FastMCP 3.2.0+, resolving all breaking changes so existing tools and tests pass (completed 2026-04-01)
- [ ] **Phase 2: Auth Config + Bearer Token Middleware** - Add env-var-only auth config and implement BearerTokenMiddleware with 401/403 semantics
- [ ] **Phase 3: Streamable HTTP Transport + Session Routing** - Wire streamable HTTP at /mcp, fix session routing for HTTP transport, add --generate-token CLI flag
- [ ] **Phase 4: Human-in-the-Loop Approval** - Add configurable HITL gates for protected functions and file operations using FastMCP 3.0 elicitation API
- [ ] **Phase 5: Windows 10 + Platform Hardening** - Validate and harden the server for Windows 10 no-admin deployment with cross-platform CI
- [ ] **Phase 6: Documentation + Agent Onboarding** - Write Windows deployment guide and agent onboarding docs for Claude Code, Codex CLI, and Cursor

## Phase Details

### Phase 1: FastMCP 3.0 Upgrade
**Goal**: Server runs on FastMCP 3.2.0+ with all breaking changes resolved and all existing capabilities working
**Depends on**: Nothing (first phase)
**Requirements**: FMCP-01, FMCP-02, FMCP-03, FMCP-04, FMCP-05
**Success Criteria** (what must be TRUE):
  1. Server starts without errors after `fastmcp>=3.2.0,<4.0.0` pin is applied
  2. All existing MCP tools (execute_code, check_code, file operations, workspace tools) respond correctly in stdio mode
  3. Monitoring dashboard loads via the migrated `@mcp.custom_route()` pattern
  4. Regression test suite passes end-to-end under FastMCP 3.2.0 with no skipped tests
  5. `from fastmcp import Context` and all updated import paths resolve without ImportError
**Plans**: 2 plans
Plans:
- [x] 01-01-PLAN.md — Upgrade FastMCP dependency to 3.2.0, fix tests, suppress stdio banner
- [x] 01-02-PLAN.md — Migrate monitoring routes from private _additional_http_routes to @mcp.custom_route() (gap closure)

### Phase 2: Auth Config + Bearer Token Middleware
**Goal**: Bearer token authentication is enforced on HTTP/SSE transports via middleware, with tokens sourced exclusively from environment variables
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06
**Success Criteria** (what must be TRUE):
  1. A request with a valid `Authorization: Bearer <token>` header is accepted; without a token it receives HTTP 401 with `WWW-Authenticate` header
  2. Auth token is read only from `MATLAB_MCP_AUTH_TOKEN` env var — not from config.yaml — and a startup warning fires if any token-like value is found in config
  3. stdio transport processes requests without any auth check
  4. CORS headers are present on HTTP responses so browser-based agent UIs can connect
  5. Running `--generate-token` prints a ready-to-use token and the env var snippet to set it
**Plans**: 2 plans
Plans:
- [x] 02-01-PLAN.md — Create BearerAuthMiddleware pure ASGI class with unit tests
- [ ] 02-02-PLAN.md — Wire middleware into server.py, add --generate-token CLI, config token warning

### Phase 3: Streamable HTTP Transport + Session Routing
**Goal**: Agents can connect via streamable HTTP at /mcp with correct per-session workspace isolation, and SSE is kept working but marked deprecated
**Depends on**: Phase 2
**Requirements**: TRNS-01, TRNS-02, TRNS-03, TRNS-04, TRNS-05
**Success Criteria** (what must be TRUE):
  1. Codex CLI connects to the server at `/mcp` using streamable HTTP and executes MATLAB code successfully
  2. Two simultaneous HTTP-transport agents each get an isolated MATLAB workspace (no workspace cross-contamination)
  3. stdio transport continues to work identically to pre-migration behavior
  4. Server started with `transport: sse` logs a deprecation warning on startup
  5. Stateless HTTP mode (`stateless_http=True`) can be enabled via config for load-balancer deployments
**Plans**: 2 plans
Plans:
- [x] 03-01-PLAN.md — Add streamablehttp transport value and stateless_http field to ServerConfig
- [x] 03-02-PLAN.md — Wire streamable HTTP transport into server.py with session routing and SSE deprecation

### Phase 4: Human-in-the-Loop Approval
**Goal**: Operators can configure approval gates that pause dangerous operations until a human confirms, using the FastMCP 3.0 elicitation API
**Depends on**: Phase 3
**Requirements**: HITL-01, HITL-02, HITL-03, HITL-04, HITL-05, HITL-06
**Success Criteria** (what must be TRUE):
  1. Calling a function in the `protected_functions` list causes the agent to receive an elicitation prompt before MATLAB executes anything
  2. File upload, delete, and write operations pause for approval when the HITL file-operations toggle is enabled in config.yaml
  3. Read-only tools (list_toolboxes, get_help, get_workspace) execute immediately with no approval prompt regardless of HITL settings
  4. With all HITL toggles disabled (default), no approval prompts appear and existing behavior is unchanged
  5. HITL configuration (protected functions list, toggles) is present in config.yaml with commented sensible defaults
**Plans**: 2 plans
Plans:
- [ ] 04-01-PLAN.md — HITLConfig model, HumanApproval schema, gate helpers, and unit tests
- [ ] 04-02-PLAN.md — Wire HITL gates into tool impl functions and server.py with integration tests

### Phase 5: Windows 10 + Platform Hardening
**Goal**: Server runs correctly on Windows 10 without admin rights with default loopback binding, and cross-platform validation passes on Win10, macOS, and Linux
**Depends on**: Phase 4
**Requirements**: PLAT-01, PLAT-02, PLAT-03
**Success Criteria** (what must be TRUE):
  1. Server starts on Windows 10 without admin rights, binding to 127.0.0.1 by default, without triggering a Windows Firewall UAC prompt
  2. All MCP tools pass on Windows 10, macOS, and Linux in CI (cross-platform test run exits green)
  3. Changing `bind_address: 0.0.0.0` in config is documented as requiring an admin-created firewall rule, and the default is loopback
**Plans**: [To be planned]

### Phase 6: Documentation + Agent Onboarding
**Goal**: Any developer can follow written guides to deploy the server on Windows 10 without admin rights and connect Claude Code, Codex CLI, or Cursor with minimal friction
**Depends on**: Phase 5
**Requirements**: PLAT-04, PLAT-05
**Success Criteria** (what must be TRUE):
  1. A developer on a restricted Windows 10 machine can complete the deployment guide from pip install to first successful MATLAB tool call without needing admin rights
  2. Connection examples for Claude Code, Codex CLI, and Cursor are present in docs, each showing the exact config needed including `bearer_token_env_var`
  3. All doc examples use the streamable HTTP transport at `/mcp`, not SSE
**Plans**: [To be planned]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. FastMCP 3.0 Upgrade | 2/2 | Complete   | 2026-04-01 |
| 2. Auth Config + Bearer Token Middleware | 1/2 | In Progress|  |
| 3. Streamable HTTP Transport + Session Routing | 2/2 | In Progress|  |
| 4. Human-in-the-Loop Approval | 0/2 | Not started | - |
| 5. Windows 10 + Platform Hardening | 0/TBD | Not started | - |
| 6. Documentation + Agent Onboarding | 0/TBD | Not started | - |
