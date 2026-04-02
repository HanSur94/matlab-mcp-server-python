"""HITL gate helpers — centralized elicitation logic.

Provides approval request functions for execute_code and file operations.
All functions are async and require a FastMCP Context for elicitation.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from pydantic import BaseModel

from matlab_mcp.config import HITLConfig

logger = logging.getLogger(__name__)


class HumanApproval(BaseModel):
    """User approval response for HITL gate."""

    approved: bool


DENIED = {"status": "denied", "message": "Operation blocked by HITL approval"}


async def _request_approval(ctx, message: str) -> bool:
    """Request human approval via elicitation.

    Parameters
    ----------
    ctx : Context
        FastMCP request context (must support elicit).
    message : str
        Human-readable description of what is being approved.

    Returns
    -------
    bool
        True if the human approved, False if declined or cancelled.
    """
    from fastmcp.server.context import AcceptedElicitation

    result = await ctx.elicit(message, HumanApproval)
    if isinstance(result, AcceptedElicitation):
        return result.data.approved
    return False


def _detect_protected_function(
    code: str, protected: list[str]
) -> Optional[str]:
    """Return first protected function name found in code, or None.

    Parameters
    ----------
    code : str
        MATLAB source code to scan.
    protected : list[str]
        Function names to search for.

    Returns
    -------
    str or None
        The first matched function name, or None if no match.
    """
    for func in protected:
        if func and re.search(rf"\b{re.escape(func)}\s*\(", code):
            return func
    return None


async def request_execute_approval(
    code: str,
    session_id: str,
    ctx,
    hitl_config: HITLConfig,
) -> Optional[dict]:
    """Check HITL gates for execute_code and request approval if needed.

    Returns None if execution should proceed, or a denied dict if blocked.

    Parameters
    ----------
    code : str
        MATLAB code about to be executed.
    session_id : str
        Current session identifier (for audit logging).
    ctx : Context
        FastMCP request context.
    hitl_config : HITLConfig
        HITL configuration.

    Returns
    -------
    dict or None
        None if approved (or HITL disabled), denied dict if blocked.
    """
    if not hitl_config.enabled:
        return None
    if ctx is None:
        return None

    snippet = code[:200]

    # HITL-02: all_execute gate — every execute_code call prompts
    if hitl_config.all_execute:
        message = (
            f"MATLAB code execution requested.\n"
            f"Code snippet: {snippet!r}\n"
            f"Approve to execute?"
        )
        approved = await _request_approval(ctx, message)
        logger.info(
            "HITL %s: all_execute session=%s",
            "approved" if approved else "denied",
            session_id,
        )
        if not approved:
            return dict(DENIED)
        return None

    # HITL-01: protected function gate
    matched = _detect_protected_function(
        code, hitl_config.protected_functions
    )
    if matched is not None:
        message = (
            f"MATLAB code calls protected function '{matched}'.\n"
            f"Code snippet: {snippet!r}\n"
            f"Approve to execute?"
        )
        approved = await _request_approval(ctx, message)
        logger.info(
            "HITL %s: function=%s session=%s",
            "approved" if approved else "denied",
            matched,
            session_id,
        )
        if not approved:
            return dict(DENIED)

    return None


async def request_file_approval(
    operation: str,
    filename: str,
    session_id: str,
    ctx,
    hitl_config: HITLConfig,
) -> Optional[dict]:
    """Check HITL gate for file operations and request approval if needed.

    Returns None if operation should proceed, or a denied dict if blocked.

    Parameters
    ----------
    operation : str
        Operation name, e.g. ``"upload"`` or ``"delete"``.
    filename : str
        The sanitized filename being operated on.
    session_id : str
        Current session identifier (for audit logging).
    ctx : Context
        FastMCP request context.
    hitl_config : HITLConfig
        HITL configuration.

    Returns
    -------
    dict or None
        None if approved (or HITL disabled), denied dict if blocked.
    """
    if not hitl_config.enabled:
        return None
    if not hitl_config.protect_file_ops:
        return None
    if ctx is None:
        return None

    message = (
        f"Agent wants to {operation} file '{filename}'. Approve?"
    )
    approved = await _request_approval(ctx, message)
    logger.info(
        "HITL %s %s: file=%s session=%s",
        operation,
        "approved" if approved else "denied",
        filename,
        session_id,
    )
    if not approved:
        return dict(DENIED)
    return None
