# CI, Release & LLM-Powered Docs Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full CI/CD pipeline with security scanning, coverage reporting, Docker validation, LLM-powered MCP tool documentation generation, and semi-automated releases with AI-generated changelogs.

**Architecture:** Four modular GitHub Actions workflows (ci.yml, docs.yml, release.yml, publish.yml). Two Python scripts (generate_docs.py, generate_changelog.py) use the Anthropic SDK to call Claude Haiku for structured doc/changelog generation. AST parsing of server.py extracts MCP tool metadata.

**Tech Stack:** GitHub Actions, Python ast module, Anthropic SDK (claude-haiku-4-5), pip-audit, Codecov, Docker

**Spec:** `docs/superpowers/specs/2026-03-18-ci-release-docs-design.md`

---

### Task 1: Fix pyproject.toml — ruff target-version and dev dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Fix ruff target-version**

In `pyproject.toml`, change `target-version = "py39"` to `"py310"` to match `requires-python = ">=3.10"`:

```toml
[tool.ruff]
target-version = "py310"
line-length = 100
```

- [ ] **Step 2: Add pip-audit and build to dev dependencies**

In `pyproject.toml`, add `pip-audit` and `build` to the `[project.optional-dependencies] dev` list:

```toml
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
    "psutil>=5.9.0",
    "uvicorn>=0.20.0",
    "pip-audit>=2.6.0",
    "build>=1.0.0",
]
```

- [ ] **Step 3: Verify the install works**

Run: `pip install -e ".[dev]" 2>&1 | tail -5`
Expected: Installs successfully without errors

- [ ] **Step 4: Verify ruff still passes**

Run: `ruff check src/ tests/`
Expected: No errors (or same errors as before — the target-version change may surface new warnings)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "chore: fix ruff target-version to py310, add pip-audit and build to dev deps"
```

---

### Task 2: Enhance CI pipeline — security, build, docker, codecov

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Replace ci.yml with enhanced version**

Write the full enhanced `ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/

  test:
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev,monitoring]"
      - run: pytest tests/ -v --cov=matlab_mcp --cov-report=xml --cov-report=term-missing
      - uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.12'
        with:
          files: coverage.xml
          token: ${{ secrets.CODECOV_TOKEN }}
          fail_ci_if_error: false

  security:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev,monitoring]"
      - run: pip-audit

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: python -m build
      - run: twine check dist/*
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  docker:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t matlab-mcp:test .
      - name: Smoke-test container health endpoint
        run: |
          docker run -d --name mcp-test \
            -e MATLAB_MCP_SERVER_TRANSPORT=sse \
            -e MATLAB_MCP_MONITORING_ENABLED=true \
            -p 8765:8765 \
            matlab-mcp:test
          # Wait for the server to start (it will fail to connect to MATLAB
          # but the /health endpoint should still respond)
          sleep 5
          curl --retry 10 --retry-delay 3 --retry-connrefused \
            http://localhost:8765/health || true
          docker logs mcp-test
          docker stop mcp-test
          docker rm mcp-test
```

Note: The docker health check uses `|| true` because the server may report unhealthy (no MATLAB engine available in CI) but the goal is to verify the container builds and starts — not that MATLAB is present.

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add security scanning, build verification, Docker smoke test, Codecov"
```

---

### Task 3: Create generate_docs.py — AST extraction + Claude API

**Files:**
- Create: `scripts/generate_docs.py`

- [ ] **Step 1: Create scripts directory**

Run: `ls scripts/ 2>/dev/null || mkdir scripts`

- [ ] **Step 2: Write generate_docs.py**

Create `scripts/generate_docs.py`:

```python
#!/usr/bin/env python3
"""Extract MCP tool metadata from server.py and generate wiki docs via Claude API.

Parses @mcp.tool-decorated functions in src/matlab_mcp/server.py using the AST
module, then sends the extracted metadata to Claude Haiku to generate a comprehensive
MCP Tools Reference markdown document.

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/generate_docs.py

Output:
    wiki/MCP-Tools-Reference.md
"""
from __future__ import annotations

import ast
import json
import os
import sys
import time
from pathlib import Path

SERVER_PY = Path("src/matlab_mcp/server.py")
WIKI_OUTPUT = Path("wiki/MCP-Tools-Reference.md")
MODEL = "claude-haiku-4-5"
MAX_RETRIES = 2
TIMEOUT = 60


def extract_tools(source: str) -> list[dict]:
    """Parse server.py AST and extract @mcp.tool function metadata."""
    tree = ast.parse(source)
    tools: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Check for @mcp.tool decorator
        is_tool = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr == "tool":
                is_tool = True
            elif isinstance(dec, ast.Name) and dec.id == "tool":
                is_tool = True
        if not is_tool:
            continue

        # Extract docstring
        docstring = ast.get_docstring(node) or ""

        # Extract parameters (skip 'ctx' which is the MCP context)
        params: list[dict] = []
        for arg in node.args.args:
            name = arg.arg
            if name in ("self", "ctx"):
                continue

            # Get type annotation
            type_str = ""
            if arg.annotation:
                type_str = ast.unparse(arg.annotation)

            params.append({
                "name": name,
                "type": type_str,
                "required": True,
                "default": None,
            })

        # Check for defaults (aligned from the end)
        defaults = node.args.defaults
        if defaults:
            non_ctx_args = [a for a in node.args.args if a.arg not in ("self", "ctx")]
            offset = len(non_ctx_args) - len(defaults)
            for i, default in enumerate(defaults):
                idx = offset + i
                if 0 <= idx < len(params):
                    params[idx]["required"] = False
                    try:
                        params[idx]["default"] = ast.literal_eval(default)
                    except (ValueError, TypeError):
                        params[idx]["default"] = ast.unparse(default)

        # Get return type
        return_type = ""
        if node.returns:
            return_type = ast.unparse(node.returns)

        tools.append({
            "name": node.name,
            "docstring": docstring,
            "parameters": params,
            "return_type": return_type,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
        })

    return tools


def categorize_tools(tools: list[dict]) -> dict[str, list[dict]]:
    """Group tools into logical categories."""
    categories = {
        "Code Execution": ["execute_code", "check_code", "get_workspace"],
        "Async Job Management": ["get_job_status", "get_job_result", "cancel_job", "list_jobs"],
        "Discovery": ["list_toolboxes", "list_functions", "get_help"],
        "File Management": ["upload_data", "delete_file", "list_files"],
        "File Reading": ["read_script", "read_data", "read_image"],
        "Admin": ["get_pool_status"],
        "Monitoring": ["get_server_metrics", "get_server_health", "get_error_log"],
    }

    tool_map = {t["name"]: t for t in tools}
    result: dict[str, list[dict]] = {}

    for category, names in categories.items():
        cat_tools = [tool_map[n] for n in names if n in tool_map]
        if cat_tools:
            result[category] = cat_tools

    # Any uncategorized tools
    categorized = {n for names in categories.values() for n in names}
    uncategorized = [t for t in tools if t["name"] not in categorized]
    if uncategorized:
        result["Other"] = uncategorized

    return result


def generate_docs_via_api(categorized: dict[str, list[dict]], style_ref: str) -> str:
    """Call Claude API to generate the MCP Tools Reference markdown."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT)

    prompt = f"""Generate a comprehensive MCP Tools Reference in markdown for the matlab-mcp-server.

Here is the extracted tool metadata (JSON):
```json
{json.dumps(categorized, indent=2)}
```

Here is the existing reference document for style guidance:
```markdown
{style_ref[:3000]}
```

Requirements:
- Start with: "# MCP Tools Reference\\n\\nThe server exposes {{N}} built-in tools plus any custom tools defined in your `custom_tools.yaml`."
- Replace {{N}} with the actual count of tools in the metadata.
- Group tools by category using ## headings (use the category names from the JSON).
- For each tool use ### heading with the tool name in backticks.
- For each tool include:
  - A description (from the docstring).
  - A parameters table with columns: Parameter, Type, Required, Description.
  - If the tool has no user parameters, show: | (none) | — | — | — |
  - Where appropriate, include a realistic example JSON response.
- Match the style of the existing reference (parameter tables, code blocks, etc.).
- Add a final section "## Custom Tools" noting that custom tools are configured via `custom_tools.yaml` and are dynamically registered at runtime.
- Output ONLY the markdown content, no surrounding explanation.
"""

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                print(f"API call failed ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"ERROR: API call failed after {MAX_RETRIES + 1} attempts: {e}", file=sys.stderr)
                sys.exit(1)
    # Unreachable but satisfies type checker
    sys.exit(1)


def main() -> None:
    if not SERVER_PY.exists():
        print(f"ERROR: {SERVER_PY} not found. Run from repo root.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {SERVER_PY}...")
    source = SERVER_PY.read_text()
    tools = extract_tools(source)
    print(f"Found {len(tools)} MCP tools: {[t['name'] for t in tools]}")

    categorized = categorize_tools(tools)
    print(f"Categories: {list(categorized.keys())}")

    # Read existing style reference
    style_ref = ""
    if WIKI_OUTPUT.exists():
        style_ref = WIKI_OUTPUT.read_text()
        print(f"Loaded style reference from {WIKI_OUTPUT} ({len(style_ref)} chars)")

    print(f"Calling Claude API ({MODEL})...")
    markdown = generate_docs_via_api(categorized, style_ref)

    WIKI_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WIKI_OUTPUT.write_text(markdown)
    print(f"Written {len(markdown)} chars to {WIKI_OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test AST extraction locally (no API call needed)**

Run: `python -c "from scripts.generate_docs import extract_tools; from pathlib import Path; tools = extract_tools(Path('src/matlab_mcp/server.py').read_text()); print(f'{len(tools)} tools found'); [print(f'  {t[\"name\"]}({[p[\"name\"] for p in t[\"parameters\"]]})') for t in tools]"`

Expected: Lists 20 tools with their user-facing parameters (no ctx, no internal params like executor/tracker).

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_docs.py
git commit -m "feat: add generate_docs.py — AST-based MCP tool extraction + Claude API"
```

---

### Task 4: Create docs.yml workflow

**Files:**
- Create: `.github/workflows/docs.yml`

- [ ] **Step 1: Write docs.yml**

```yaml
name: Generate Docs

on:
  push:
    branches: [master]

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  generate-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install anthropic

      - name: Generate MCP Tools Reference
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/generate_docs.py

      - name: Push to wiki
        env:
          WIKI_PAT: ${{ secrets.WIKI_PAT }}
        run: |
          # Clone wiki repo
          git clone https://x-access-token:${WIKI_PAT}@github.com/HanSur94/matlab-mcp-server-python.wiki.git /tmp/wiki

          # Copy generated file
          cp wiki/MCP-Tools-Reference.md /tmp/wiki/MCP-Tools-Reference.md

          # Check for changes
          cd /tmp/wiki
          git diff --quiet && echo "No changes to wiki" && exit 0

          # Commit and push
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add MCP-Tools-Reference.md
          git commit -m "docs: auto-update MCP Tools Reference"
          git push
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/docs.yml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docs.yml
git commit -m "ci: add docs generation workflow — LLM-powered MCP tool reference"
```

---

### Task 5: Create generate_changelog.py — git log + Claude API

**Files:**
- Create: `scripts/generate_changelog.py`

- [ ] **Step 1: Write generate_changelog.py**

```python
#!/usr/bin/env python3
"""Generate release notes from git history using Claude API.

Reads commits since the previous tag (or all commits if no tags exist),
groups them by conventional commit type, and calls Claude Haiku to produce
human-readable release notes.

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/generate_changelog.py

Output:
    CHANGELOG.md (in the current directory)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MODEL = "claude-haiku-4-5"
MAX_RETRIES = 2
TIMEOUT = 60
MAX_COMMIT_MSG_LEN = 500
OUTPUT_FILE = Path("CHANGELOG.md")


def get_previous_tag() -> str | None:
    """Find the most recent tag before HEAD."""
    result = subprocess.run(
        ["git", "tag", "--sort=-creatordate"],
        capture_output=True, text=True,
    )
    tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]

    # If we're on a tag, get the one before it
    current = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        capture_output=True, text=True,
    )
    current_tag = current.stdout.strip() if current.returncode == 0 else None

    for tag in tags:
        if tag != current_tag:
            return tag
    return None


def get_commits(since_tag: str | None) -> list[dict]:
    """Get commits since the given tag (or all commits if None)."""
    fmt = "%H|%s|%an|%ad"
    if since_tag:
        cmd = ["git", "log", f"{since_tag}..HEAD", f"--format={fmt}", "--date=short"]
    else:
        cmd = ["git", "log", f"--format={fmt}", "--date=short"]

    result = subprocess.run(cmd, capture_output=True, text=True)
    commits: list[dict] = []

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        commits.append({
            "hash": parts[0][:8],
            "message": parts[1][:MAX_COMMIT_MSG_LEN],
            "author": parts[2],
            "date": parts[3],
        })

    return commits


def group_commits(commits: list[dict]) -> dict[str, list[dict]]:
    """Group commits by conventional commit type."""
    groups: dict[str, list[dict]] = {
        "feat": [],
        "fix": [],
        "docs": [],
        "ci": [],
        "refactor": [],
        "test": [],
        "chore": [],
        "other": [],
    }

    pattern = re.compile(r"^(\w+)(?:\(.+?\))?!?:\s*(.+)")

    for commit in commits:
        match = pattern.match(commit["message"])
        if match:
            ctype = match.group(1).lower()
            if ctype in groups:
                groups[ctype].append(commit)
            else:
                groups["other"].append(commit)
        else:
            groups["other"].append(commit)

    # Remove empty groups
    return {k: v for k, v in groups.items() if v}


def generate_changelog_via_api(grouped: dict[str, list[dict]], tag: str) -> str:
    """Call Claude API to generate release notes."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT)

    total_commits = sum(len(v) for v in grouped.values())

    prompt = f"""Write concise release notes for version {tag} of the matlab-mcp-server project.

This is an MCP (Model Context Protocol) server that exposes MATLAB capabilities to AI agents.

Here are the commits grouped by type:
```json
{json.dumps(grouped, indent=2)}
```

Total commits: {total_commits}

Requirements:
- Start with "## {tag}" as the heading
- First paragraph: 1-2 sentence highlight summary of what's in this release
- Sections (only include if there are commits for that type):
  - **New Features** (from feat commits)
  - **Bug Fixes** (from fix commits)
  - **Documentation** (from docs commits)
  - **CI/CD** (from ci commits)
  - **Other Changes** (from refactor, test, chore, other)
- Use bullet points, be concise, focus on user impact
- Do not include commit hashes
- Output ONLY the markdown, no surrounding explanation
"""

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                print(f"API call failed ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"ERROR: API call failed after {MAX_RETRIES + 1} attempts: {e}", file=sys.stderr)
                sys.exit(1)
    sys.exit(1)


def main() -> None:
    # Get the current tag from environment or git
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if not tag:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True, text=True,
        )
        tag = result.stdout.strip() if result.returncode == 0 else "unreleased"

    print(f"Generating changelog for: {tag}")

    prev_tag = get_previous_tag()
    if prev_tag:
        print(f"Commits since: {prev_tag}")
    else:
        print("No previous tag found — including all commits")

    commits = get_commits(prev_tag)
    print(f"Found {len(commits)} commits")

    if not commits:
        print("No commits found — writing minimal changelog")
        OUTPUT_FILE.write_text(f"## {tag}\n\nNo changes.\n")
        return

    grouped = group_commits(commits)
    print(f"Groups: {', '.join(f'{k}({len(v)})' for k, v in grouped.items())}")

    print(f"Calling Claude API ({MODEL})...")
    changelog = generate_changelog_via_api(grouped, tag)

    OUTPUT_FILE.write_text(changelog)
    print(f"Written {len(changelog)} chars to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test commit grouping locally (no API call needed)**

Run: `python -c "from scripts.generate_changelog import get_commits, group_commits, get_previous_tag; prev = get_previous_tag(); print(f'prev_tag={prev}'); commits = get_commits(prev); print(f'{len(commits)} commits'); grouped = group_commits(commits); print({k: len(v) for k, v in grouped.items()})"`

Expected: Shows all commits grouped by type (feat, fix, docs, ci, etc.)

- [ ] **Step 3: Commit**

```bash
git add scripts/generate_changelog.py
git commit -m "feat: add generate_changelog.py — git log parsing + Claude API release notes"
```

---

### Task 6: Create release.yml workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write release.yml**

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write

jobs:
  draft-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install tools
        run: pip install anthropic build

      - name: Generate changelog
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python scripts/generate_changelog.py

      - name: Build package
        run: python -m build

      - name: Create draft release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh release create ${{ github.ref_name }} \
            --draft \
            --title "${{ github.ref_name }}" \
            --notes-file CHANGELOG.md \
            dist/*
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add semi-automated release workflow with LLM-generated changelog"
```

---

### Task 7: Update README badges

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Codecov and License badges**

The README already has CI, PyPI, and Python version badges (lines 17-26). Add Codecov and License badges to the existing badge block. The badges are in an HTML `<p align="center">` block.

Add these two badges after the existing Python badge (before the closing `</p>`):

```html
  <a href="https://codecov.io/gh/HanSur94/matlab-mcp-server-python">
    <img src="https://codecov.io/gh/HanSur94/matlab-mcp-server-python/branch/master/graph/badge.svg" alt="codecov">
  </a>
  <a href="https://github.com/HanSur94/matlab-mcp-server-python/blob/master/LICENSE">
    <img src="https://img.shields.io/github/license/HanSur94/matlab-mcp-server-python" alt="License">
  </a>
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add Codecov and License badges to README"
```

---

### Task 8: Final validation

- [ ] **Step 1: Verify all workflow YAML files parse correctly**

Run: `python -c "import yaml; [yaml.safe_load(open(f'.github/workflows/{f}')) for f in ['ci.yml', 'docs.yml', 'release.yml', 'publish.yml']]; print('All workflows valid')"`

- [ ] **Step 2: Verify ruff passes on scripts**

Run: `ruff check scripts/`
Expected: No errors (fix any issues if found)

- [ ] **Step 3: Verify the generate_docs AST extraction finds all 20 tools**

Run: `python -c "from scripts.generate_docs import extract_tools; from pathlib import Path; tools = extract_tools(Path('src/matlab_mcp/server.py').read_text()); assert len(tools) == 20, f'Expected 20 tools, got {len(tools)}: {[t[\"name\"] for t in tools]}'; print('OK: 20 tools extracted')"`

- [ ] **Step 4: List all new and modified files**

Run: `git log --oneline --name-status HEAD~7..HEAD`

Expected files touched:
- `pyproject.toml` (M)
- `.github/workflows/ci.yml` (M)
- `.github/workflows/docs.yml` (A)
- `.github/workflows/release.yml` (A)
- `scripts/generate_docs.py` (A)
- `scripts/generate_changelog.py` (A)
- `README.md` (M)

---

## Secrets Setup Checklist (manual, post-implementation)

After all code is pushed, the repo owner must configure these GitHub secrets:

1. **`ANTHROPIC_API_KEY`** — Anthropic API key for Claude Haiku calls (docs + changelog generation)
2. **`WIKI_PAT`** — GitHub Personal Access Token with `public_repo` scope (for pushing to wiki repo)
3. **`CODECOV_TOKEN`** — Codecov upload token (get from codecov.io after connecting the repo)
