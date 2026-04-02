# Phase 6: Documentation + Agent Onboarding - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (docs phase — discuss skipped)

<domain>
## Phase Boundary

Write deployment guide for Windows 10 no-admin environments and agent onboarding docs with connection examples for Claude Code, Codex CLI, and Cursor. All examples use streamable HTTP transport at /mcp.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure documentation phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key docs to create:
- Windows 10 deployment guide (pip install → first MATLAB tool call, no admin required)
- Agent connection examples for Claude Code, Codex CLI, and Cursor
- Each example shows exact config including `bearer_token_env_var`
- All examples use streamable HTTP transport at `/mcp`, not SSE

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/` directory exists (has `docs/superpowers/`)
- `config.yaml` — reference for configuration examples
- `src/matlab_mcp/server.py` — CLI flags documentation source
- `pyproject.toml` — package installation metadata

### Integration Points
- `docs/` — New markdown files for guides
- README.md — May need links to new docs

</code_context>

<specifics>
## Specific Ideas

No specific requirements — documentation phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
