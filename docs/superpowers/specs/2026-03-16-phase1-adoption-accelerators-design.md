# Phase 1: Adoption Accelerators — Design Spec

**Date:** 2026-03-16
**Goal:** Lower the barrier to adoption for teams and open-source users by adding Docker support, CI/CD, file download tools, and PyPI publishing.

## 1. Dockerfile + docker-compose

### Dockerfile

- **Base image:** `python:3.12-slim`
- **What's included:** The MCP server Python package and all dependencies
- **What's NOT included:** MATLAB — users must volume-mount their own MATLAB installation
- **Exposed ports:** 8765 (SSE transport), 8766 (monitoring dashboard in stdio mode)
- **Entry point:** `matlab-mcp --transport sse` (SSE is the natural choice for containerized deployment)
- **Health check:** Python-based (`urllib.request`) since `python:3.12-slim` does not include `curl`
- **Build args:** None required — config is via environment variables or mounted config.yaml
- **Layer caching:** Copy `pyproject.toml` first, install deps, then copy source — avoids rebuilding deps on every code change

**Dockerfile structure:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Install third-party deps first for layer caching
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir \
    "fastmcp>=2.0.0,<3.0.0" pydantic pyyaml pillow aiosqlite plotly psutil uvicorn

# Copy source and install the package itself (no-deps since deps are cached above)
COPY src/ ./src/
COPY examples/ ./examples/
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8765 8766
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/health')" || exit 1
ENTRYPOINT ["matlab-mcp"]
CMD ["--transport", "sse"]
```

**Note:** The `/health` route is available when monitoring is enabled (default) and transport is SSE. Both are true for the default container config.

**Key constraint:** The MATLAB Engine API for Python must be accessible inside the container. Users achieve this by either:
- Volume-mounting their MATLAB installation and installing the Engine API into the container's Python
- Building a derived image that includes the Engine API

### docker-compose.yml

```yaml
services:
  matlab-mcp:
    build: .
    ports:
      - "8765:8765"
      - "8766:8766"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./custom_tools.yaml:/app/custom_tools.yaml:ro
      - /usr/local/MATLAB/R2024b:/opt/matlab:ro  # Bind mount — user adjusts path
      - results:/app/results
      - monitoring_data:/app/monitoring
    environment:
      - MATLAB_MCP_SERVER_TRANSPORT=sse
      - MATLAB_MCP_POOL_MAX_ENGINES=4
      - MATLAB_MCP_POOL_MATLAB_ROOT=/opt/matlab   # Must match mounted path
volumes:
  results:
  monitoring_data:
```

### Documentation

Add a "Docker Quickstart" section to the README after the existing "Run it" section, explaining:
1. How to build the image
2. How to mount MATLAB
3. How to pass config via env vars or volume mount
4. Link to docker-compose for full setup

## 2. GitHub Actions CI

### ci.yml — Continuous Integration

**Triggers:** push to `master`, pull requests to `master`

**Jobs:**

1. **lint** (Python 3.12 only)
   - Checkout code
   - Install dependencies: `pip install -e ".[dev]"`
   - Run: `ruff check src/ tests/`

2. **test** (matrix: Python 3.9, 3.12)
   - Checkout code
   - Set up Python (matrix version)
   - Install dependencies: `pip install -e ".[dev,monitoring]"`
   - Run: `pytest tests/ -v --cov=matlab_mcp --cov-report=term-missing`
   - No MATLAB required — tests use mock engine

### publish.yml — PyPI Publishing

**Triggers:** GitHub Release created (tagged `v*`)

**Jobs:**

1. **publish**
   - Checkout code
   - Set up Python 3.12
   - Install build tools: `pip install build twine`
   - Build: `python -m build`
   - Verify: `twine check dist/*` (catches malformed metadata before upload)
   - Publish: Uses PyPI OIDC Trusted Publishing (`pypa/gh-action-pypi-publish@release/v1`) — no long-lived API token secrets needed
   - Requires `permissions: id-token: write` on the job

### README Badges

Add to top of README after the title block:
- CI status badge: `![CI](https://github.com/HanSur94/matlab-mcp-server-python/actions/workflows/ci.yml/badge.svg)`
- PyPI version badge
- Python version badge

## 3. File Download Tools

Three new MCP tools that complement the existing file management tools (`upload_data`, `delete_file`, `list_files`).

### 3.1 `read_script`

**Purpose:** Read MATLAB `.m` files from the session temp directory.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | yes | `.m` file in session temp directory |

**Behavior:**
- Validates filename via `SecurityValidator.sanitize_filename()`
- Extension check is case-insensitive (`.M` files are valid MATLAB scripts)
- Verifies file exists in session temp directory
- Reads file as UTF-8 text
- Truncates at `max_inline_text_length` with a message if exceeded
- Returns error if file extension is not `.m`

**Implementation signature:**
```python
async def read_script_impl(
    filename: str,
    session_temp_dir: str,
    security: SecurityValidator,
    max_inline_text_length: int,  # passed from OutputConfig
) -> dict:
```

**Implementation location:** `src/matlab_mcp/tools/files.py` (alongside existing file tools)
**Registration:** `server.py` alongside existing file tools

### 3.2 `read_data`

**Purpose:** Read data files (`.mat`, `.csv`, `.json`, `.txt`, `.xlsx`) from the session temp directory.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | yes | Data file in session temp directory |
| `format` | string | no | `summary` (default) or `raw` |

**Behavior by file type and format:**

| File type | `summary` mode | `raw` mode |
|-----------|---------------|------------|
| `.mat` | Runs MATLAB `whos('-file', path)` with `fprintf` loop to show variable names, sizes, and types in tabular format | Returns base64-encoded file content |
| `.csv`, `.txt`, `.json` | Returns text content (truncated at limit) | Returns text content (truncated at limit) |
| `.xlsx` | Returns base64 (not human-readable as text) | Returns base64 |

**Implementation notes:**
- `.mat` summary mode uses `executor.execute(session_id, code)` — NOT direct pool access. The MATLAB code uses a `fprintf` loop over the `whos('-file', '<path>')` struct array to produce clean tabular output (name, size, class per variable). This follows the same pattern as all existing tools.
- Text files use UTF-8 decoding with fallback to latin-1
- All filenames go through `sanitize_filename()`
- Size check against `max_upload_size_mb` before reading into memory
- `.xlsx` is returned as base64 only — no text preview (would require `openpyxl` which is not a dependency)

**Implementation signature:**
```python
async def read_data_impl(
    filename: str,
    format: str,            # "summary" or "raw"
    session_temp_dir: str,
    security: SecurityValidator,
    max_size_mb: int,       # from SecurityConfig
    max_inline_text_length: int,  # from OutputConfig
    executor: JobExecutor,  # needed for .mat summary
    session_id: str,        # needed for executor.execute()
) -> dict:
```

**Implementation location:** `src/matlab_mcp/tools/files.py`

### 3.3 `read_image`

**Purpose:** Read image files from the session temp directory and return them as MCP Image content blocks.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | yes | Image file in session temp directory |

**Behavior:**
- Supported raster extensions: `.png`, `.jpg`, `.jpeg`, `.gif`
- SVG excluded — Pillow can't process it and most MCP clients won't render SVG inline
- Returns FastMCP `Image` content type using `from fastmcp.utilities.types import Image`
- Agent UIs (Claude Desktop, Cursor) render the image inline
- Returns a single `Image` object (full resolution). No separate thumbnail — let the agent UI handle scaling. This avoids the ambiguity of returning multiple content blocks.
- Validates filename, checks existence, checks file size against `max_upload_size_mb`

**MIME type mapping:**
| Extension | MIME type |
|-----------|----------|
| `.png` | `image/png` |
| `.jpg`, `.jpeg` | `image/jpeg` |
| `.gif` | `image/gif` |

**Implementation signature:**
```python
async def read_image_impl(
    filename: str,
    session_temp_dir: str,
    security: SecurityValidator,
    max_size_mb: int,
) -> Image:  # from fastmcp.utilities.types import Image
```

**Implementation location:** `src/matlab_mcp/tools/files.py`

### Tool count update

These 3 new tools bring the total from 17 to 20 built-in tools. Documentation (README, wiki) must be updated accordingly.

## 4. PyPI Publishing Setup

### pyproject.toml changes

```toml
[project]
name = "matlab-mcp-python"
version = "1.0.0"
description = "MCP server exposing MATLAB capabilities to AI agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.9"
authors = [
    { name = "Hannes Suhr", email = "..." },
]
keywords = ["matlab", "mcp", "model-context-protocol", "ai", "agent"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Scientific/Engineering",
    "Topic :: Software Development :: Libraries",
]

[project.urls]
Homepage = "https://github.com/HanSur94/matlab-mcp-server-python"
Repository = "https://github.com/HanSur94/matlab-mcp-server-python"
Issues = "https://github.com/HanSur94/matlab-mcp-server-python/issues"
Wiki = "https://github.com/HanSur94/matlab-mcp-server-python/wiki"
```

### Versioning strategy

- Single source of truth: `version` field in `pyproject.toml`
- Semantic versioning: `MAJOR.MINOR.PATCH`
- Start at `1.0.0` since the server is feature-complete and stable
- Publish workflow reads version from the built package automatically

### Install experience

```bash
pip install matlab-mcp-python
matlab-mcp --help        # CLI available immediately
matlab-mcp               # Start in stdio mode
matlab-mcp --transport sse  # Start in SSE mode
```

## Files to create/modify

### New files
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore` (excludes: `.git`, `tests/`, `docs/`, `wiki/`, `logs/`, `temp/`, `results/`, `monitoring/`, `__pycache__`, `*.pyc`, `.env`, `.venv`, `.ruff_cache`, `.pytest_cache`, `.claude/`)
- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`

### Modified files
- `pyproject.toml` — name, version, metadata, classifiers, urls
- `src/matlab_mcp/server.py` — register 3 new tools
- `src/matlab_mcp/tools/files.py` — implement `read_script`, `read_data`, `read_image`
- `README.md` — Docker quickstart, badges, updated tool count (17→20), new tools in reference table
- `wiki/Home.md` — tool count update
- `wiki/MCP-Tools-Reference.md` — add File Download section with 3 new tools
- `wiki/Architecture.md` — tool count update
- `wiki/SETUP_WIKI.md` — tool count update

## Testing

### New tests (in `tests/test_files.py` or extending existing)
- `test_read_script_success` — reads .m file, returns text
- `test_read_script_not_found` — file doesn't exist
- `test_read_script_invalid_extension` — rejects non-.m files
- `test_read_script_path_traversal` — rejects `../../etc/passwd`
- `test_read_script_truncation` — large file truncated at limit
- `test_read_data_csv_summary` — reads CSV as text
- `test_read_data_csv_raw` — reads CSV as text (same)
- `test_read_data_mat_summary` — mocks `executor.execute()` to return whos output (no live MATLAB needed)
- `test_read_data_mat_raw` — returns base64
- `test_read_data_not_found` — file doesn't exist
- `test_read_image_png` — returns Image content block
- `test_read_image_jpg` — returns Image content block
- `test_read_image_not_found` — file doesn't exist
- `test_read_image_invalid_extension` — rejects non-image files

### CI tests
- Verify ci.yml runs lint + test successfully
- Verify publish.yml builds the package (dry-run)

## Migration note

The package name changes from `matlab-mcp-server` (current `pyproject.toml`) to `matlab-mcp-python`. Users who installed from the current source should uninstall the old name first:
```bash
pip uninstall matlab-mcp-server
pip install matlab-mcp-python
```
The README Docker Quickstart and upgrade notes should call this out.

## Out of scope
- Built-in authentication (Phase 2)
- Rate limiting (Phase 2)
- MCP Resources (Phase 3)
- MCP Prompts (Phase 3)
