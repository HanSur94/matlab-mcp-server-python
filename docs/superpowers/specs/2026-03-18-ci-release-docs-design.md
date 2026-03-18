# CI, Release & LLM-Powered Docs Pipeline — Design Spec

**Date:** 2026-03-18
**Status:** Approved
**Project:** matlab-mcp-server-python

## Overview

Add a comprehensive CI/CD pipeline with modular GitHub Actions workflows covering testing, security, build verification, Docker validation, LLM-powered MCP tool documentation generation, and semi-automated releases with AI-generated changelogs.

## Architecture: Modular Workflows

Four separate workflow files, each with a clear responsibility:

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| CI | `ci.yml` | Push to master, PRs | Lint, test, security, build, Docker |
| Docs | `docs.yml` | Push to master | LLM-generated MCP tool reference |
| Release | `release.yml` | Tag push `v*` | Draft release with LLM changelog |
| Publish | `publish.yml` | Release published | PyPI publish (existing, unchanged) |

## Workflow 1: CI Pipeline (`ci.yml`)

### Trigger
- Push to `master`
- Pull requests targeting `master`

### Jobs

#### 1. lint
- **Runner:** ubuntu-latest, Python 3.12
- **Steps:** Install dev deps, run `ruff check src/ tests/`

#### 2. test
- **Runner:** ubuntu-latest, matrix Python 3.10 + 3.12
- **Steps:** Install dev + monitoring deps, run `pytest tests/ -v --cov=matlab_mcp --cov-report=xml --cov-report=term-missing`
- **Post:** Upload coverage XML to Codecov using `codecov/codecov-action@v4`
- **Needs:** lint

#### 3. security
- **Runner:** ubuntu-latest, Python 3.12
- **Steps:** Install project deps, run `pip-audit` to scan for known vulnerabilities
- **Needs:** lint

#### 4. build
- **Runner:** ubuntu-latest, Python 3.12
- **Steps:** `python -m build`, `twine check dist/*`, upload dist as artifact
- **Needs:** test

#### 5. docker
- **Runner:** ubuntu-latest
- **Steps:** `docker build -t matlab-mcp:test .`, run container with `MATLAB_MCP_MONITORING_ENABLED=true` and `MATLAB_MCP_SERVER_TRANSPORT=sse`, wait for health check (`curl --retry 10 --retry-delay 3 --retry-connrefused http://localhost:8765/health`), stop container
- **Needs:** lint (runs in parallel with test to reduce wall-clock time)

## Workflow 2: Docs Generation (`docs.yml`)

### Trigger
- Push to `master`

### Concurrency
`concurrency: { group: docs-${{ github.ref }}, cancel-in-progress: true }` — prevents parallel doc generation from rapid pushes.

### Job: generate-docs

**Runner:** ubuntu-latest, Python 3.12

**Steps:**
1. Checkout main repo
2. Install project dependencies + `anthropic` SDK
3. Run `scripts/generate_docs.py`
4. Clone the GitHub Wiki repo (`HanSur94/matlab-mcp-server-python.wiki.git`)
5. Copy generated `wiki/MCP-Tools-Reference.md` to wiki repo
6. If diff exists, commit and push to wiki repo

**Wiki push authentication:** Requires a Personal Access Token (PAT) with `repo` scope stored as `WIKI_PAT` secret. `GITHUB_TOKEN` cannot push to the wiki repo (it's a separate git repository). The PAT is used as the git credential when cloning and pushing to the wiki repo.

### Script: `scripts/generate_docs.py`

**Purpose:** Extract MCP tool metadata from source code and generate comprehensive tool reference documentation via Claude API.

**Process:**
1. **AST Parsing:** Use Python's `ast` module to parse `src/matlab_mcp/server.py` for functions decorated with `@mcp.tool`. These wrapper functions define the actual MCP-visible tool names, docstrings, and parameter signatures exposed to clients. Do NOT parse the `_impl` functions in `tools/*.py` — those contain internal parameters (executor, tracker, session_id, etc.) that are not visible to MCP clients.
   - **Excluded:** Custom tools (registered dynamically from YAML at runtime). The generated docs will note that custom tools are configured via `custom_tools.yaml`.
   - Extract: function name, decorator info, docstring, parameters (name, type annotation, default), return type
2. **Build payload:** Structure extracted metadata as JSON with tool categories:
   - Execution & Workspace (execute_code, check_code, get_workspace)
   - Job Management (get_job_status, get_job_result, cancel_job, list_jobs)
   - Discovery (list_toolboxes, list_functions, get_help)
   - File Operations (upload_data, read_script, read_data, read_image, delete_file, list_files)
   - Admin (get_pool_status)
   - Monitoring (get_server_metrics, get_server_health, get_error_log)
3. **Read existing content:** Load `wiki/MCP-Tools-Reference.md` from the main repo checkout as style reference (not from the wiki clone)
4. **Call Claude API:** Send metadata + style reference to `claude-haiku-4-5` with prompt:
   - "Generate a comprehensive MCP Tools Reference in markdown for the matlab-mcp-server"
   - "For each tool: name, description, parameters table (name, type, required, default, description), return value description, usage example"
   - "Group tools by category. Match the style of the existing reference."
5. **Write output:** Save to `wiki/MCP-Tools-Reference.md`

**Model choice:** `claude-haiku-4-5` — cost-efficient for structured data transformation. Tool reference generation is a well-constrained task that doesn't require Opus-level reasoning.

**Error handling:** If API call fails, the workflow fails (no partial writes). Retry up to 2 times with backoff. API client timeout set to 60 seconds to prevent hung calls from consuming runner minutes.

## Workflow 3: Release Pipeline (`release.yml`)

### Trigger
- Push of tags matching `v*` (e.g., `v1.1.0`)

### Job: draft-release

**Permissions:** `contents: write` (required for `gh release create`)

**Runner:** ubuntu-latest, Python 3.12

**Steps:**
1. Checkout with full history (`fetch-depth: 0`)
2. Install `anthropic` SDK + `build` package (`pip install anthropic build`)
3. Run `scripts/generate_changelog.py` — outputs changelog to `CHANGELOG.md` (temp)
4. Build wheel + sdist with `python -m build`
5. Create draft GitHub release with artifacts: `gh release create $TAG --draft --title "$TAG" --notes-file CHANGELOG.md dist/*`

### Script: `scripts/generate_changelog.py`

**Purpose:** Generate human-readable release notes from git history using Claude API.

**Process:**
1. **Get commits:** Find the most recent previous tag via `git tag --sort=-creatordate`. If tags exist, run `git log <prev_tag>..HEAD --format="%H|%s|%an|%ad"`. If no previous tags exist (first release), fall back to `git log HEAD --format="%H|%s|%an|%ad"` to include all commits.
2. **Parse commits:** Group by conventional commit prefix (feat, fix, docs, ci, refactor, test, chore). Truncate individual commit messages to 500 characters to prevent oversized API payloads.
3. **Call Claude API:** Send parsed commits to `claude-haiku-4-5` (timeout: 60s) with prompt:
   - "Write concise release notes from these commits"
   - "Sections: Highlights (1-2 sentence summary), New Features, Bug Fixes, Documentation, Other Changes"
   - "Use bullet points, be concise, focus on user impact"
4. **Write output:** Save to `CHANGELOG.md`

**Edge case:** If no previous tag exists (first release), include all commits.

## Workflow 4: Publish (`publish.yml`)

**Unchanged.** Existing workflow triggers on GitHub release published, builds and publishes to PyPI via OIDC.

## README Badge Updates

Add/update badges at the top of `README.md`:

```markdown
[![CI](https://github.com/HanSur94/matlab-mcp-server-python/actions/workflows/ci.yml/badge.svg)](https://github.com/HanSur94/matlab-mcp-server-python/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/HanSur94/matlab-mcp-server-python/branch/master/graph/badge.svg)](https://codecov.io/gh/HanSur94/matlab-mcp-server-python)
[![PyPI](https://img.shields.io/pypi/v/matlab-mcp-python)](https://pypi.org/project/matlab-mcp-python/)
[![Python](https://img.shields.io/pypi/pyversions/matlab-mcp-python)](https://pypi.org/project/matlab-mcp-python/)
[![License](https://img.shields.io/github/license/HanSur94/matlab-mcp-server-python)](https://github.com/HanSur94/matlab-mcp-server-python/blob/master/LICENSE)
```

Existing badges will be deduplicated — no duplicates.

## New Files

| File | Purpose |
|------|---------|
| `scripts/generate_docs.py` | AST-based tool extraction + Claude API doc generation |
| `scripts/generate_changelog.py` | Git log parsing + Claude API changelog generation |
| `.github/workflows/docs.yml` | Docs generation workflow |
| `.github/workflows/release.yml` | Semi-automated release workflow |

## Modified Files

| File | Changes |
|------|---------|
| `.github/workflows/ci.yml` | Add security, build, docker, codecov jobs |
| `README.md` | Add/update badges |
| `pyproject.toml` | Add `pip-audit` and `build` to dev dependencies; fix ruff `target-version` from `py39` to `py310` to match `requires-python` |

## Secrets Required

| Secret | Purpose | Where to set |
|--------|---------|--------------|
| `ANTHROPIC_API_KEY` | Claude API for docs + changelog | GitHub repo settings → Secrets |
| `WIKI_PAT` | PAT with `public_repo` scope for pushing to wiki repo (use `repo` scope if private) | GitHub repo settings → Secrets |
| `CODECOV_TOKEN` | Coverage upload (required for Codecov v4 action) | GitHub repo settings → Secrets |

## Cost Considerations

- **Claude API:** Using Haiku model for both docs and changelog generation. Expected cost per run: ~$0.01-0.05 (small input/output for structured tasks).
- **GitHub Actions:** All jobs use ubuntu-latest. Expected CI time: ~5-8 minutes per push. Docker build adds ~2-3 minutes.

## Dependencies Added

- `pip-audit` — vulnerability scanning (dev dependency)
- `build` — PEP 517 build frontend (dev dependency)
- `anthropic` — Claude API SDK (used in scripts only, not a project dependency; installed in CI via pip)
