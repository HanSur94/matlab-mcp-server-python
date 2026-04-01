# Phase 1: FastMCP 3.0 Upgrade - Context

**Gathered:** 2026-04-01
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Server runs on FastMCP 3.2.0+ with all breaking changes resolved and all existing capabilities working. This is a pure migration/upgrade phase — no new user-facing features, only framework version bump and API compatibility fixes.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key migration areas to address:
- FastMCP dependency pin: `fastmcp>=2.0.0,<3.0.0` → `fastmcp>=3.2.0,<4.0.0`
- Import path changes (e.g., `from fastmcp import Context`)
- Tool registration API changes (decorator signatures, parameter types)
- Custom route API for monitoring dashboard (`@mcp.custom_route()`)
- Lifespan management changes
- Any breaking changes in MCP protocol types or context objects

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/matlab_mcp/server.py` — Main server with `create_server()` factory, tool registration (lines 391-679), lifespan (lines 158-363)
- `src/matlab_mcp/config.py` — Pydantic config models, `load_config()`
- `src/matlab_mcp/monitoring/dashboard.py` — Starlette-based HTTP dashboard (uses custom routes)
- `src/matlab_mcp/tools/` — All tool implementations (core, discovery, files, jobs, admin, custom, monitoring)

### Established Patterns
- FastMCP 2.x decorator-based tool registration
- `MatlabMCPServer` state container passed via server context
- Async-first design with `async def` tool handlers
- Background tasks launched in lifespan context manager

### Integration Points
- `pyproject.toml` — dependency pin must change
- `requirements-lock.txt` — pinned versions must be regenerated
- All `import fastmcp` and `from fastmcp import ...` statements
- All `@mcp.tool()` decorator usages
- Dashboard custom route registration
- Entry point: `matlab-mcp = "matlab_mcp.server:main"`

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase. Refer to ROADMAP phase description and success criteria.

</specifics>

<deferred>
## Deferred Ideas

None — infrastructure phase.

</deferred>
