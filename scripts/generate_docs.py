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
        "Execution & Workspace": ["execute_code", "check_code", "get_workspace"],
        "Job Management": ["get_job_status", "get_job_result", "cancel_job", "list_jobs"],
        "Discovery": ["list_toolboxes", "list_functions", "get_help"],
        "File Operations": ["upload_data", "delete_file", "list_files", "read_script", "read_data", "read_image"],
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
