# Milestones

## v2.0 MATLAB MCP Server v2.0 (Shipped: 2026-04-03)

**Phases completed:** 6 phases, 12 plans, 9 tasks

**Key accomplishments:**

- One-liner:
- Monitoring dashboard routes migrated from private mcp._additional_http_routes to @mcp.custom_route() public API, closing the FMCP-03 verification gap with 755 tests passing.
- One-liner:
- One-liner:
- Pydantic ServerConfig extended with `"streamablehttp"` transport value and `stateless_http: bool = False` field, gating Plan 02's server.py transport branch
- `src/matlab_mcp/server.py`
- One-liner:
- HITL approval gates wired into execute_code_impl, upload_data_impl, and delete_file_impl with ctx/hitl_config forwarded from server.py tool handlers
- Default bind address changed to 127.0.0.1, SessionManager temp dir fixed to use tempfile.gettempdir(), and Windows non-loopback startup warning added
- GitHub Actions test-macos job added, completing the Linux + Windows + macOS cross-platform CI triad required by PLAT-03
- Comprehensive 454-line no-admin Windows 10 deployment guide covering pip install through first MATLAB tool call, with explicit 127.0.0.1-vs-0.0.0.0 firewall guidance and streamablehttp transport throughout
- Copy-pasteable MCP connection configs for Claude Code, Codex CLI, and Cursor over streamable HTTP with bearer token auth

---
