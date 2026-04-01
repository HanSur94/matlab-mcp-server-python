"""Bearer token authentication middleware for MATLAB MCP Server.

Provides BearerAuthMiddleware — a pure ASGI class (not BaseHTTPMiddleware) that
validates Authorization: Bearer <token> headers on every HTTP request.

The token is read exclusively from the MATLAB_MCP_AUTH_TOKEN environment variable
at middleware initialization. When no token is configured, all requests pass through
(auth disabled). The /health path and OPTIONS requests always bypass authentication.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any, MutableMapping

logger = logging.getLogger(__name__)

# Type aliases matching starlette.types
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

# Paths that bypass authentication — health checks need no token for load balancers
_BYPASS_PATHS: frozenset[str] = frozenset({"/health"})


class BearerAuthMiddleware:
    """Pure-ASGI bearer token authentication middleware.

    Validates Authorization: Bearer <token> header on every HTTP request,
    except paths in _BYPASS_PATHS and OPTIONS requests. Non-HTTP scopes
    (WebSocket, lifespan) pass through unconditionally.

    Token is read from MATLAB_MCP_AUTH_TOKEN env var at init time. When the
    env var is not set, authentication is disabled and all requests pass through.

    Uses hmac.compare_digest for constant-time token comparison to prevent
    timing oracle attacks.

    Parameters
    ----------
    app : ASGIApp
        The downstream ASGI application to wrap.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._token: str | None = os.environ.get("MATLAB_MCP_AUTH_TOKEN")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process ASGI request, enforcing bearer token auth for HTTP requests."""
        # Only apply auth checks to HTTP requests
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Bypass auth for health check endpoint (load balancers need unauthenticated access)
        if path in _BYPASS_PATHS:
            await self._app(scope, receive, send)
            return

        # No token configured — auth disabled, pass all requests through
        if self._token is None:
            await self._app(scope, receive, send)
            return

        # Bypass auth for CORS pre-flight OPTIONS requests (sent without credentials)
        if scope.get("method") == "OPTIONS":
            await self._app(scope, receive, send)
            return

        # Extract Authorization header (headers are list of (bytes, bytes) tuples)
        headers = dict(scope.get("headers", []))
        auth_header: bytes = headers.get(b"authorization", b"")

        # Parse Bearer token (case-insensitive prefix check)
        provided_token = ""
        if auth_header.lower().startswith(b"bearer "):
            provided_token = auth_header[7:].decode("utf-8", errors="replace")

        # Constant-time comparison to prevent timing oracle attacks
        if hmac.compare_digest(provided_token, self._token):
            await self._app(scope, receive, send)
            return

        # Reject with 401 — include WWW-Authenticate and JSON body per RFC 6750
        await self._send_401(send)

    async def _send_401(self, send: Send) -> None:
        """Send a 401 Unauthorized response with JSON body and Bearer challenge."""
        body = json.dumps({
            "error": "unauthorized",
            "message": "Valid Bearer token required",
        }).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
