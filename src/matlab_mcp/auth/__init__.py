"""Auth package for MATLAB MCP Server.

Provides BearerAuthMiddleware for HTTP transport authentication.
"""
from __future__ import annotations

from matlab_mcp.auth.middleware import BearerAuthMiddleware

__all__ = ["BearerAuthMiddleware"]
