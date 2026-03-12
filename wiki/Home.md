# MATLAB MCP Server Wiki

Welcome to the **MATLAB MCP Server** wiki! This server connects any AI agent to a shared MATLAB installation via the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

## Quick Navigation

- **[[Installation]]** — Prerequisites, MATLAB Engine API, server setup
- **[[Configuration]]** — Full YAML config reference with all options
- **[[MCP Tools Reference]]** — All 14 built-in tools with parameters and examples
- **[[Custom Tools]]** — Expose your own `.m` functions as AI-callable tools
- **[[Examples]]** — Ready-to-run MATLAB examples for common tasks
- **[[Architecture]]** — System design, engine pool, async jobs, session model
- **[[Async Jobs]]** — Long-running jobs, progress reporting, job lifecycle
- **[[Security]]** — Function blocklist, workspace isolation, upload limits
- **[[Troubleshooting]]** — Common issues and solutions
- **[[FAQ]]** — Frequently asked questions

## What is this?

A Python MCP server that gives AI agents (Claude, Cursor, Copilot, custom agents) the ability to:

- **Execute MATLAB code** — sync for fast commands, async for long-running jobs
- **Discover toolboxes** — browse installed toolboxes, functions, and help text
- **Check code quality** — run `checkcode`/`mlint` before execution
- **Get interactive plots** — figures auto-converted to Plotly JSON
- **Use custom libraries** — expose your `.m`/`.mex` functions as first-class MCP tools

## Supported Platforms

| Platform | MATLAB Version | Transport |
|----------|---------------|-----------|
| macOS | 2020b+ | stdio, SSE |
| Windows | 2020b+ | stdio, SSE |

## Getting Help

- [GitHub Issues](https://github.com/HanSur94/matlab-mcp-server-python/issues)
- [README](https://github.com/HanSur94/matlab-mcp-server-python#readme)
