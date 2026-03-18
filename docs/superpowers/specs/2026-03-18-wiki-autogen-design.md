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

**Page mapping (explicit file lists, no globs):**

| Wiki Page | Source Files | Truncation |
|-----------|-------------|------------|
| Home | README.md, pyproject.toml | 12000, 4000 |
| Installation | README.md, pyproject.toml, Dockerfile, docker-compose.yml | 12000, 4000, 4000, 4000 |
| Configuration | config.yaml, src/matlab_mcp/config.py | 8000, 8000 |
| Architecture | src/matlab_mcp/server.py, src/matlab_mcp/pool/manager.py, src/matlab_mcp/pool/engine.py, src/matlab_mcp/jobs/executor.py, src/matlab_mcp/session/manager.py, src/matlab_mcp/output/formatter.py | 6000 each |
| MCP-Tools-Reference | src/matlab_mcp/server.py (AST extraction — no truncation, uses structured metadata) | N/A |
| Async-Jobs | src/matlab_mcp/jobs/executor.py, src/matlab_mcp/jobs/models.py, src/matlab_mcp/jobs/tracker.py | 6000 each |
| Custom-Tools | custom_tools.yaml, examples/custom_tools.yaml, src/matlab_mcp/tools/custom.py | 4000 each |
| Security | src/matlab_mcp/security/validator.py, config.yaml | 6000, 4000 |
| Examples | examples/basic_usage.m, examples/async_simulation.m, examples/plotting_examples.m, examples/signal_processing.m | 4000 each |
| FAQ | README.md | 12000 |
| Troubleshooting | README.md, config.yaml | 12000, 4000 |

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

**Source file truncation:** Per-file truncation limits are specified in the page mapping above. README.md gets 12000 chars (vs default 4000) for pages where it's the primary source.

**Missing source files:** If a source file does not exist, log a warning and skip it. Continue generating the page with the remaining source files. If ALL source files for a page are missing, skip the page entirely.

**Model:** `claude-haiku-4-5` (same as current). `max_tokens: 8000` per page. Retry logic: 2 retries with exponential backoff per page (same as current).

**Output validation:** Before writing a generated page to disk, verify:
- Output is non-empty
- Output does not start with known refusal patterns ("I'm sorry", "I cannot", "I apologize")
If validation fails, keep the existing page content and log a warning.

**Error handling:** If a page generation fails (after retries) or validation fails, log the error and continue to the next page. The script exits non-zero if ANY page fails, so CI surfaces the problem.

### 2. Update `docs.yml` workflow

Change the wiki push step to copy **all** wiki markdown files and use explicit `git add *.md` (not `-A`) to avoid accidentally staging non-markdown files:

```bash
cp wiki/*.md /tmp/wiki/
git add *.md
git commit -m "docs: auto-update wiki"
```

Note: this intentionally overwrites any manual edits made directly to the wiki repo. The `wiki/` directory in the main repo is the source of truth.

### 3. No other changes

- `docs.yml` trigger, concurrency, secrets — unchanged
- `generate_changelog.py` — unchanged
- All other workflows — unchanged

## Files Modified

| File | Changes |
|------|---------|
| `scripts/generate_docs.py` | Rewrite to handle all 11 pages |
| `.github/workflows/docs.yml` | Copy all wiki/*.md files, use `git add *.md` |

## Cost

~11 Haiku API calls per push to master. At ~$0.07 per call, roughly $0.75 per run.
