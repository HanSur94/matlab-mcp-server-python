"""Core MCP tool implementations for MATLAB MCP Server.

Provides the primary execution tools:
- execute_code_impl  — run MATLAB code (with security check)
- check_code_impl    — lint MATLAB code via checkcode/mlint
- get_workspace_impl — retrieve workspace variables via 'whos'
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from matlab_mcp.hitl.gate import request_execute_approval
from matlab_mcp.security.validator import BlockedFunctionError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# F6 structured output models (schema-additive)
# ---------------------------------------------------------------------------
#
# ``execute_code_impl``/``check_code_impl`` keep returning plain dicts (their
# contract is unchanged — see tests in ``tests/test_tools.py``). These models
# are a *typed view* built by the ``execute_code``/``check_code`` tool
# wrappers in ``server.py`` purely so FastMCP can emit an output schema and
# ``structuredContent`` alongside the existing wire shape.
#
# Wire-compat strategy: every field the underlying dicts may or may not carry
# is declared ``Optional`` with a default of ``None``. ``to_wire_dict()`` dumps
# with ``exclude_none=True`` so only the keys actually present on a given
# code path are serialized — reproducing the exact pre-change dict shape.
# Nested dicts (``error``) are typed as plain ``dict`` (not a nested Pydantic
# model) so ``exclude_none`` only prunes *top-level* None fields and does not
# recurse into — and strip legitimate ``None``-valued keys from — the nested
# error dict (e.g. ``error["matlab_id"]`` is `None` on validation errors but
# the key itself must remain present on the wire).


class ExecuteResult(BaseModel):
    """Typed, schema-additive view of an ``execute_code`` result dict.

    Parameters
    ----------
    status:
        Execution status: ``"completed"``, ``"pending"``, ``"failed"``, or
        ``"denied"`` (HITL rejection).
    job_id:
        Job identifier. Absent when a request is rejected before a job is
        created (e.g. a blocked-function security violation).
    message:
        Present only on the HITL ``"denied"`` path.
    text:
        Captured stdout/stderr text. Present on ``"completed"``.
    variables:
        Workspace variables snapshot. Present on ``"completed"``.
    figures:
        Plotly-converted figures. Present on ``"completed"``.
    files:
        Files written to the session temp dir. Present on ``"completed"``.
    warnings:
        Execution warnings. Present on ``"completed"``.
    errors:
        Execution errors (non-fatal). Present on ``"completed"``.
    error:
        Structured error dict (``type``, ``message``, ``matlab_id``,
        ``stack_trace``). Present on ``"failed"``.
    """

    status: str
    job_id: Optional[str] = None
    message: Optional[str] = None
    text: Optional[str] = None
    variables: Optional[dict] = None
    figures: Optional[list] = None
    files: Optional[list] = None
    warnings: Optional[list] = None
    errors: Optional[list] = None
    error: Optional[dict] = None

    def to_wire_dict(self) -> dict:
        """Serialize back to the exact pre-change dict shape.

        Returns
        -------
        dict
            ``model_dump(exclude_none=True)`` — only keys that were actually
            populated are emitted, matching the legacy dict wire shape.
        """
        return self.model_dump(exclude_none=True)


class CheckResult(BaseModel):
    """Typed, schema-additive view of a ``check_code`` result dict.

    Parameters
    ----------
    status:
        Check status: ``"completed"``, ``"pending"``, or ``"failed"``
        (checkcode is executed via the same executor as ``execute_code``, so
        the non-completed statuses can pass through unchanged).
    issues:
        Parsed ``mcp_checkcode`` JSON issues list. Present when the raw
        output parsed as JSON.
    raw:
        Raw checkcode text output. Present as a fallback when JSON parsing
        of the checkcode output failed.
    job_id:
        Job identifier, present on the pass-through ``"pending"``/``"failed"``
        paths.
    error:
        Structured error dict, present on the pass-through ``"failed"`` path.
    """

    status: str
    issues: Optional[Any] = None
    raw: Optional[str] = None
    job_id: Optional[str] = None
    error: Optional[dict] = None

    def to_wire_dict(self) -> dict:
        """Serialize back to the exact pre-change dict shape.

        Returns
        -------
        dict
            ``model_dump(exclude_none=True)`` — only keys that were actually
            populated are emitted, matching the legacy dict wire shape.
        """
        return self.model_dump(exclude_none=True)


async def execute_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    security: Any,
    temp_dir: Optional[str] = None,
    ctx: Optional[Any] = None,
    hitl_config: Optional[Any] = None,
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
    temp_dir:
        Optional temporary directory path for the session.
    ctx:
        Optional FastMCP request context used for HITL elicitation.
    hitl_config:
        Optional :class:`~matlab_mcp.config.HITLConfig` instance.
        When provided alongside ``ctx``, the HITL gate is evaluated before
        execution.

    Returns
    -------
    dict
        Result dict with at minimum ``status`` and ``job_id`` keys.
        On security violation returns ``{"status": "failed", "error": {...}}``.
        On HITL denial returns ``{"status": "denied", "message": ...}``.
    """
    # Defense-in-depth: executor also checks, but pre-check catches early
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

    # HITL approval gate (after security check, before execution)
    if ctx is not None and hitl_config is not None:
        denied = await request_execute_approval(
            code=code,
            session_id=session_id,
            ctx=ctx,
            hitl_config=hitl_config,
        )
        if denied is not None:
            return denied

    # Delegate to executor
    return await executor.execute(session_id=session_id, code=code, temp_dir=temp_dir)


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
        escaped_path = str(tmp_file).replace("\\", "\\\\").replace("'", "''")
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
