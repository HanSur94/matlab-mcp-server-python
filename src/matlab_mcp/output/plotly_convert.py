"""Plotly JSON loader for MATLAB MCP Server.

Provides ``load_plotly_json`` which reads a Plotly-compatible JSON file
written by the MATLAB helper ``mcp_fig2plotly.m``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_plotly_json(json_path: str) -> Optional[dict]:
    """Load a Plotly JSON file produced by ``mcp_fig2plotly``.

    Parameters
    ----------
    json_path:
        Path to the JSON file to load.

    Returns
    -------
    Optional[dict]
        Parsed Plotly figure dict, or ``None`` if the file does not exist or
        cannot be parsed.
    """
    path = Path(json_path)
    if not path.exists():
        logger.debug("Plotly JSON file not found: %s", json_path)
        return None

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            logger.warning("Plotly JSON at %s is not a dict: %r", json_path, type(data))
            return None
        return data
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Plotly JSON from %s: %s", json_path, exc)
        return None
    except Exception as exc:
        logger.warning("Failed to load Plotly JSON from %s: %s", json_path, exc)
        return None
