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
