"""TimingMiddleware: per-tool-call duration and success/failure metrics.

Records a ``"tool_call"`` event (distinct from the executor's
``job_completed``/``job_failed`` events) into the server's ``MetricsCollector``
for every FastMCP tool invocation. This is the incremental first step of
migrating imperative timing to the middleware layer (CONTEXT.md §7); the
executor's own job-level timing is left in place this pass.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

logger = logging.getLogger(__name__)

_EVENT_TYPE = "tool_call"


class TimingMiddleware(Middleware):
    """FastMCP middleware that times tool calls and records them via a collector.

    Parameters
    ----------
    collector:
        A ``MetricsCollector``-like object exposing
        ``record_event(event_type: str, details: dict) -> None``. May be
        ``None``, in which case timing is measured but never recorded
        (no-op), so the middleware is safe to register even when
        monitoring is disabled.
    """

    def __init__(self, collector: Optional[Any]) -> None:
        """Initialize the middleware with a (possibly ``None``) collector."""
        self._collector = collector

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Any,
    ) -> ToolResult:
        """Time a tool call and record its duration and success/failure.

        Awaits ``call_next(context)`` and, on success, records a
        ``"tool_call"`` event with the tool name, elapsed duration in
        milliseconds, and ``success=True``. On exception, records the same
        event with ``success=False`` and re-raises — the original exception
        always propagates unchanged.
        """
        tool_name = self._extract_tool_name(context)
        start = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            self._record(tool_name, duration_ms, success=False)
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        self._record(tool_name, duration_ms, success=True)
        return result

    def _record(self, tool_name: str, duration_ms: float, *, success: bool) -> None:
        """Record a ``tool_call`` event via the collector, tolerating a None collector."""
        if self._collector is None:
            return
        try:
            self._collector.record_event(
                _EVENT_TYPE,
                {
                    "tool": tool_name,
                    "duration_ms": duration_ms,
                    "success": success,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive, must never mask tool result
            logger.warning("TimingMiddleware failed to record event: %s", exc)

    @staticmethod
    def _extract_tool_name(context: MiddlewareContext[Any]) -> str:
        """Resolve the tool name from the middleware context, tolerating shape differences.

        The tool name lives at ``context.message.name`` for
        ``CallToolRequestParams`` across FastMCP 3.x. Falls back to
        ``"unknown"`` if the expected attribute is absent.
        """
        message = getattr(context, "message", None)
        name = getattr(message, "name", None)
        return name if isinstance(name, str) else "unknown"
