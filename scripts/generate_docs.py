#!/usr/bin/env python3
"""Generate all wiki pages for matlab-mcp-server using Claude API.

For each wiki page, reads relevant source files + the existing page as seed,
then calls Claude Haiku to produce an updated version. MCP-Tools-Reference
uses AST extraction for structured metadata; all other pages use raw source
file context.

Usage:
    ANTHROPIC_API_KEY=sk-... python scripts/generate_docs.py

Output:
    wiki/*.md (11 pages)
"""
from __future__ import annotations

import ast
import json
import os
import sys
import time
from pathlib import Path

MODEL = "claude-haiku-4-5"
MAX_RETRIES = 2
TIMEOUT = 60
WIKI_DIR = Path("wiki")

# ---------------------------------------------------------------------------
# Page definitions: wiki page name -> (source files with truncation limits, prompt)
# ---------------------------------------------------------------------------

PAGES: dict[str, dict] = {
    "Home": {
        "sources": [("README.md", 12000), ("pyproject.toml", 4000)],
        "prompt": (
            "Update this Home page for the matlab-mcp-server wiki. "
            "It should be a concise overview: what the project does, key features, "
            "links to other wiki pages, and a quick-start snippet. "
            "Keep it welcoming and scannable."
        ),
    },
    "Installation": {
        "sources": [
            ("README.md", 12000),
            ("pyproject.toml", 4000),
            ("Dockerfile", 4000),
            ("docker-compose.yml", 4000),
        ],
        "prompt": (
            "Update this Installation page. Cover: pip install, from source, "
            "Docker (Dockerfile + docker-compose), Python version requirements, "
            "and MATLAB engine setup. Use the source files for accurate commands and versions."
        ),
    },
    "Configuration": {
        "sources": [("config.yaml", 8000), ("src/matlab_mcp/config.py", 8000)],
        "prompt": (
            "Update this Configuration page. Document all config sections, "
            "their fields, defaults, and types. Use the Pydantic models in config.py "
            "and the example config.yaml as the source of truth. Include environment "
            "variable override syntax (MATLAB_MCP_<SECTION>_<KEY>)."
        ),
    },
    "Architecture": {
        "sources": [
            ("src/matlab_mcp/server.py", 6000),
            ("src/matlab_mcp/pool/manager.py", 6000),
            ("src/matlab_mcp/pool/engine.py", 6000),
            ("src/matlab_mcp/jobs/executor.py", 6000),
            ("src/matlab_mcp/session/manager.py", 6000),
            ("src/matlab_mcp/output/formatter.py", 6000),
        ],
        "prompt": (
            "Update this Architecture page. Describe the system components: "
            "server entry point, engine pool, job executor, session manager, "
            "output formatter, security validator, monitoring. Show how they "
            "connect. Use the source code to verify component relationships."
        ),
    },
    "MCP-Tools-Reference": {
        "sources": [],  # Special case: uses AST extraction
        "prompt": "",  # Has its own prompt in generate_tools_reference()
    },
    "Async-Jobs": {
        "sources": [
            ("src/matlab_mcp/jobs/executor.py", 6000),
            ("src/matlab_mcp/jobs/models.py", 6000),
            ("src/matlab_mcp/jobs/tracker.py", 6000),
        ],
        "prompt": (
            "Update this Async Jobs page. Document the job lifecycle: "
            "sync execution, async promotion (when sync_timeout is exceeded), "
            "job status polling, progress reporting via mcp_progress.m, "
            "job result retrieval, cancellation, and retention/cleanup."
        ),
    },
    "Custom-Tools": {
        "sources": [
            ("custom_tools.yaml", 4000),
            ("examples/custom_tools.yaml", 4000),
            ("src/matlab_mcp/tools/custom.py", 4000),
        ],
        "prompt": (
            "Update this Custom Tools page. Document how to define custom "
            "MATLAB functions as MCP tools via custom_tools.yaml. Cover the "
            "YAML schema (name, description, parameters, code), examples, "
            "and how they are loaded and registered at startup."
        ),
    },
    "Security": {
        "sources": [
            ("src/matlab_mcp/security/validator.py", 6000),
            ("config.yaml", 4000),
        ],
        "prompt": (
            "Update this Security page. Document: blocked functions list, "
            "filename sanitization, upload size limits, proxy auth, "
            "workspace isolation, and security best practices."
        ),
    },
    "Examples": {
        "sources": [
            ("examples/basic_usage.m", 4000),
            ("examples/async_simulation.m", 4000),
            ("examples/plotting_examples.m", 4000),
            ("examples/signal_processing.m", 4000),
        ],
        "prompt": (
            "Update this Examples page. Show practical usage examples: "
            "basic MATLAB execution, async simulations, plotting with Plotly "
            "conversion, signal processing. Use the actual .m files as the "
            "source of truth for code snippets."
        ),
    },
    "FAQ": {
        "sources": [("README.md", 12000)],
        "prompt": (
            "Update this FAQ page. Answer common questions about: "
            "supported MATLAB versions, MCP client compatibility, "
            "Docker usage, troubleshooting, performance, and security."
        ),
    },
    "Troubleshooting": {
        "sources": [("README.md", 12000), ("config.yaml", 4000)],
        "prompt": (
            "Update this Troubleshooting page. Cover common issues: "
            "MATLAB engine connection failures, pool startup problems, "
            "timeout tuning, logging configuration, Docker networking, "
            "and how to enable debug logging."
        ),
    },
}

# ---------------------------------------------------------------------------
# Source file reading
# ---------------------------------------------------------------------------


def read_source_file(path: str, max_chars: int) -> str | None:
    """Read a source file, truncated to max_chars. Returns None if missing."""
    p = Path(path)
    if not p.exists():
        print(f"  WARNING: Source file not found: {path}", file=sys.stderr)
        return None
    content = p.read_text()
    if len(content) > max_chars:
        content = content[:max_chars] + f"\n\n... (truncated at {max_chars} chars)"
    return content


def read_sources(sources: list[tuple[str, int]]) -> str:
    """Read all source files for a page, formatted as labeled sections."""
    parts: list[str] = []
    for path, max_chars in sources:
        content = read_source_file(path, max_chars)
        if content:
            parts.append(f"### File: {path}\n```\n{content}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# AST extraction for MCP-Tools-Reference (preserved from original)
# ---------------------------------------------------------------------------


def extract_tools(source: str) -> list[dict]:
    """Parse server.py AST and extract @mcp.tool function metadata."""
    tree = ast.parse(source)
    tools: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_tool = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr == "tool":
                is_tool = True
            elif isinstance(dec, ast.Name) and dec.id == "tool":
                is_tool = True
            elif isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Attribute) and func.attr == "tool":
                    is_tool = True
                elif isinstance(func, ast.Name) and func.id == "tool":
                    is_tool = True
        if not is_tool:
            continue

        docstring = ast.get_docstring(node) or ""

        params: list[dict] = []
        for arg in node.args.args:
            name = arg.arg
            if name in ("self", "ctx"):
                continue
            type_str = ""
            if arg.annotation:
                type_str = ast.unparse(arg.annotation)
            params.append({
                "name": name,
                "type": type_str,
                "required": True,
                "default": None,
            })

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
        "File Operations": [
            "upload_data", "delete_file", "list_files",
            "read_script", "read_data", "read_image",
        ],
        "Admin": ["get_pool_status"],
        "Monitoring": ["get_server_metrics", "get_server_health", "get_error_log"],
    }

    tool_map = {t["name"]: t for t in tools}
    result: dict[str, list[dict]] = {}

    for category, names in categories.items():
        cat_tools = [tool_map[n] for n in names if n in tool_map]
        if cat_tools:
            result[category] = cat_tools

    categorized = {n for names in categories.values() for n in names}
    uncategorized = [t for t in tools if t["name"] not in categorized]
    if uncategorized:
        result["Other"] = uncategorized

    return result


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

REFUSAL_PREFIXES = ("I'm sorry", "I cannot", "I apologize", "Sorry,")


def get_client():
    """Create and return an Anthropic client."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    return anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT)


def call_api(client, prompt: str, max_tokens: int = 8000) -> str | None:
    """Call Claude API with retry logic. Returns None on failure."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text

            # Validate output
            if not text or not text.strip():
                print("  WARNING: API returned empty output", file=sys.stderr)
                return None
            if text.lstrip().startswith(REFUSAL_PREFIXES):
                print(f"  WARNING: API returned refusal: {text[:80]}...", file=sys.stderr)
                return None

            return text
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt + 1)
                print(f"  API call failed ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"  ERROR: API call failed after {MAX_RETRIES + 1} attempts: {e}", file=sys.stderr)
                return None
    return None


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------


def generate_tools_reference(client) -> str | None:
    """Generate MCP-Tools-Reference using AST extraction (special case)."""
    server_py = Path("src/matlab_mcp/server.py")
    if not server_py.exists():
        print(f"  ERROR: {server_py} not found", file=sys.stderr)
        return None

    source = server_py.read_text()
    tools = extract_tools(source)
    print(f"  Extracted {len(tools)} MCP tools via AST")
    categorized = categorize_tools(tools)

    style_ref = ""
    wiki_file = WIKI_DIR / "MCP-Tools-Reference.md"
    if wiki_file.exists():
        style_ref = wiki_file.read_text()

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
- Start with: "# MCP Tools Reference\\n\\nThe server exposes {len(tools)} built-in tools plus any custom tools defined in your `custom_tools.yaml`."
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
    return call_api(client, prompt)


def generate_generic_page(client, page_name: str, page_def: dict) -> str | None:
    """Generate a wiki page using source files as context."""
    source_context = read_sources(page_def["sources"])
    if not source_context:
        print(f"  WARNING: No source files available for {page_name}", file=sys.stderr)
        return None

    existing = ""
    wiki_file = WIKI_DIR / f"{page_name}.md"
    if wiki_file.exists():
        existing = wiki_file.read_text()

    prompt = f"""{page_def['prompt']}

Keep the existing structure and tone. Update content to match the current source code.
Do not remove sections unless the feature no longer exists.
Add new sections if the source code reveals undocumented features.
Output ONLY the updated markdown, no surrounding explanation.

## Existing page content:
```markdown
{existing[:8000]}
```

## Source code context:
{source_context}
"""
    return call_api(client, prompt)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    client = get_client()

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    failed_pages: list[str] = []
    updated_pages: list[str] = []

    for page_name, page_def in PAGES.items():
        print(f"\n{'='*60}")
        print(f"Generating: {page_name}")
        print(f"{'='*60}")

        # Special case for MCP-Tools-Reference
        if page_name == "MCP-Tools-Reference":
            result = generate_tools_reference(client)
        else:
            result = generate_generic_page(client, page_name, page_def)

        if result is None:
            print(f"  FAILED: {page_name}")
            failed_pages.append(page_name)
            continue

        output_path = WIKI_DIR / f"{page_name}.md"
        output_path.write_text(result)
        updated_pages.append(page_name)
        print(f"  OK: Written {len(result)} chars to {output_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary: {len(updated_pages)} updated, {len(failed_pages)} failed")
    if updated_pages:
        print(f"  Updated: {', '.join(updated_pages)}")
    if failed_pages:
        print(f"  Failed:  {', '.join(failed_pages)}")
    print(f"{'='*60}")

    if failed_pages:
        sys.exit(1)


if __name__ == "__main__":
    main()
