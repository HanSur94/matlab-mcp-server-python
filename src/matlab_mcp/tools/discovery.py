"""Toolbox and function discovery MCP tool implementations.

Provides:
- list_toolboxes_impl  — list available MATLAB toolboxes
- list_functions_impl  — list functions in a toolbox
- get_help_impl        — get help text for a function
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

# Valid MATLAB identifier or toolbox name: alphanumeric, underscores, dots, slashes
_SAFE_NAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_./ ]*$')

logger = logging.getLogger(__name__)


def _validate_matlab_name(name: str, label: str) -> tuple[Optional[str], Optional[dict]]:
    """Sanitize and validate a MATLAB name for use in ``help`` commands.

    Returns ``(safe_name, None)`` on success or ``(None, error_dict)`` on failure.
    """
    safe = name.replace("'", "").replace('"', "").strip()
    if not _SAFE_NAME_RE.match(safe):
        return None, {
            label: name,
            "status": "failed",
            "error": f"Invalid {label}: must contain only alphanumeric characters, underscores, dots, slashes, and spaces",
        }
    return safe, None


async def list_toolboxes_impl(
    session_id: str,
    executor: Any,
    toolbox_config: Optional[Any] = None,
) -> dict:
    """List available MATLAB toolboxes by running ``ver``.

    Parameters
    ----------
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.
    toolbox_config:
        Optional ``ToolboxesConfig`` instance with mode/list info to annotate results.

    Returns
    -------
    dict
        Result dict with toolbox listing and optional config info.
    """
    result = await executor.execute(session_id=session_id, code="ver")

    output: dict = {
        "status": result.get("status"),
        "job_id": result.get("job_id"),
        "text": result.get("text", ""),
    }

    # Annotate with config info if available
    if toolbox_config is not None:
        output["toolbox_mode"] = toolbox_config.mode
        output["toolbox_list"] = toolbox_config.list

    return output


async def list_functions_impl(
    toolbox_name: str,
    session_id: str,
    executor: Any,
) -> dict:
    """List functions in a toolbox by running ``help <toolbox>``.

    Parameters
    ----------
    toolbox_name:
        Name of the toolbox to query.
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.

    Returns
    -------
    dict
        Result dict with the help text for the toolbox.
    """
    safe_name, err = _validate_matlab_name(toolbox_name, "toolbox_name")
    if err is not None:
        return err
    matlab_cmd = f"help {safe_name}"
    result = await executor.execute(session_id=session_id, code=matlab_cmd)
    return {
        "toolbox_name": toolbox_name,
        "status": result.get("status"),
        "job_id": result.get("job_id"),
        "text": result.get("text", ""),
    }


async def get_help_impl(
    function_name: str,
    session_id: str,
    executor: Any,
) -> dict:
    """Get help text for a MATLAB function.

    Parameters
    ----------
    function_name:
        The function name to look up.
    session_id:
        ID of the owning session.
    executor:
        A :class:`~matlab_mcp.jobs.executor.JobExecutor` instance.

    Returns
    -------
    dict
        Result dict with the help text.
    """
    safe_name, err = _validate_matlab_name(function_name, "function_name")
    if err is not None:
        return err
    matlab_cmd = f"help {safe_name}"
    result = await executor.execute(session_id=session_id, code=matlab_cmd)
    return {
        "function_name": function_name,
        "status": result.get("status"),
        "job_id": result.get("job_id"),
        "text": result.get("text", ""),
    }
