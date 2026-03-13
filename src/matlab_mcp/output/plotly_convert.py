"""Figure property JSON loader for MATLAB MCP Server.

Provides ``load_plotly_json`` which reads a JSON file written by the
MATLAB helper ``mcp_extract_props.m``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SUPPORTED_SCHEMA_VERSION = 1


def load_plotly_json(json_path: str) -> Optional[dict]:
    """Load a figure property JSON file produced by ``mcp_extract_props``.

    Parameters
    ----------
    json_path:
        Path to the JSON file to load.

    Returns
    -------
    Optional[dict]
        Parsed figure dict, or ``None`` if the file does not exist,
        cannot be parsed, or has an unsupported schema_version.
    """
    path = Path(json_path)
    if not path.exists():
        logger.debug("Figure JSON file not found: %s", json_path)
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            logger.warning("Figure JSON at %s is not a dict: %r", json_path, type(data))
            return None
        version = data.get("schema_version")
        if version is None:
            logger.warning("Figure JSON at %s missing schema_version", json_path)
            return None
        if version > SUPPORTED_SCHEMA_VERSION:
            logger.warning(
                "Figure JSON at %s has unsupported schema_version %s (max %s)",
                json_path, version, SUPPORTED_SCHEMA_VERSION,
            )
            return None
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse figure JSON from %s: %s", json_path, exc)
        return None
    except Exception as exc:
        logger.warning("Failed to load figure JSON from %s: %s", json_path, exc)
        return None
