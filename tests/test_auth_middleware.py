"""Tests for BearerAuthMiddleware."""
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any
import pytest

from matlab_mcp.auth import BearerAuthMiddleware


# ---------------------------------------------------------------------------
# ASGI test helpers
# ---------------------------------------------------------------------------

def make_http_scope(
    path: str = "/api",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    """Build a minimal ASGI HTTP scope dict."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
    }


def make_websocket_scope(path: str = "/ws") -> dict[str, Any]:
    """Build a minimal ASGI WebSocket scope dict."""
    return {
        "type": "websocket",
        "path": path,
        "headers": [],
    }


async def dummy_receive() -> dict[str, Any]:
    """Minimal ASGI receive callable."""
    return {"type": "http.request", "body": b""}


class CapturedResponse:
    """Captures ASGI send() calls for inspection."""

    def __init__(self) -> None:
        self.status: int | None = None
        self.headers: dict[bytes, bytes] = {}
        self.body: bytes = b""
        self._messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self._messages.append(message)
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = dict(message.get("headers", []))
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")


async def dummy_app(scope: dict, receive: Any, send: Any) -> None:
    """Minimal downstream app that returns 200."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBearerAuthMiddleware:

    def test_valid_token_passes(self, monkeypatch):
        """Valid Bearer token passes through to downstream app."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope(headers=[(b"authorization", b"Bearer abc123")])
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 200

    def test_missing_auth_header_returns_401(self, monkeypatch):
        """Missing Authorization header returns 401."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope()
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401

    def test_invalid_token_returns_401(self, monkeypatch):
        """Wrong token returns 401."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "correcttoken")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope(headers=[(b"authorization", b"Bearer wrongtoken")])
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401

    def test_malformed_bearer_header_returns_401(self, monkeypatch):
        """Basic auth instead of Bearer returns 401."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope(headers=[(b"authorization", b"Basic xyz")])
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401

    def test_health_bypass(self, monkeypatch):
        """Requests to /health bypass auth even when token is configured."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope(path="/health")
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 200

    def test_options_bypass_auth(self, monkeypatch):
        """OPTIONS requests bypass auth for CORS pre-flight support."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope(method="OPTIONS")
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 200

    def test_no_token_configured_passes_all(self, monkeypatch):
        """When no MATLAB_MCP_AUTH_TOKEN is set, all requests pass through."""
        monkeypatch.delenv("MATLAB_MCP_AUTH_TOKEN", raising=False)
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope()
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 200

    def test_token_from_env_var(self, monkeypatch):
        """Token is read from env var at __init__ time, not module level."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "envtoken42")
        middleware = BearerAuthMiddleware(dummy_app)
        assert middleware._token == "envtoken42"

    def test_non_http_scope_passes_through(self, monkeypatch):
        """Non-HTTP scopes (e.g. websocket) pass through without auth check."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_websocket_scope()

        received_scope = None

        async def recording_app(s, r, send):
            nonlocal received_scope
            received_scope = s

        middleware_recording = BearerAuthMiddleware(recording_app)
        import asyncio
        asyncio.run(middleware_recording(scope, dummy_receive, dummy_app))
        # WebSocket scope passed through — no auth check means recording_app was called
        assert received_scope == scope

    def test_401_body_is_json(self, monkeypatch):
        """401 response body is valid JSON with error and message fields."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope()
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401
        body = json.loads(captured.body.decode())
        assert "error" in body
        assert "message" in body
        assert body["error"] == "unauthorized"

    def test_401_has_www_authenticate_header(self, monkeypatch):
        """401 response includes WWW-Authenticate: Bearer header."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope()
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401
        assert b"www-authenticate" in captured.headers
        assert captured.headers[b"www-authenticate"] == b"Bearer"

    def test_401_has_content_type_json(self, monkeypatch):
        """401 response has Content-Type: application/json."""
        monkeypatch.setenv("MATLAB_MCP_AUTH_TOKEN", "abc123")
        middleware = BearerAuthMiddleware(dummy_app)
        scope = make_http_scope()
        captured = CapturedResponse()
        import asyncio
        asyncio.run(middleware(scope, dummy_receive, captured))
        assert captured.status == 401
        assert b"content-type" in captured.headers
        assert b"application/json" in captured.headers[b"content-type"]

    def test_constant_time_comparison(self, monkeypatch):
        """Middleware uses hmac.compare_digest for constant-time comparison."""
        import matlab_mcp.auth.middleware as mod
        assert hasattr(mod, "hmac"), "hmac module must be imported in middleware"
        import inspect
        src = inspect.getsource(mod.BearerAuthMiddleware)
        assert "hmac.compare_digest" in src

    def test_no_basehttpmiddleware(self):
        """BearerAuthMiddleware must NOT inherit from BaseHTTPMiddleware."""
        try:
            from starlette.middleware.base import BaseHTTPMiddleware
            assert not issubclass(BearerAuthMiddleware, BaseHTTPMiddleware)
        except ImportError:
            pass  # starlette not installed — skip check
