# Phase 4: Human-in-the-Loop Approval - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Configurable HITL approval gates using FastMCP 3.0 elicitation API. Protected functions and file operations pause for human approval before execution. Disabled by default — operators opt-in via config.

</domain>

<decisions>
## Implementation Decisions

### Elicitation API Usage
- Use `ctx.elicit(HumanApproval)` where `HumanApproval` is a Pydantic model with `approved: bool` field
- On denial: return error dict `{"status": "denied", "message": "Operation blocked by HITL approval"}` — do not execute
- No server-side timeout — wait indefinitely (agent/client decides timeout)
- Approval message: show function name, code snippet (first 200 chars), and reason for gate

### Config Structure
- New `hitl` section in config.yaml: `enabled: false`, `protected_functions: [...]`, `protect_file_ops: false`
- Default protected functions list: empty (all disabled by default — operators opt-in)
- Config model: `HITLConfig` in config.py as Pydantic BaseModel
- Env var override: `MATLAB_MCP_HITL_ENABLED=true` — standard prefix pattern

### Implementation Scope
- Intercept inside `execute_code_impl()` and file tool impl functions — check before execution
- Per-call approval — each dangerous call prompts independently
- Audit logging: log all approvals/denials at INFO level with function name and session
- File operations that trigger: `upload_data`, `delete_file` — write operations only (not read_script/read_data/list_files)

### Claude's Discretion
- Internal module organization for HITL logic
- Exact Pydantic model field structure for elicitation
- Test mocking approach for elicitation API

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/matlab_mcp/security/validator.py` — SecurityValidator with blocked function regex patterns
- `src/matlab_mcp/tools/core.py` — `execute_code_impl()` where HITL check inserts
- `src/matlab_mcp/tools/files.py` — `upload_data_impl()`, `delete_file_impl()` where file HITL checks insert
- `src/matlab_mcp/config.py` — Pydantic config models, env var override system

### Established Patterns
- Security checks in `execute_code_impl()` via `SecurityValidator.check_code()`
- Config sections as Pydantic BaseModel classes
- `from fastmcp.server.context import Context` for ctx access in tool handlers
- Tool handlers receive ctx as first parameter

### Integration Points
- `config.py` — Add `HITLConfig` model and wire into `AppConfig`
- `tools/core.py::execute_code_impl()` — Add HITL check after security check
- `tools/files.py` — Add HITL check in `upload_data_impl()` and `delete_file_impl()`
- `server.py::create_server()` — Pass HITL config through to tool handlers

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
