# Coding Conventions

**Analysis Date:** 2026-04-01

## Naming Patterns

**Files:**
- Module files use lowercase with underscores: `executor.py`, `security_validator.py`
- Test files use `test_<module_name>.py`: `test_session.py`, `test_security.py`
- Mock files use `<name>_mock.py`: `matlab_engine_mock.py`
- Package directories use lowercase with underscores: `matlab_mcp`, `matlab_mcp/tools`, `matlab_mcp/security`

**Functions:**
- Use snake_case for all functions: `execute_code_impl`, `check_code_impl`, `get_workspace_impl`
- Implementation functions commonly end with `_impl` suffix for clarity
- Async functions use `async def` prefix: `async def execute_code_impl(...)`
- Private/internal functions use leading underscore: `_strip_string_literals`, `_make_config`

**Variables:**
- Use snake_case for all variables and constants: `session_id`, `max_sessions`, `temp_dir`
- Constants (module-level, typically) use UPPERCASE: `_DEFAULT_SESSION_ID`, `_DEFAULT_MAX_SIZE_MB`
- Abbreviations expand naturally: `temp_dir` not `tmp_dir`, `session_id` not `sess_id`
- Thread locks use `_lock` suffix: `self._lock = threading.Lock()`

**Types:**
- Custom exception classes use PascalCase: `BlockedFunctionError`, `MatlabExecutionError`
- Dataclass and Pydantic model classes use PascalCase: `Session`, `Job`, `CustomToolParam`, `AppConfig`
- Type hints use full paths only when necessary for clarity (avoid noise)

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml` via `ruff`)
- Indentation: 4 spaces (Python default)
- Trailing commas in multiline collections encouraged for diffs

**Linting:**
- Tool: `ruff` (configured in `pyproject.toml`)
- Target version: Python 3.10+ (`target-version = "py310"`)
- Configuration minimal - only line-length and version specified

**Async/Await:**
- Async functions are marked `async def`
- All test methods that call async code are `async def test_*` (pytest-asyncio handles auto-execution via `asyncio_mode = "auto"`)
- Background operations use `asyncio.create_task()` for fire-and-forget

## Import Organization

**Order:**
1. Standard library imports (sys, asyncio, logging, pathlib, etc.)
2. Third-party imports (fastmcp, pydantic, yaml, pillow, etc.)
3. Local imports from `matlab_mcp` package (relative or absolute)

**Example from `src/matlab_mcp/server.py`:**
```python
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.server.context import Context

from matlab_mcp.config import AppConfig, load_config
from matlab_mcp.jobs.executor import JobExecutor
```

**Path Aliases:**
- No path aliases configured; all imports use full module paths from package root
- Absolute imports preferred over relative imports

**Future Annotations:**
- All modules use `from __future__ import annotations` at the top for forward reference support
- This is a universal practice across the codebase

## Error Handling

**Patterns:**
- Custom exceptions inherit from standard Python exceptions: `class BlockedFunctionError(Exception):`
- Error handling uses try/except blocks that catch specific exceptions when possible
- Generic `Exception as exc` used only when catching broad categories
- Security violations raise `BlockedFunctionError` with descriptive message
- File operations catch `FileNotFoundError`, `ValueError`, and generic `Exception` for disk issues
- Results return error dicts instead of raising exceptions where appropriate: `{"status": "error", "message": "..."}`

**Example from `src/matlab_mcp/tools/files.py`:**
```python
try:
    safe_name = security.sanitize_filename(filename)
except ValueError as exc:
    return {
        "status": "error",
        "message": f"Invalid filename: {exc}",
    }
```

## Logging

**Framework:** `logging` standard library

**Patterns:**
- Every module defines `logger = logging.getLogger(__name__)` near the top
- Log levels used appropriately:
  - `logger.debug()` for detailed diagnostic info
  - `logger.info()` for important lifecycle events (startup, shutdown, major state changes)
  - `logger.warning()` for recoverable issues
  - `logger.error()` rarely used; most errors return error dicts instead
- String formatting uses `%s` style with arguments: `logger.info("Starting pool with %d engines", num_engines)`
- Complex objects logged only at debug level

**Example from `src/matlab_mcp/output/formatter.py`:**
```python
logger.debug("Saved truncated output to %s", saved_path)
logger.warning("Failed to save output text: %s", exc)
```

## Comments

**When to Comment:**
- Docstrings required for all public classes and functions
- Inline comments rare; code should be self-explanatory
- Comments explain WHY something is done, not WHAT it does
- Section separators used: `# --------` lines with hyphens

**JSDoc/TSDoc:**
- NumPy-style docstrings used for comprehensive API documentation
- All parameters documented with type and description
- Returns section specifies return type and keys/structure
- Raises section documents exceptions that can be raised

**Example from `src/matlab_mcp/tools/core.py`:**
```python
async def execute_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    security: Any,
    temp_dir: Optional[str] = None,
) -> dict:
    """Execute MATLAB code with security check.

    Parameters
    ----------
    code:
        MATLAB source code to execute.
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.
    security:
        A :class:`~matlab_mcp.security.validator.SecurityValidator` instance.

    Returns
    -------
    dict
        Result dict with at minimum ``status`` and ``job_id`` keys.
        On security violation returns ``{"status": "failed", "error": {...}}``.
    """
```

## Function Design

**Size:** Functions typically 20-60 lines; longer functions broken into helper functions

**Parameters:**
- Maximum 4-5 positional parameters; additional parameters via context objects or config
- Keyword-only arguments used where clarity helps: `async def execute_code_impl(..., temp_dir: Optional[str] = None)`
- Type hints on all parameters and return values (even `Any` when necessary)

**Return Values:**
- Simple return values (dict, str, bool) preferred
- Complex returns use structured objects (dataclasses, Pydantic models)
- Async functions return coroutines that resolve to above types
- Implementation functions often return dicts: `{"status": "ok", "key": value}`

## Module Design

**Exports:**
- No explicit `__all__` lists; public functions/classes are those not starting with underscore
- Module docstrings at the top describe the module's purpose and main exports
- Internal utilities prefixed with underscore: `_strip_string_literals`, `_make_config`

**Barrel Files:**
- Minimal use of barrel files; `__init__.py` files mostly empty or import key classes
- `src/matlab_mcp/__init__.py` typically empty (no re-exports)
- Direct imports from submodules preferred

**Organization:**
- Related functions/classes grouped by responsibility in single files
- Config models (`config.py`) use Pydantic `BaseModel`
- Dataclass models use `@dataclass` decorator with `from dataclasses import`
- Each tool category has its own module: `tools/core.py`, `tools/files.py`, `tools/admin.py`

## Type Annotations

**Full Coverage:**
- All function parameters have type hints
- All return types specified (including `-> dict`, `-> None`)
- Class attributes typed (especially in dataclasses and Pydantic models)
- Optional parameters use `Optional[T]` or `T | None`

**Example from `src/matlab_mcp/session/manager.py`:**
```python
def create_session(self, *, session_id: Optional[str] = None) -> Session:
    """Create a new session with a temporary directory.
    
    Parameters
    ----------
    session_id
        Optional explicit ID for the session.  When *None* (the default),
        a random UUID is generated.
    """
```

---

*Convention analysis: 2026-04-01*
