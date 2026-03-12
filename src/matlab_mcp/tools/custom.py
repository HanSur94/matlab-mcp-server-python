"""Custom tool support for MATLAB MCP Server.

Provides:
- CustomToolParam  — pydantic model for a tool parameter definition
- CustomToolDef    — pydantic model for a complete custom tool definition
- load_custom_tools  — load custom tools from a YAML config file
- make_custom_tool_handler  — factory that creates a typed async handler function
  with a proper ``inspect.Signature`` so FastMCP can introspect it correctly.
"""
from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_TYPE_MAP: Dict[str, type] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "number": float,
    "bool": bool,
    "boolean": bool,
    "list": list,
    "dict": dict,
    "any": Any,
}


class CustomToolParam(BaseModel):
    """Definition of a single parameter for a custom tool.

    Parameters
    ----------
    name:
        Parameter name (valid Python identifier).
    type:
        Parameter type as a string (e.g. ``"str"``, ``"int"``, ``"float"``).
    required:
        Whether the parameter is required.  Defaults to True.
    default:
        Default value when ``required`` is False.
    """

    name: str
    type: str = "str"
    required: bool = True
    default: Optional[Any] = None


class CustomToolDef(BaseModel):
    """Definition of a custom MATLAB-backed tool.

    Parameters
    ----------
    name:
        Tool name (used as the MCP tool name).
    matlab_function:
        MATLAB function to call when this tool is invoked.
    description:
        Human-readable description shown in MCP tool listings.
    parameters:
        List of :class:`CustomToolParam` definitions.
    returns:
        Description of the return value.
    """

    name: str
    matlab_function: str
    description: str = ""
    parameters: List[CustomToolParam] = Field(default_factory=list)
    returns: str = ""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_custom_tools(config_path: str) -> List[CustomToolDef]:
    """Load custom tool definitions from a YAML file.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.

    Returns
    -------
    list of CustomToolDef
        Parsed tool definitions, or an empty list if the file does not exist
        or contains no ``tools`` section.
    """
    path = Path(config_path)
    if not path.exists():
        logger.debug("Custom tools config not found: %s", path)
        return []

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("Failed to load custom tools from %s: %s", path, exc)
        return []

    raw_tools = data.get("tools", []) or []
    tools: List[CustomToolDef] = []
    for raw in raw_tools:
        try:
            tools.append(CustomToolDef.model_validate(raw))
        except Exception as exc:
            logger.warning("Invalid custom tool definition %r: %s", raw, exc)

    return tools


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------

def make_custom_tool_handler(
    tool_def: CustomToolDef,
    server_state: Any,
) -> Callable:
    """Create an async handler function for a custom tool.

    FastMCP introspects the function signature to determine parameter names and
    types. This factory builds a proper ``inspect.Signature`` with:
    - ``ctx: Context`` as the first parameter
    - One parameter per entry in ``tool_def.parameters``

    The returned function delegates to the executor stored in
    ``server_state.executor``, building a MATLAB function call from
    ``tool_def.matlab_function`` and the supplied arguments.

    Parameters
    ----------
    tool_def:
        The :class:`CustomToolDef` that describes this tool.
    server_state:
        An object with at minimum:
        - ``executor`` — a :class:`~matlab_mcp.jobs.executor.JobExecutor`
        - ``session_id`` — default session ID string

    Returns
    -------
    callable
        An async function with ``__name__``, ``__doc__``, and ``__signature__``
        properly set.
    """
    # Try to import Context from fastmcp; fall back to Any for tests without fastmcp
    try:
        from fastmcp import Context as _Context
    except ImportError:  # pragma: no cover
        _Context = Any  # type: ignore[misc,assignment]

    # Build the inspect.Parameter list
    params: List[inspect.Parameter] = [
        inspect.Parameter(
            "ctx",
            kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=_Context,
        )
    ]

    for p in tool_def.parameters:
        py_type = _TYPE_MAP.get(p.type.lower(), str)
        if p.required:
            params.append(
                inspect.Parameter(
                    p.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=py_type,
                )
            )
        else:
            params.append(
                inspect.Parameter(
                    p.name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=py_type,
                    default=p.default,
                )
            )

    sig = inspect.Signature(params, return_annotation=dict)

    # Build the actual handler
    # Capture tool_def and server_state in closure
    _tool_def = tool_def
    _server_state = server_state

    async def _handler(*args, **kwargs):
        # Bind arguments to the signature (skip ctx which is first positional)
        # args[0] is ctx
        # remaining args / kwargs are tool params
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        # Remove ctx
        arguments.pop("ctx", None)

        # Build MATLAB function call: func(arg1, arg2, ...)
        matlab_args = []
        for param in _tool_def.parameters:
            val = arguments.get(param.name)
            py_type = _TYPE_MAP.get(param.type.lower(), str)
            if py_type in (str,):
                matlab_args.append(f"'{val}'")
            elif py_type in (int, float):
                matlab_args.append(str(val))
            elif py_type is bool:
                matlab_args.append("true" if val else "false")
            else:
                matlab_args.append(str(val))

        matlab_call = f"{_tool_def.matlab_function}({', '.join(matlab_args)})"

        session_id = getattr(_server_state, "session_id", "default")
        executor = _server_state.executor

        return await executor.execute(session_id=session_id, code=matlab_call)

    # Set metadata so FastMCP can use it
    _handler.__name__ = tool_def.name
    _handler.__doc__ = tool_def.description or f"Custom tool: {tool_def.name}"
    _handler.__signature__ = sig

    return _handler
