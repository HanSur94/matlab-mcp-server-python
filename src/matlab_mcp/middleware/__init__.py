"""Middleware package for the MATLAB MCP Server.

Exposes FastMCP middleware components used by ``create_server``.
"""
from __future__ import annotations

from matlab_mcp.middleware.timing import TimingMiddleware

__all__ = ["TimingMiddleware"]
