"""Toolbox and function discovery MCP tool implementations.

Provides:
- list_toolboxes_impl  — list available MATLAB toolboxes
- list_functions_impl  — list functions in a toolbox
- get_help_impl        — get help text for a function
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    # Sanitize toolbox_name to prevent injection
    safe_name = toolbox_name.replace("'", "").replace('"', "").strip()
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
    # Sanitize to prevent injection
    safe_name = function_name.replace("'", "").replace('"', "").strip()
    matlab_cmd = f"help {safe_name}"
    result = await executor.execute(session_id=session_id, code=matlab_cmd)
    return {
        "function_name": function_name,
        "status": result.get("status"),
        "job_id": result.get("job_id"),
        "text": result.get("text", ""),
    }
