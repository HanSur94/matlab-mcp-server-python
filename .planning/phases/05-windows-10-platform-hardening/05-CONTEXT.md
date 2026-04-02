# Phase 5: Windows 10 + Platform Hardening - Context

**Gathered:** 2026-04-02
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Server runs correctly on Windows 10 without admin rights with default loopback binding. Cross-platform validation passes on Win10, macOS, and Linux. Default bind address is 127.0.0.1 to avoid Windows Firewall UAC prompts.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure/hardening phase. Use ROADMAP phase goal, success criteria, and codebase conventions to guide decisions.

Key areas to address:
- Default bind address change from 0.0.0.0 to 127.0.0.1 in ServerConfig
- Cross-platform path handling (os.path vs pathlib)
- Platform-specific test markers or skips
- CI configuration for cross-platform testing (if applicable)
- Documentation of 0.0.0.0 bind requiring admin firewall rule

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/matlab_mcp/config.py` — ServerConfig with `host: str = "0.0.0.0"` (needs change to 127.0.0.1)
- `src/matlab_mcp/server.py` — main() with transport selection, host/port binding
- `src/matlab_mcp/session/manager.py` — temp dir management (may need Windows path fixes)
- `pyproject.toml` — test configuration

### Integration Points
- `config.py::ServerConfig.host` — default value change
- `server.py` — startup logging, bind address display
- Test suite — cross-platform compatibility

</code_context>

<specifics>
## Specific Ideas

No specific requirements — infrastructure phase.

</specifics>

<deferred>
## Deferred Ideas

None.

</deferred>
