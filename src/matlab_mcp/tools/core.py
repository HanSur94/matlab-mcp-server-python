"""Core MCP tool implementations for MATLAB MCP Server.

Provides the primary execution tools:
- execute_code_impl  — run MATLAB code (with security check)
- check_code_impl    — lint MATLAB code via checkcode/mlint
- get_workspace_impl — retrieve workspace variables via 'whos'
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from matlab_mcp.security.validator import BlockedFunctionError

logger = logging.getLogger(__name__)


async def execute_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    security: Any,
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
    # Check security blocklist first
    try:
        security.check_code(code)
    except BlockedFunctionError as exc:
        return {
            "status": "failed",
            "error": {
                "type": "ValidationError",
                "message": f"Blocked: {exc}",
                "matlab_id": None,
                "stack_trace": None,
            },
        }

    # Delegate to executor
    return await executor.execute(session_id=session_id, code=code)


async def check_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    temp_dir: str,
) -> dict:
    """Run checkcode/mlint on MATLAB code.

    Writes *code* to a temporary ``.m`` file, calls ``mcp_checkcode()`` via
    the executor, parses the JSON result, and cleans up the temp file.

    Parameters
    ----------
    code:
        MATLAB source code to check.
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.
    temp_dir:
        Temporary directory path for writing the ``.m`` file.

    Returns
    -------
    dict
        Parsed result from ``mcp_checkcode`` or an error dict.
    """
    # Write code to a temp .m file
    td = Path(temp_dir)
    td.mkdir(parents=True, exist_ok=True)

    tmp_file = td / f"_check_{session_id}.m"
    try:
        tmp_file.write_text(code, encoding="utf-8")

        # Build the MATLAB call
        escaped_path = str(tmp_file).replace("\\", "\\\\").replace("'", "\\'")
        matlab_cmd = f"mcp_checkcode('{escaped_path}')"

        result = await executor.execute(session_id=session_id, code=matlab_cmd)

        # Try to parse JSON from the output text
        if result.get("status") == "completed":
            raw_text = result.get("text", "")
            try:
                parsed = json.loads(raw_text)
                return {"status": "completed", "issues": parsed}
            except (json.JSONDecodeError, ValueError):
                # Return raw text if not valid JSON
                return {"status": "completed", "issues": [], "raw": raw_text}

        return result
    finally:
        # Clean up temp file
        try:
            if tmp_file.exists():
                tmp_file.unlink()
        except Exception:
            logger.debug("Failed to remove temp file %s", tmp_file)


async def get_workspace_impl(
    session_id: str,
    executor: Any,
) -> dict:
    """Get workspace variables via 'whos'.

    Parameters
    ----------
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.

    Returns
    -------
    dict
        Result dict with variables list or raw whos output.
    """
    result = await executor.execute(session_id=session_id, code="whos")
    return result
