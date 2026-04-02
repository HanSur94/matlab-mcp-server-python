# Wiki Gen Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable GitHub Composite Action + CLI extension that auto-generates wiki documentation for any GitHub project using the Anthropic Claude API.

**Architecture:** Two separate repos: `wiki-gen-action` (the GitHub Action with Python scripts for discovery, generation, and pushing) and `gh-wiki-gen` (a bash-based `gh` CLI extension for bootstrapping). The action uses a two-pass approach: Pass 1 summarizes all source files with haiku, Pass 2 generates wiki pages with the configured model. Discovery is automatic but overridable via `.github/docs-config.yml`.

**Tech Stack:** Python 3.12, Anthropic SDK, PyYAML, Bash, GitHub Actions, `gh` CLI

**Spec:** `docs/superpowers/specs/2026-03-22-wiki-gen-action-design.md`

---

## Part 1: wiki-gen-action

All files created under `/Users/hannessuhr/wiki-gen-action/`.

### Task 1: Repo Scaffolding

**Files:**
- Create: `action.yml`
- Create: `LICENSE`
- Create: `scripts/.gitkeep` (placeholder)
- Create: `defaults/.gitkeep` (placeholder)

- [ ] **Step 1: Initialize the repo**

```bash
mkdir -p /Users/hannessuhr/wiki-gen-action
cd /Users/hannessuhr/wiki-gen-action
git init
```

- [ ] **Step 2: Create LICENSE (MIT)**

```
MIT License

Copyright (c) 2026 Hannes Suhr

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Create action.yml**

```yaml
name: 'Wiki Gen Action'
description: 'Auto-generate wiki documentation for any GitHub project using Claude API'
author: 'Hannes Suhr'

inputs:
  anthropic_api_key:
    description: 'Anthropic API key'
    required: true
  wiki_pat:
    description: 'GitHub PAT with wiki push access (requires repo scope for classic PATs, or contents:write for fine-grained PATs; add pull-requests:write if using push_strategy: pr)'
    required: true
  model:
    description: 'Claude model for Pass 2 page generation. Pass 1 always uses claude-haiku-4-5 for cost efficiency.'
    default: 'claude-haiku-4-5'
  config_path:
    description: 'Path to docs config file. If the file does not exist (default or custom path), auto-discovery runs.'
    default: '.github/docs-config.yml'
  dry_run:
    description: 'Generate pages without pushing to wiki'
    default: 'false'
  push_strategy:
    description: 'How to push wiki updates: "direct" (push to wiki repo) or "pr" (commit wiki files to a docs/ branch in the main repo and open a PR for review)'
    default: 'direct'
  auto_merge:
    description: 'Auto-merge wiki update PRs via gh pr merge --auto (only with push_strategy: pr). Note: requires branch protection to allow auto-merge and may not satisfy required-reviews if the workflow token is the PR creator.'
    default: 'false'

outputs:
  pages_updated:
    description: 'Number of wiki pages successfully written'
    value: ${{ steps.generate.outputs.pages_updated }}
  pages_failed:
    description: 'Number of wiki pages that failed generation'
    value: ${{ steps.generate.outputs.pages_failed }}
  wiki_commit_sha:
    description: 'Git SHA of the wiki commit (empty on dry_run or no changes)'
    value: ${{ steps.push.outputs.wiki_commit_sha }}

runs:
  using: 'composite'
  steps:
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'

    - name: Install dependencies
      shell: bash
      run: pip install anthropic pyyaml

    - name: Discover and generate wiki pages
      id: generate
      shell: bash
      env:
        ANTHROPIC_API_KEY: ${{ inputs.anthropic_api_key }}
        INPUT_MODEL: ${{ inputs.model }}
        INPUT_CONFIG_PATH: ${{ inputs.config_path }}
        INPUT_DRY_RUN: ${{ inputs.dry_run }}
      run: |
        python ${{ github.action_path }}/scripts/discover.py
        python ${{ github.action_path }}/scripts/generate.py

    - name: Push wiki
      id: push
      if: inputs.dry_run != 'true'
      shell: bash
      env:
        WIKI_PAT: ${{ inputs.wiki_pat }}
        PUSH_STRATEGY: ${{ inputs.push_strategy }}
        AUTO_MERGE: ${{ inputs.auto_merge }}
        GITHUB_REPOSITORY: ${{ github.repository }}
      run: bash ${{ github.action_path }}/scripts/push_wiki.sh

branding:
  icon: 'book-open'
  color: 'blue'
```

- [ ] **Step 4: Create directory structure and commit**

```bash
mkdir -p scripts defaults tests
git add action.yml LICENSE
git commit -m "feat: add action.yml and LICENSE"
```

---

### Task 2: File Discovery — File Walker and Filtering

**Files:**
- Create: `scripts/discover.py`
- Create: `tests/test_discover.py`

- [ ] **Step 1: Write failing tests for file walker**

Create `tests/test_discover.py`:

```python
"""Tests for discover.py file walking and filtering."""
import os
import tempfile
from pathlib import Path

import pytest

# We'll import after creating the module
from scripts.discover import walk_source_files, is_text_file, EXCLUDED_DIRS, SOURCE_EXTENSIONS


class TestIsTextField:
    def test_python_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        assert is_text_file(f) is True

    def test_binary_file(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        assert is_text_file(f) is False

    def test_large_file_skipped(self, tmp_path):
        f = tmp_path / "large.py"
        f.write_text("x" * 200_000)  # > 100KB
        assert is_text_file(f) is False

    def test_unknown_extension_but_text(self, tmp_path):
        f = tmp_path / "Makefile"
        f.write_text("all:\n\techo hello")
        # Unknown extension, not in SOURCE_EXTENSIONS
        assert is_text_file(f) is False

    def test_symlink_skipped(self, tmp_path):
        target = tmp_path / "real.py"
        target.write_text("x = 1")
        link = tmp_path / "link.py"
        link.symlink_to(target)
        assert is_text_file(link) is False


class TestWalkSourceFiles:
    def test_finds_python_files(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main(): pass")
        (tmp_path / "src" / "utils.py").write_text("def util(): pass")
        files = walk_source_files(tmp_path)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "utils.py" in names

    def test_excludes_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.js").write_text("module.exports = {}")
        files = walk_source_files(tmp_path)
        names = {f.name for f in files}
        assert "pkg.js" not in names

    def test_excludes_git_dir(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("[core]")
        files = walk_source_files(tmp_path)
        names = {f.name for f in files}
        assert "config" not in names

    def test_respects_max_depth(self, tmp_path):
        # Create a deeply nested file (11 levels)
        d = tmp_path
        for i in range(11):
            d = d / f"level{i}"
            d.mkdir()
        (d / "deep.py").write_text("x = 1")
        files = walk_source_files(tmp_path, max_depth=10)
        names = {f.name for f in files}
        assert "deep.py" not in names

    def test_respects_source_dirs(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "lib").mkdir()
        (tmp_path / "src" / "a.py").write_text("a = 1")
        (tmp_path / "lib" / "b.py").write_text("b = 2")
        (tmp_path / "other" ).mkdir()
        (tmp_path / "other" / "c.py").write_text("c = 3")
        files = walk_source_files(tmp_path, source_dirs=["src/", "lib/"])
        names = {f.name for f in files}
        assert "a.py" in names
        assert "b.py" in names
        assert "c.py" not in names

    def test_respects_exclude_patterns(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x = 1")
        (tmp_path / "src" / "main.test.py").write_text("test = 1")
        files = walk_source_files(tmp_path, exclude_patterns=["*.test.*"])
        names = {f.name for f in files}
        assert "main.py" in names
        assert "main.test.py" not in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/hannessuhr/wiki-gen-action
pip install pytest
pytest tests/test_discover.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.discover'`

- [ ] **Step 3: Implement discover.py — file walking and filtering**

Create `scripts/__init__.py` (empty) and `scripts/discover.py`:

```python
#!/usr/bin/env python3
"""Auto-discover repo structure and generate page definitions for wiki generation.

Walks the source tree, filters files, detects languages, and produces a JSON
page definition file that generate.py consumes.
"""
from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_EXTENSIONS: set[str] = {
    # Programming languages
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".go", ".rs",
    ".rb", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".c", ".cs", ".m",
    ".swift", ".kt", ".kts", ".php",
    # Config / docs / scripts
    ".md", ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini",
    ".sh", ".bat", ".ps1", ".sql", ".html", ".css", ".scss",
    ".r", ".R", ".jl",
}

EXCLUDED_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", ".tox", ".venv", "venv",
    ".eggs", "dist", "build", ".mypy_cache",
}

LANG_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".h": "C++", ".hpp": "C++",
    ".c": "C", ".cs": "C#", ".m": "MATLAB/Objective-C",
    ".swift": "Swift", ".kt": "Kotlin", ".kts": "Kotlin", ".php": "PHP",
}

SECURITY_KEYWORDS: set[str] = {
    "security", "auth", "permissions", "rbac", "acl",
    "crypto", "encrypt", "sanitiz", "validat",
}

MAX_FILE_SIZE: int = 100_000  # 100KB
DEFAULT_MAX_DEPTH: int = 10
DEFAULT_MAX_CHARS_PER_FILE: int = 6000


# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------


def is_text_file(path: Path) -> bool:
    """Check if a file should be included based on extension, size, symlink, and binary checks."""
    if path.is_symlink():
        return False
    # Special case: .env.example has suffix .example but should be included
    if path.name == ".env.example":
        pass  # Allow through
    elif path.suffix not in SOURCE_EXTENSIONS:
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size > MAX_FILE_SIZE:
        print(f"  WARNING: Skipping large file ({size} bytes): {path}", file=sys.stderr)
        return False
    # Binary check: look for null bytes in first 8KB
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        if b"\x00" in chunk:
            return False
    except OSError:
        return False
    return True


def walk_source_files(
    root: Path,
    source_dirs: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> list[Path]:
    """Walk the source tree and return all eligible source files."""
    result: list[Path] = []
    exclude_patterns = exclude_patterns or []

    # Determine which directories to walk
    if source_dirs:
        roots = [root / d.rstrip("/") for d in source_dirs]
        roots = [r for r in roots if r.is_dir()]
    else:
        roots = [root]

    for walk_root in roots:
        for dirpath, dirnames, filenames in os.walk(walk_root):
            dp = Path(dirpath)
            # Depth check
            try:
                depth = len(dp.relative_to(root).parts)
            except ValueError:
                depth = len(dp.relative_to(walk_root).parts)
            if depth > max_depth:
                dirnames.clear()
                continue
            # Prune excluded directories (in-place to prevent os.walk from descending)
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDED_DIRS and not Path(d).is_symlink()
            ]
            for fname in filenames:
                fpath = dp / fname
                # Check exclude patterns
                rel = str(fpath.relative_to(root))
                if any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fname, pat) for pat in exclude_patterns):
                    continue
                if is_text_file(fpath):
                    result.append(fpath)
    return sorted(result)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def detect_languages(files: list[Path]) -> list[str]:
    """Detect programming languages from file extensions."""
    langs: set[str] = set()
    for f in files:
        lang = LANG_MAP.get(f.suffix)
        if lang:
            langs.add(lang)
    return sorted(langs)


# ---------------------------------------------------------------------------
# Auto-discovery: page definitions
# ---------------------------------------------------------------------------

PACKAGE_MANIFESTS = [
    "pyproject.toml", "setup.py", "setup.cfg",  # Python
    "package.json",  # JS/TS
    "Cargo.toml",  # Rust
    "go.mod",  # Go
    "pom.xml", "build.gradle", "build.gradle.kts",  # Java/Kotlin
    "Gemfile",  # Ruby
    "composer.json",  # PHP
    "Package.swift",  # Swift
]


def discover_pages(root: Path, files: list[Path], languages: list[str]) -> dict:
    """Auto-discover which wiki pages to generate based on repo structure."""
    pages: dict[str, dict] = {}
    rel_files = [str(f.relative_to(root)) for f in files]

    # --- Always-on pages ---
    readme_sources = [f for f in rel_files if Path(f).name.lower().startswith("readme")]
    manifest_sources = [f for f in rel_files if Path(f).name in PACKAGE_MANIFESTS]

    pages["Home"] = {
        "sources": readme_sources + manifest_sources,
        "auto": True,
    }
    pages["Installation"] = {
        "sources": readme_sources + manifest_sources + [
            f for f in rel_files if Path(f).name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml")
        ],
        "auto": True,
    }
    pages["FAQ"] = {
        "sources": readme_sources,
        "auto": True,
    }
    pages["Troubleshooting"] = {
        "sources": readme_sources + [f for f in rel_files if "config" in Path(f).name.lower()],
        "auto": True,
    }

    # --- Conditional pages ---
    has_src = any(f.startswith("src/") or f.startswith("lib/") for f in rel_files)
    if has_src:
        pages["Architecture"] = {
            "sources": rel_files,  # All files via two-pass
            "auto": True,
        }

    # API Reference: if source files exist
    code_files = [f for f in rel_files if Path(f).suffix in LANG_MAP]
    if code_files:
        pages["API-Reference"] = {
            "sources": code_files,
            "auto": True,
        }

    # Configuration: if config files exist
    config_files = [
        f for f in rel_files
        if any(kw in Path(f).name.lower() for kw in ("config", "settings", ".env"))
        or Path(f).suffix in (".toml", ".ini", ".cfg")
    ]
    if config_files:
        pages["Configuration"] = {
            "sources": config_files,
            "auto": True,
        }

    # Security: if security-related files exist
    security_files = [
        f for f in rel_files
        if any(kw in f.lower() for kw in SECURITY_KEYWORDS)
    ]
    if security_files:
        pages["Security"] = {
            "sources": security_files,
            "auto": True,
        }

    # Examples: if examples/ directory exists
    example_files = [f for f in rel_files if f.startswith("examples/")]
    if example_files:
        pages["Examples"] = {
            "sources": example_files,
            "auto": True,
        }

    return pages


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_config(config_path: Path) -> dict | None:
    """Load .github/docs-config.yml if it exists. Returns None if not found."""
    if not config_path.is_file():
        return None
    try:
        import yaml
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"  WARNING: Failed to parse config {config_path}: {e}", file=sys.stderr)
        return None


def resolve_glob_sources(root: Path, sources: list[str]) -> list[str]:
    """Resolve glob patterns and directory paths in source lists to actual file paths."""
    import glob as glob_mod
    result: list[str] = []
    for src in sources:
        src_path = root / src
        # If it's a directory without glob, treat as dir/**/*
        if src_path.is_dir():
            for match in glob_mod.glob(str(src_path / "**" / "*"), recursive=True):
                mp = Path(match)
                if mp.is_file() and is_text_file(mp):
                    result.append(str(mp.relative_to(root)))
        elif "*" in src or "?" in src:
            for match in glob_mod.glob(str(root / src), recursive=True):
                mp = Path(match)
                if mp.is_file():
                    result.append(str(mp.relative_to(root)))
        else:
            if src_path.is_file():
                result.append(src)
    return sorted(set(result))


def merge_config_with_discovery(
    config: dict, auto_pages: dict, root: Path
) -> dict:
    """Merge user config with auto-discovered pages."""
    # If config defines 'pages', use only those (no auto-discovery)
    if "pages" in config:
        pages = {}
        for name, page_def in config["pages"].items():
            sources = resolve_glob_sources(root, page_def.get("sources", []))
            pages[name] = {
                "sources": sources,
                "prompt": page_def.get("prompt", ""),
                "auto": False,
            }
    else:
        pages = auto_pages

    # Append extra_pages (skip conflicts with explicit pages)
    if "extra_pages" in config:
        for name, page_def in config["extra_pages"].items():
            if name in pages and not pages[name].get("auto", True):
                continue  # Explicit pages win
            sources = resolve_glob_sources(root, page_def.get("sources", []))
            pages[name] = {
                "sources": sources,
                "prompt": page_def.get("prompt", ""),
                "auto": False,
            }

    return pages


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    root = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
    config_path = Path(os.environ.get("INPUT_CONFIG_PATH", ".github/docs-config.yml"))

    # Make config_path relative to root if not absolute
    if not config_path.is_absolute():
        config_path = root / config_path

    print(f"[wiki-gen] Discovering files in: {root}")
    config = load_config(config_path)

    # Determine filters from config
    source_dirs = config.get("source_dirs") if config else None
    exclude = config.get("exclude", []) if config else []

    # Walk files
    files = walk_source_files(root, source_dirs=source_dirs, exclude_patterns=exclude)
    print(f"[wiki-gen] Found {len(files)} source files")

    # Detect languages
    languages = detect_languages(files)
    print(f"[wiki-gen] Detected languages: {', '.join(languages) or 'none'}")

    # Auto-discover pages
    auto_pages = discover_pages(root, files, languages)

    # Merge with config if present
    if config:
        print(f"[wiki-gen] Loading config from: {config_path}")
        pages = merge_config_with_discovery(config, auto_pages, root)
    else:
        print("[wiki-gen] No config found, using auto-discovery")
        pages = auto_pages

    # Write discovery output for generate.py to consume
    output = {
        "root": str(root),
        "languages": languages,
        "pages": pages,
        "max_chars_per_file": (config or {}).get("max_chars_per_file", DEFAULT_MAX_CHARS_PER_FILE),
        "include_mermaid": (config or {}).get("include_mermaid", True),
    }
    output_path = root / "wiki" / "_discovery.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2))
    print(f"[wiki-gen] Discovery output: {output_path}")
    print(f"[wiki-gen] Pages to generate: {', '.join(pages.keys())}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create `scripts/__init__.py`**

Empty file.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/hannessuhr/wiki-gen-action
PYTHONPATH=. pytest tests/test_discover.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/discover.py scripts/__init__.py tests/test_discover.py
git commit -m "feat: add file discovery with filtering, language detection, and auto-discovery"
```

---

### Task 3: Default Prompts

**Files:**
- Create: `defaults/prompts.yml`

- [ ] **Step 1: Create prompts.yml**

```yaml
# Default prompts for each wiki page type.
# Each prompt instructs Claude how to generate that page.
# {languages} and {mermaid_instruction} are template variables replaced at runtime.

Home:
  prompt: |
    Generate a Home page for this project's wiki.
    Languages: {languages}

    Write a concise, welcoming overview:
    - What the project does (1-2 sentences)
    - Key features as bullet points
    - Quick-start code snippet
    - Links to other wiki pages (Installation, Configuration, API Reference, etc.)

    {mermaid_instruction}
    Keep it scannable. Output ONLY the markdown.

Installation:
  prompt: |
    Generate an Installation page for this project's wiki.
    Languages: {languages}

    Cover all installation methods found in the source:
    - Package manager install (pip, npm, cargo, etc.)
    - From source
    - Docker / docker-compose (if Dockerfile exists)
    - System requirements and prerequisites

    {mermaid_instruction}
    Use a flowchart to show the different installation paths if multiple methods exist.
    Output ONLY the markdown.

Architecture:
  prompt: |
    Generate an Architecture page for this project's wiki.
    Languages: {languages}

    Document the system architecture:
    - High-level component overview
    - How components connect and communicate
    - Data flow through the system
    - Key design decisions

    {mermaid_instruction}
    Include a component diagram (flowchart) showing how the major modules relate.
    Include a sequence diagram if there is a notable request/response or job flow.
    Output ONLY the markdown.

API-Reference:
  prompt: |
    Generate an API Reference page for this project's wiki.
    Languages: {languages}

    Document all public APIs, classes, functions, and endpoints:
    - Group by module/package
    - For each item: name, description, parameters (with types), return value
    - Include usage examples where helpful

    {mermaid_instruction}
    Include a classDiagram or flowchart showing module/class relationships.
    Output ONLY the markdown.

Configuration:
  prompt: |
    Generate a Configuration page for this project's wiki.
    Languages: {languages}

    Document all configuration options:
    - Config file format and location
    - All fields with types, defaults, and descriptions
    - Environment variable overrides (if applicable)
    - Example configurations for common scenarios

    {mermaid_instruction}
    Output ONLY the markdown.

Security:
  prompt: |
    Generate a Security page for this project's wiki.
    Languages: {languages}

    Document security features and practices:
    - Authentication/authorization mechanisms
    - Input validation and sanitization
    - Security configuration options
    - Best practices for deployment

    {mermaid_instruction}
    Output ONLY the markdown.

Examples:
  prompt: |
    Generate an Examples page for this project's wiki.
    Languages: {languages}

    Show practical usage examples from the examples/ directory:
    - Basic usage
    - Advanced patterns
    - Integration examples

    Use the actual example files as the source of truth for code snippets.
    {mermaid_instruction}
    Output ONLY the markdown.

FAQ:
  prompt: |
    Generate a FAQ page for this project's wiki.
    Languages: {languages}

    Answer common questions about:
    - Supported versions and compatibility
    - Common setup issues
    - Performance and scaling
    - Integration with other tools

    {mermaid_instruction}
    Output ONLY the markdown.

Troubleshooting:
  prompt: |
    Generate a Troubleshooting page for this project's wiki.
    Languages: {languages}

    Cover common issues and their solutions:
    - Installation problems
    - Configuration errors
    - Runtime issues
    - How to enable debug logging
    - Where to get help

    {mermaid_instruction}
    Output ONLY the markdown.
```

- [ ] **Step 2: Commit**

```bash
git add defaults/prompts.yml
git commit -m "feat: add default prompt templates for all wiki page types"
```

---

### Task 4: Generation Script — Two-Pass with Anthropic API

**Files:**
- Create: `scripts/generate.py`
- Create: `tests/test_generate.py`

- [ ] **Step 1: Write failing tests for generate.py helpers**

Create `tests/test_generate.py`:

```python
"""Tests for generate.py — batching, validation, prompt building."""
import json
import re
from pathlib import Path

import pytest

from scripts.generate import (
    batch_files,
    validate_mermaid,
    strip_invalid_mermaid,
    build_page_prompt,
    MERMAID_DIAGRAM_TYPES,
)


class TestBatchFiles:
    def test_single_small_file(self):
        files = {"a.py": "x = 1"}
        batches = batch_files(files, max_chars=50000)
        assert len(batches) == 1
        assert "a.py" in batches[0]

    def test_splits_large_batch(self):
        files = {f"file{i}.py": "x" * 10000 for i in range(10)}
        batches = batch_files(files, max_chars=50000)
        assert len(batches) >= 2

    def test_single_oversized_file_alone(self):
        files = {"big.py": "x" * 60000, "small.py": "y = 1"}
        batches = batch_files(files, max_chars=50000)
        # big.py should be in its own batch
        assert any(len(b) == 1 and "big.py" in b for b in batches)


class TestMermaidValidation:
    def test_valid_flowchart(self):
        block = "```mermaid\nflowchart TD\n  A --> B\n```"
        assert validate_mermaid(block) is True

    def test_valid_sequence_diagram(self):
        block = "```mermaid\nsequenceDiagram\n  A->>B: Hello\n```"
        assert validate_mermaid(block) is True

    def test_invalid_no_diagram_type(self):
        block = "```mermaid\nA --> B\n```"
        assert validate_mermaid(block) is False

    def test_unclosed_block(self):
        text = "```mermaid\nflowchart TD\n  A --> B"
        assert validate_mermaid(text) is False


class TestStripInvalidMermaid:
    def test_keeps_valid_blocks(self):
        text = "# Title\n\n```mermaid\nflowchart TD\n  A --> B\n```\n\nMore text."
        result = strip_invalid_mermaid(text)
        assert "```mermaid" in result

    def test_strips_invalid_blocks(self):
        text = "# Title\n\n```mermaid\nNOTVALID\n  A --> B\n```\n\nMore text."
        result = strip_invalid_mermaid(text)
        assert "```mermaid" not in result
        assert "More text." in result

    def test_no_mermaid_blocks_unchanged(self):
        text = "# Title\n\nJust text."
        result = strip_invalid_mermaid(text)
        assert result == text


class TestBuildPagePrompt:
    def test_includes_summaries(self):
        prompt = build_page_prompt(
            page_name="Architecture",
            page_prompt="Document the architecture.",
            summaries={"src/main.py": "Entry point for the application."},
            source_snippets={"src/main.py": "def main(): pass"},
            languages=["Python"],
            include_mermaid=True,
            existing_page="",
        )
        assert "Entry point" in prompt
        assert "def main()" in prompt
        assert "Mermaid" in prompt or "mermaid" in prompt

    def test_no_mermaid_when_disabled(self):
        prompt = build_page_prompt(
            page_name="Home",
            page_prompt="Write a home page.",
            summaries={},
            source_snippets={},
            languages=["Python"],
            include_mermaid=False,
            existing_page="",
        )
        # The page_prompt itself doesn't contain mermaid, and include_mermaid=False
        # means no mermaid instruction is added
        assert "Include Mermaid" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=. pytest tests/test_generate.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement generate.py**

Create `scripts/generate.py`:

```python
#!/usr/bin/env python3
"""Generate wiki pages via Claude API using two-pass approach.

Reads _discovery.json from discover.py, summarizes all source files (Pass 1),
then generates wiki pages (Pass 2).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASS1_MODEL = "claude-haiku-4-5"
MAX_RETRIES = 2
TIMEOUT = 120
MAX_BATCH_CHARS = 50_000
MERMAID_DIAGRAM_TYPES = {
    "graph", "flowchart", "sequenceDiagram", "classDiagram",
    "stateDiagram", "erDiagram", "gantt", "pie", "gitgraph",
}
REFUSAL_PATTERNS = re.compile(
    r"^(I'm sorry|I cannot|I apologize|Sorry,|As an AI|Unfortunately,\s+I)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Batching
# ---------------------------------------------------------------------------


def batch_files(
    file_contents: dict[str, str], max_chars: int = MAX_BATCH_CHARS
) -> list[dict[str, str]]:
    """Group files into batches that fit within max_chars."""
    batches: list[dict[str, str]] = []
    current_batch: dict[str, str] = {}
    current_size = 0

    for path, content in file_contents.items():
        size = len(content)
        if size > max_chars:
            # Oversized file gets its own batch (truncated by caller)
            if current_batch:
                batches.append(current_batch)
                current_batch = {}
                current_size = 0
            batches.append({path: content})
            continue

        if current_size + size > max_chars:
            batches.append(current_batch)
            current_batch = {}
            current_size = 0

        current_batch[path] = content
        current_size += size

    if current_batch:
        batches.append(current_batch)

    return batches


# ---------------------------------------------------------------------------
# Mermaid validation
# ---------------------------------------------------------------------------

MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*\n(.*?)```", re.DOTALL
)


def validate_mermaid(block: str) -> bool:
    """Check if a mermaid block is well-formed (has closing fence + known diagram type)."""
    # Must have opening and closing fences
    if "```mermaid" not in block:
        return False
    match = MERMAID_BLOCK_RE.search(block)
    if not match:
        return False
    content = match.group(1).strip()
    # First word (or line) must contain a known diagram type
    first_line = content.split("\n")[0].strip() if content else ""
    return any(dt in first_line for dt in MERMAID_DIAGRAM_TYPES)


def strip_invalid_mermaid(text: str) -> str:
    """Remove invalid mermaid blocks from generated text, keep valid ones."""
    result = text
    for match in reversed(list(MERMAID_BLOCK_RE.finditer(text))):
        full_block = match.group(0)
        if not validate_mermaid(full_block):
            print("  WARNING: Stripped invalid mermaid block", file=sys.stderr)
            result = result[:match.start()] + result[match.end():]
    return result.strip()


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def build_page_prompt(
    page_name: str,
    page_prompt: str,
    summaries: dict[str, str],
    source_snippets: dict[str, str],
    languages: list[str],
    include_mermaid: bool,
    existing_page: str,
) -> str:
    """Build the full prompt for Pass 2 page generation."""
    parts: list[str] = []

    parts.append(page_prompt)
    if include_mermaid:
        parts.append(
            "\nInclude Mermaid diagrams using ```mermaid code blocks where they aid "
            "understanding. Use flowchart, sequenceDiagram, classDiagram, or other "
            "appropriate diagram types. Ensure each mermaid block starts with a valid "
            "diagram type keyword."
        )

    if summaries:
        parts.append("\n## File Summaries\n")
        for path, summary in summaries.items():
            parts.append(f"### {path}\n{summary}\n")

    if source_snippets:
        parts.append("\n## Key Source Files\n")
        for path, code in source_snippets.items():
            parts.append(f"### {path}\n```\n{code}\n```\n")

    if existing_page:
        parts.append(
            "\n## Existing Page (for style reference)\n"
            f"```markdown\n{existing_page[:3000]}\n```\n"
        )

    parts.append("\nOutput ONLY the markdown content. No surrounding explanation.")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def get_client():
    """Create Anthropic client."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    return anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT)


def call_api(client, prompt: str, model: str, max_tokens: int = 8000) -> tuple[str | None, int, int]:
    """Call Claude API with retry. Returns (text, input_tokens, output_tokens)."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            if not text or not text.strip():
                print("  WARNING: API returned empty output", file=sys.stderr)
                return None, input_tokens, output_tokens

            if response.stop_reason != "end_turn":
                print(f"  WARNING: unexpected stop_reason: {response.stop_reason}", file=sys.stderr)

            if REFUSAL_PATTERNS.match(text.lstrip()):
                print(f"  WARNING: API refusal: {text[:80]}...", file=sys.stderr)
                return None, input_tokens, output_tokens

            return text, input_tokens, output_tokens

        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                print(f"  API error ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  ERROR: API failed after {MAX_RETRIES + 1} attempts: {e}", file=sys.stderr)
                return None, 0, 0

    return None, 0, 0


# ---------------------------------------------------------------------------
# Pass 1: Summarize
# ---------------------------------------------------------------------------


def pass1_summarize(
    client, root: Path, files: list[str], max_chars_per_file: int
) -> dict[str, str]:
    """Summarize all source files in batches."""
    print("\n[wiki-gen] === Pass 1: Summarizing source files ===")

    # Read all files
    file_contents: dict[str, str] = {}
    for rel_path in files:
        full_path = root / rel_path
        try:
            content = full_path.read_text(errors="replace")
            if len(content) > max_chars_per_file:
                content = content[:max_chars_per_file] + f"\n... (truncated at {max_chars_per_file} chars)"
            file_contents[rel_path] = content
        except Exception as e:
            print(f"  WARNING: Could not read {rel_path}: {e}", file=sys.stderr)

    if not file_contents:
        print("  No files to summarize")
        return {}

    batches = batch_files(file_contents)
    print(f"  Processing {len(file_contents)} files in {len(batches)} batches")

    summaries: dict[str, str] = {}
    total_input = 0
    total_output = 0

    for i, batch in enumerate(batches):
        file_list = "\n".join(
            f"### File: {path}\n```\n{content}\n```"
            for path, content in batch.items()
        )
        prompt = (
            "Summarize each of the following source files. For each file, provide:\n"
            "- Purpose (1 sentence)\n"
            "- Key classes, functions, or exports\n"
            "- Dependencies and relationships to other files\n\n"
            "Format as:\n"
            "## <filepath>\n<summary>\n\n"
            f"{file_list}"
        )

        text, inp, out = call_api(client, prompt, PASS1_MODEL, max_tokens=4000)
        total_input += inp
        total_output += out

        if text:
            # Parse summaries from response
            current_file = None
            current_summary: list[str] = []
            for line in text.split("\n"):
                if line.startswith("## "):
                    if current_file and current_summary:
                        summaries[current_file] = "\n".join(current_summary).strip()
                    current_file = line[3:].strip()
                    current_summary = []
                else:
                    current_summary.append(line)
            if current_file and current_summary:
                summaries[current_file] = "\n".join(current_summary).strip()

        print(f"  Batch {i+1}/{len(batches)}: {len(batch)} files")

    print(f"[wiki-gen] Pass 1 complete: {len(summaries)} summaries | "
          f"input={total_input} output={total_output}")
    return summaries


# ---------------------------------------------------------------------------
# Pass 2: Generate pages
# ---------------------------------------------------------------------------


def load_default_prompts(action_path: Path) -> dict[str, str]:
    """Load default prompts from defaults/prompts.yml."""
    prompts_path = action_path / "defaults" / "prompts.yml"
    if not prompts_path.exists():
        return {}
    try:
        import yaml
        with open(prompts_path) as f:
            data = yaml.safe_load(f) or {}
        return {name: p["prompt"] for name, p in data.items() if "prompt" in p}
    except Exception as e:
        print(f"  WARNING: Could not load prompts.yml: {e}", file=sys.stderr)
        return {}


def pass2_generate(
    client,
    root: Path,
    pages: dict,
    summaries: dict[str, str],
    languages: list[str],
    include_mermaid: bool,
    model: str,
    max_chars_per_file: int,
    action_path: Path,
) -> tuple[int, int]:
    """Generate all wiki pages. Returns (updated_count, failed_count)."""
    print(f"\n[wiki-gen] === Pass 2: Generating {len(pages)} wiki pages ===")

    default_prompts = load_default_prompts(action_path)
    wiki_dir = root / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    updated = 0
    failed = 0
    total_input = 0
    total_output = 0

    for page_name, page_def in pages.items():
        print(f"\n  Generating: {page_name}")

        # Get the prompt
        page_prompt = page_def.get("prompt") or default_prompts.get(page_name, "")
        if not page_prompt:
            page_prompt = f"Generate a comprehensive {page_name} wiki page for this project."

        # Format template variables
        mermaid_instruction = (
            "Include Mermaid diagrams using ```mermaid code blocks where appropriate."
            if include_mermaid else ""
        )
        page_prompt = page_prompt.replace("{languages}", ", ".join(languages) or "unknown")
        page_prompt = page_prompt.replace("{mermaid_instruction}", mermaid_instruction)

        # Read key source files for this page
        source_snippets: dict[str, str] = {}
        for src in page_def.get("sources", [])[:20]:  # Limit to 20 files per page
            full_path = root / src
            if full_path.is_file():
                try:
                    content = full_path.read_text(errors="replace")
                    if len(content) > max_chars_per_file:
                        content = content[:max_chars_per_file] + "\n... (truncated)"
                    source_snippets[src] = content
                except Exception:
                    pass

        # Load existing wiki page for style reference
        existing_page = ""
        existing_path = wiki_dir / f"{page_name}.md"
        if existing_path.exists():
            existing_page = existing_path.read_text()

        # Build prompt
        prompt = build_page_prompt(
            page_name=page_name,
            page_prompt=page_prompt,
            summaries=summaries,
            source_snippets=source_snippets,
            languages=languages,
            include_mermaid=include_mermaid,
            existing_page=existing_page,
        )

        # Call API
        text, inp, out = call_api(client, prompt, model)
        total_input += inp
        total_output += out

        print(f"  [wiki-gen] Page: {page_name} | input_tokens: {inp} | "
              f"output_tokens: {out} | model: {model}")

        if text is None:
            print(f"  FAILED: {page_name}")
            failed += 1
            continue

        # Validate and fix mermaid blocks
        if include_mermaid:
            text = strip_invalid_mermaid(text)

        # Write output
        output_path = wiki_dir / f"{page_name}.md"
        output_path.write_text(text)
        updated += 1
        print(f"  OK: {len(text)} chars -> {output_path}")

    print(f"\n[wiki-gen] Total: input={total_input} output={total_output} "
          f"pages={updated}/{updated + failed}")

    return updated, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    root_env = os.environ.get("GITHUB_WORKSPACE", ".")
    root = Path(root_env).resolve()
    model = os.environ.get("INPUT_MODEL", "claude-haiku-4-5")

    # Determine action path (for loading defaults/prompts.yml)
    # In GitHub Actions, this is set by the composite action
    # Locally, use the script's parent directory
    action_path = Path(__file__).resolve().parent.parent

    # Load discovery output
    discovery_path = root / "wiki" / "_discovery.json"
    if not discovery_path.exists():
        print("ERROR: _discovery.json not found. Run discover.py first.", file=sys.stderr)
        sys.exit(1)

    discovery = json.loads(discovery_path.read_text())
    pages = discovery["pages"]
    languages = discovery["languages"]
    max_chars = discovery.get("max_chars_per_file", 6000)
    include_mermaid = discovery.get("include_mermaid", True)

    if not pages:
        print("[wiki-gen] No pages to generate")
        return

    # Collect all unique source files across all pages
    all_sources: set[str] = set()
    for page_def in pages.values():
        all_sources.update(page_def.get("sources", []))

    client = get_client()

    # Pass 1: Summarize
    summaries = pass1_summarize(client, root, sorted(all_sources), max_chars)

    # Pass 2: Generate pages
    updated, failed = pass2_generate(
        client, root, pages, summaries, languages,
        include_mermaid, model, max_chars, action_path,
    )

    # Set GitHub Actions outputs
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"pages_updated={updated}\n")
            f.write(f"pages_failed={failed}\n")

    # Clean up discovery file
    discovery_path.unlink(missing_ok=True)

    if updated == 0 and failed > 0:
        print("ERROR: All pages failed to generate", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONPATH=. pytest tests/test_generate.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/generate.py tests/test_generate.py
git commit -m "feat: add two-pass wiki generation with Mermaid validation"
```

---

### Task 5: Push Script

**Files:**
- Create: `scripts/push_wiki.sh`

- [ ] **Step 1: Create push_wiki.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

# push_wiki.sh — Push generated wiki pages to GitHub wiki or create a PR.
#
# Environment variables:
#   WIKI_PAT          — GitHub PAT with repo/contents:write scope
#   PUSH_STRATEGY     — "direct" or "pr"
#   AUTO_MERGE        — "true" or "false"
#   GITHUB_REPOSITORY — owner/repo
#   GITHUB_OUTPUT     — path to GitHub Actions output file (optional)

WIKI_DIR="${GITHUB_WORKSPACE:-$(pwd)}/wiki"
REPO="${GITHUB_REPOSITORY}"
MAX_PUSH_RETRIES=2

if [ ! -d "$WIKI_DIR" ] || [ -z "$(ls -A "$WIKI_DIR"/*.md 2>/dev/null)" ]; then
    echo "[wiki-gen] No wiki pages to push"
    exit 0
fi

# Remove internal files
rm -f "$WIKI_DIR/_discovery.json"

push_direct() {
    local wiki_url="https://x-access-token:${WIKI_PAT}@github.com/${REPO}.wiki.git"
    local tmp_dir
    tmp_dir=$(mktemp -d)

    echo "[wiki-gen] Cloning wiki repo..."

    # Try cloning; if wiki doesn't exist, initialize it
    if ! git clone "$wiki_url" "$tmp_dir" 2>/dev/null; then
        echo "[wiki-gen] Wiki repo does not exist, initializing..."
        cd "$tmp_dir"
        git init
        git remote add origin "$wiki_url"
        echo "# Home" > Home.md
        git add Home.md
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git commit -m "docs: initialize wiki"
        git branch -M master
        git push -u origin master
    fi

    # Copy generated pages
    cp "$WIKI_DIR"/*.md "$tmp_dir/"
    cd "$tmp_dir"

    # Check for changes
    if [ -z "$(git status --porcelain)" ]; then
        echo "[wiki-gen] No changes to wiki"
        rm -rf "$tmp_dir"
        exit 0
    fi

    # Commit
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add *.md
    git commit -m "docs: auto-update wiki"

    # Push with retry on non-fast-forward
    local attempt=0
    while [ $attempt -le $MAX_PUSH_RETRIES ]; do
        if git push; then
            local sha
            sha=$(git rev-parse HEAD)
            echo "[wiki-gen] Wiki updated: $sha"
            if [ -n "${GITHUB_OUTPUT:-}" ]; then
                echo "wiki_commit_sha=$sha" >> "$GITHUB_OUTPUT"
            fi
            rm -rf "$tmp_dir"
            return 0
        fi
        echo "[wiki-gen] Push failed, pulling and retrying..."
        git pull --rebase
        attempt=$((attempt + 1))
    done

    echo "[wiki-gen] ERROR: Failed to push after $MAX_PUSH_RETRIES retries"
    rm -rf "$tmp_dir"
    exit 1
}

push_pr() {
    local branch="docs/wiki-update-$(git rev-parse --short HEAD)"
    local default_branch
    default_branch=$(gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name')

    echo "[wiki-gen] Creating PR branch: $branch"

    cd "${GITHUB_WORKSPACE:-$(pwd)}"
    git checkout -b "$branch"
    git add wiki/*.md
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git commit -m "docs: auto-update wiki pages"
    git push -u origin "$branch"

    echo "[wiki-gen] Creating PR..."
    local pr_url
    pr_url=$(gh pr create \
        --title "docs: auto-update wiki pages" \
        --body "Auto-generated wiki documentation update.

Pages updated:
$(ls "$WIKI_DIR"/*.md | xargs -I{} basename {} .md | sed 's/^/- /')" \
        --base "$default_branch" \
        --head "$branch")

    echo "[wiki-gen] PR created: $pr_url"

    if [ "${AUTO_MERGE}" = "true" ]; then
        echo "[wiki-gen] Enabling auto-merge..."
        gh pr merge --auto --squash "$pr_url" || \
            echo "[wiki-gen] WARNING: auto-merge failed (may need manual approval)"
    fi
}

# Main
echo "[wiki-gen] Push strategy: ${PUSH_STRATEGY}"

case "${PUSH_STRATEGY}" in
    direct)
        push_direct
        ;;
    pr)
        push_pr
        ;;
    *)
        echo "ERROR: Unknown push_strategy: ${PUSH_STRATEGY}"
        exit 1
        ;;
esac
```

- [ ] **Step 2: Make executable and commit**

```bash
chmod +x scripts/push_wiki.sh
git add scripts/push_wiki.sh
git commit -m "feat: add wiki push script with direct and PR strategies"
```

---

### Task 6: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Wiki Gen Action

Auto-generate wiki documentation for any GitHub project using the Anthropic Claude API. Language-agnostic, zero-config by default.

## Quick Start

Add to your repo's `.github/workflows/docs.yml`:

\```yaml
name: Generate Docs
on:
  push:
    branches: [main, master]

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: HanSur94/wiki-gen-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          wiki_pat: ${{ secrets.WIKI_PAT }}
\```

## How It Works

1. **Discover** — Scans your repo structure, detects languages, identifies what to document
2. **Summarize** (Pass 1) — Reads all source files and creates summaries using Claude Haiku
3. **Generate** (Pass 2) — Generates wiki pages with Mermaid diagrams using your chosen Claude model
4. **Push** — Updates your GitHub wiki (direct push or via PR)

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `anthropic_api_key` | Yes | — | Anthropic API key |
| `wiki_pat` | Yes | — | GitHub PAT (needs `repo` scope) |
| `model` | No | `claude-haiku-4-5` | Claude model for page generation |
| `config_path` | No | `.github/docs-config.yml` | Path to config file |
| `dry_run` | No | `false` | Generate without pushing |
| `push_strategy` | No | `direct` | `direct` or `pr` |
| `auto_merge` | No | `false` | Auto-merge PRs (with `pr` strategy) |

## Outputs

| Output | Description |
|--------|-------------|
| `pages_updated` | Number of pages successfully generated |
| `pages_failed` | Number of pages that failed |
| `wiki_commit_sha` | Git SHA of the wiki commit |

## Configuration

Create `.github/docs-config.yml` for custom control:

\```yaml
model: claude-haiku-4-5
max_chars_per_file: 6000
include_mermaid: true

source_dirs:
  - src/
  - lib/

exclude:
  - "*.test.*"
  - vendor/

pages:
  Home:
    sources: ["README.md"]
    prompt: "Write a welcoming overview..."

extra_pages:
  Deployment:
    sources: ["Dockerfile", "k8s/**/*"]
    prompt: "Document deployment options..."
\```

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with usage instructions"
```

---

### Task 7: Create GitHub Repo and Push

- [ ] **Step 1: Create the repo on GitHub and push**

```bash
cd /Users/hannessuhr/wiki-gen-action
gh repo create HanSur94/wiki-gen-action --public --source=. --push
```

- [ ] **Step 2: Create a v1 tag**

```bash
git tag v1
git push origin v1
```

---

## Part 2: gh-wiki-gen CLI Extension

All files created under `/Users/hannessuhr/gh-wiki-gen/`.

### Task 8: CLI Extension Scaffolding

**Files:**
- Create: `gh-wiki-gen` (main script)
- Create: `templates/docs.yml`
- Create: `templates/docs-config.yml`

- [ ] **Step 1: Initialize the repo**

```bash
mkdir -p /Users/hannessuhr/gh-wiki-gen/templates
cd /Users/hannessuhr/gh-wiki-gen
git init
```

- [ ] **Step 2: Create the workflow template**

Create `templates/docs.yml`:

```yaml
name: Generate Docs
on:
  push:
    branches: [{{DEFAULT_BRANCH}}]
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no wiki push)'
        type: boolean
        default: false

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  docs:
    runs-on: ubuntu-latest
    {{NEEDS_CI}}
    steps:
      - uses: actions/checkout@v4
      - uses: HanSur94/wiki-gen-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          wiki_pat: ${{ secrets.WIKI_PAT }}
          dry_run: ${{ inputs.dry_run || 'false' }}
          {{EXTRA_INPUTS}}
```

- [ ] **Step 3: Create the config template**

Create `templates/docs-config.yml`:

```yaml
# Wiki Gen Action Configuration
# See: https://github.com/HanSur94/wiki-gen-action

# Claude model for page generation (Pass 1 always uses claude-haiku-4-5)
# model: claude-haiku-4-5

# Max characters per source file (default: 6000)
# max_chars_per_file: 6000

# Include Mermaid diagrams in generated pages (default: true)
# include_mermaid: true

# Restrict which directories to scan (default: entire repo)
# source_dirs:
#   - src/
#   - lib/

# Exclude patterns (glob syntax)
# exclude:
#   - "*.test.*"
#   - "vendor/"
#   - "node_modules/"

# Custom page definitions (overrides auto-discovery)
# pages:
#   Home:
#     sources: ["README.md"]
#     prompt: "Write a welcoming overview..."

# Extra pages (appended to auto-discovery or custom pages)
# extra_pages:
#   Deployment:
#     sources: ["Dockerfile", "k8s/**/*"]
#     prompt: "Document deployment options..."
```

- [ ] **Step 4: Create the main extension script**

Create `gh-wiki-gen`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# gh-wiki-gen — GitHub CLI extension for bootstrapping wiki-gen-action
# Install: gh extension install HanSur94/gh-wiki-gen
# Usage:   gh wiki-gen init | status | run | dry-run

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

die() { echo "Error: $*" >&2; exit 1; }
info() { echo "==> $*"; }
warn() { echo "WARNING: $*" >&2; }

get_repo() {
    local repo_flag=""
    # Check for --repo flag in args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) repo_flag="$2"; shift 2 ;;
            --repo=*) repo_flag="${1#*=}"; shift ;;
            *) shift ;;
        esac
    done
    if [ -n "$repo_flag" ]; then
        echo "$repo_flag"
    else
        gh repo view --json nameWithOwner --jq '.nameWithOwner' 2>/dev/null || \
            die "Not in a git repo and no --repo specified"
    fi
}

get_default_branch() {
    gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name' 2>/dev/null || echo "main"
}

has_ci_workflow() {
    [ -f ".github/workflows/ci.yml" ] || [ -f ".github/workflows/ci.yaml" ]
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_init() {
    local model="" push_strategy="" auto_merge="false" repo_arg=""

    # Parse flags
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --model) model="$2"; shift 2 ;;
            --model=*) model="${1#*=}"; shift ;;
            --push-strategy) push_strategy="$2"; shift 2 ;;
            --push-strategy=*) push_strategy="${1#*=}"; shift ;;
            --auto-merge) auto_merge="true"; shift ;;
            --repo) repo_arg="$2"; shift 2 ;;
            --repo=*) repo_arg="${1#*=}"; shift ;;
            *) shift ;;
        esac
    done

    local repo
    repo="${repo_arg:-$(get_repo)}"
    local default_branch
    default_branch=$(get_default_branch)

    info "Setting up wiki-gen for: $repo (branch: $default_branch)"

    # 1. Create workflow file
    mkdir -p .github/workflows

    local needs_ci=""
    if has_ci_workflow; then
        needs_ci="needs: [ci]"
        info "CI workflow detected, adding dependency"
    fi

    local extra_inputs=""
    if [ -n "$model" ]; then
        extra_inputs="${extra_inputs}model: '$model'\n          "
    fi
    if [ -n "$push_strategy" ]; then
        extra_inputs="${extra_inputs}push_strategy: '$push_strategy'\n          "
    fi
    if [ "$auto_merge" = "true" ]; then
        extra_inputs="${extra_inputs}auto_merge: 'true'\n          "
    fi

    sed -e "s|{{DEFAULT_BRANCH}}|$default_branch|g" \
        -e "s|{{NEEDS_CI}}|$needs_ci|g" \
        -e "s|{{EXTRA_INPUTS}}|$extra_inputs|g" \
        "$TEMPLATES_DIR/docs.yml" > .github/workflows/docs.yml

    # Clean up empty lines from template substitution
    sed -i.bak '/^[[:space:]]*$/{ N; /^\n[[:space:]]*$/d; }' .github/workflows/docs.yml 2>/dev/null || true
    rm -f .github/workflows/docs.yml.bak

    info "Created .github/workflows/docs.yml"

    # 2. Set up secrets
    echo ""
    read -rp "Set up ANTHROPIC_API_KEY as a repo secret? (Y/n) " yn
    case "$yn" in
        [Nn]*) ;;
        *)
            read -rsp "Enter your Anthropic API key: " api_key
            echo ""
            echo "$api_key" | gh secret set ANTHROPIC_API_KEY --repo="$repo"
            info "ANTHROPIC_API_KEY secret set"
            ;;
    esac

    read -rp "Set up WIKI_PAT as a repo secret? (Y/n) " yn
    case "$yn" in
        [Nn]*) ;;
        *)
            read -rsp "Enter your GitHub PAT (needs repo scope): " pat
            echo ""
            echo "$pat" | gh secret set WIKI_PAT --repo="$repo"
            info "WIKI_PAT secret set"
            ;;
    esac

    # 3. Optional config file
    echo ""
    read -rp "Create a docs config file for customization? (y/N) " yn
    case "$yn" in
        [Yy]*)
            mkdir -p .github
            cp "$TEMPLATES_DIR/docs-config.yml" .github/docs-config.yml
            info "Created .github/docs-config.yml"
            ;;
    esac

    # 4. Summary
    echo ""
    echo "=============================="
    echo "Wiki generation configured for $repo"
    echo "  Workflow: .github/workflows/docs.yml"
    echo "  Secrets:  ANTHROPIC_API_KEY  WIKI_PAT"
    echo "  Config:   .github/docs-config.yml (optional)"
    echo ""
    echo "Push to trigger:"
    echo "  git add . && git commit -m 'ci: add wiki generation' && git push"
    echo "=============================="
}

parse_repo_flag() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --repo) echo "$2"; return ;;
            --repo=*) echo "${1#*=}"; return ;;
            *) shift ;;
        esac
    done
    get_repo
}

cmd_status() {
    local repo
    repo=$(parse_repo_flag "$@")
    info "Last docs workflow runs for $repo:"
    gh run list --workflow=docs.yml --limit=3 --repo="$repo"
}

cmd_run() {
    local repo
    repo=$(parse_repo_flag "$@")
    info "Triggering docs generation for $repo..."
    gh workflow run docs.yml --repo="$repo"
    info "Workflow triggered. Check status with: gh wiki-gen status"
}

cmd_dry_run() {
    local repo
    repo=$(parse_repo_flag "$@")
    info "Triggering docs dry-run for $repo..."
    gh workflow run docs.yml -f dry_run=true --repo="$repo"
    info "Dry-run triggered. Check status with: gh wiki-gen status"
}

cmd_help() {
    cat <<EOF
gh wiki-gen v${VERSION} — Auto-generate wiki docs with Claude API

USAGE
  gh wiki-gen <command> [flags]

COMMANDS
  init      Set up wiki generation for the current repo
  status    Show recent docs workflow runs
  run       Manually trigger docs generation
  dry-run   Trigger a dry-run (no wiki push)
  help      Show this help

FLAGS (init)
  --repo <owner/repo>         Target a different repo
  --model <model>             Override Claude model
  --push-strategy <direct|pr> Set push strategy
  --auto-merge                Enable auto-merge for PRs

EXAMPLES
  gh wiki-gen init
  gh wiki-gen init --model claude-sonnet-4-5-20250514 --push-strategy pr
  gh wiki-gen status
  gh wiki-gen run
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    init)     cmd_init "$@" ;;
    status)   cmd_status "$@" ;;
    run)      cmd_run "$@" ;;
    dry-run)  cmd_dry_run "$@" ;;
    help|--help|-h) cmd_help ;;
    *)        die "Unknown command: $COMMAND. Run 'gh wiki-gen help'" ;;
esac
```

- [ ] **Step 5: Make executable and commit**

```bash
chmod +x gh-wiki-gen
git add gh-wiki-gen templates/
git commit -m "feat: add gh wiki-gen CLI extension with init, status, run, dry-run"
```

---

### Task 9: CLI Extension README and Publish

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# gh-wiki-gen

GitHub CLI extension to bootstrap [wiki-gen-action](https://github.com/HanSur94/wiki-gen-action) — auto-generate wiki documentation using Claude API.

## Install

\```bash
gh extension install HanSur94/gh-wiki-gen
\```

## Usage

\```bash
# Set up wiki generation for your repo
gh wiki-gen init

# Check status of last docs run
gh wiki-gen status

# Manually trigger docs generation
gh wiki-gen run

# Preview without pushing (dry-run)
gh wiki-gen dry-run
\```

## Init Options

\```bash
gh wiki-gen init --model claude-sonnet-4-5-20250514    # Use a different model
gh wiki-gen init --push-strategy pr              # Create PRs instead of direct push
gh wiki-gen init --auto-merge                    # Auto-merge doc PRs
gh wiki-gen init --repo owner/other-repo         # Target a different repo
\```

## What `init` Does

1. Creates `.github/workflows/docs.yml` with wiki-gen-action
2. Detects your default branch and CI workflow
3. Prompts to set `ANTHROPIC_API_KEY` and `WIKI_PAT` as repo secrets
4. Optionally creates `.github/docs-config.yml` for customization

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

- [ ] **Step 3: Create GitHub repo and push**

```bash
cd /Users/hannessuhr/gh-wiki-gen
gh repo create HanSur94/gh-wiki-gen --public --source=. --push
```

---

## Part 3: Integration Test

### Task 10: Test on matlab-mcp-server-python

- [ ] **Step 1: Update the existing docs.yml to use the new action**

In `/Users/hannessuhr/matlab-mcp-server-python/.github/workflows/docs.yml`, replace the current workflow with:

```yaml
name: Generate Docs
on:
  push:
    branches: [master]
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (no wiki push)'
        type: boolean
        default: false

concurrency:
  group: docs-${{ github.ref }}
  cancel-in-progress: true

jobs:
  docs:
    runs-on: ubuntu-latest
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: HanSur94/wiki-gen-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          wiki_pat: ${{ secrets.WIKI_PAT }}
          dry_run: ${{ inputs.dry_run || 'false' }}
```

Note: `needs: [lint, test]` references jobs from the existing `ci.yml`. This ensures docs only generate after CI passes.

- [ ] **Step 2: Commit and push to test**

```bash
cd /Users/hannessuhr/matlab-mcp-server-python
git add .github/workflows/docs.yml
git commit -m "ci: switch docs workflow to wiki-gen-action"
git push
```

- [ ] **Step 3: Monitor the workflow run**

```bash
gh run watch --repo HanSur94/matlab-mcp-server-python
```

- [ ] **Step 4: Verify wiki was updated**

Check the wiki at `https://github.com/HanSur94/matlab-mcp-server-python/wiki`
