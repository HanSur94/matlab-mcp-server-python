# Full Wiki Auto-Generation — Design Spec

**Date:** 2026-03-18
**Status:** Approved
**Project:** matlab-mcp-server-python

## Overview

Extend the existing docs generation pipeline to auto-update all 11 wiki pages (not just MCP-Tools-Reference) on every push to master. Each page is seeded from its existing content and updated using relevant source files as context via Claude Haiku.

## Changes

### 1. Rewrite `scripts/generate_docs.py`

Replace the single-page generation with a multi-page system:

- **Page definitions:** A Python dict mapping each wiki page to its source files and a generation prompt.
- **Generation loop:** For each page, read source files + existing wiki page, call Claude Haiku, write output.
- **MCP-Tools-Reference:** Keeps the existing AST extraction logic as a special case (structured metadata extraction before the API call).
- **All other pages:** Read source files as raw text, send to Claude with the existing page as seed.

**Page mapping:**

| Wiki Page | Source Files |
|-----------|-------------|
| Home | README.md, pyproject.toml |
| Installation | README.md, pyproject.toml, Dockerfile, docker-compose.yml |
| Configuration | config.yaml, src/matlab_mcp/config.py |
| Architecture | src/matlab_mcp/**/__init__.py, src/matlab_mcp/server.py |
| MCP-Tools-Reference | src/matlab_mcp/server.py (AST extraction) |
| Async-Jobs | src/matlab_mcp/jobs/executor.py, src/matlab_mcp/jobs/models.py, src/matlab_mcp/jobs/tracker.py |
| Custom-Tools | custom_tools.yaml, examples/custom_tools.yaml, src/matlab_mcp/tools/custom.py |
| Security | src/matlab_mcp/security/validator.py, config.yaml |
| Examples | examples/*.m |
| FAQ | README.md |
| Troubleshooting | README.md, config.yaml |

**Excluded:** SETUP_WIKI.md (internal setup instructions, not user-facing).

**Per-page prompt pattern:**
```
Update the following wiki page for the matlab-mcp-server project.
Keep the existing structure and tone. Update content to match the current source code.
Do not remove sections unless the feature no longer exists.
Add new sections if the source code reveals undocumented features.

Existing page:
<existing content>

Source code context:
<source files>

Output ONLY the updated markdown.
```

**Source file truncation:** Each source file is truncated to 4000 chars to stay within Haiku's context limits. Total context per page: ~existing page + ~4000 * N source files.

**Model:** `claude-haiku-4-5` (same as current). `max_tokens: 8000` per page.

**Error handling:** If one page fails, log the error and continue to the next page. The script exits with error only if ALL pages fail.

### 2. Update `docs.yml` workflow

Change the wiki push step to copy **all** wiki markdown files instead of just one:

```bash
cp wiki/*.md /tmp/wiki/
git add -A
git commit -m "docs: auto-update wiki pages"
```

### 3. No other changes

- `docs.yml` trigger, concurrency, secrets — unchanged
- `generate_changelog.py` — unchanged
- All other workflows — unchanged

## Files Modified

| File | Changes |
|------|---------|
| `scripts/generate_docs.py` | Rewrite to handle all 11 pages |
| `.github/workflows/docs.yml` | Copy all wiki/*.md files, not just one |

## Cost

~11 Haiku API calls per push to master. At ~$0.01-0.05 per call, roughly $0.10-0.50 per run.
