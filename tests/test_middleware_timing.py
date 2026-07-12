"""Tests for TimingMiddleware (F5: per-tool-call timing metrics)."""
from __future__ import annotations

import pytest
import mcp.types as mt
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools.tool import ToolResult

from matlab_mcp.middleware.timing import TimingMiddleware


class _FakeCollector:
    """Captures (event_type, details) tuples passed to record_event."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record_event(self, event_type: str, details: dict) -> None:
        self.events.append((event_type, details))


def _make_context(tool_name: str = "execute_code") -> MiddlewareContext:
    """Build a MiddlewareContext wrapping a CallToolRequestParams for *tool_name*."""
    return MiddlewareContext(
        message=mt.CallToolRequestParams(name=tool_name, arguments={})
    )


class TestTimingMiddlewareSuccess:
    async def test_records_tool_call_event_with_duration_and_success(self):
        collector = _FakeCollector()
        middleware = TimingMiddleware(collector)
        context = _make_context("execute_code")
        expected_result = ToolResult(content=[])

        async def call_next(ctx):
            return expected_result

        result = await middleware.on_call_tool(context, call_next)

        assert result is expected_result
        assert len(collector.events) == 1
        event_type, details = collector.events[0]
        assert event_type == "tool_call"
        assert details["tool"] == "execute_code"
        assert isinstance(details["duration_ms"], float)
        assert details["duration_ms"] >= 0.0
        assert details["success"] is True

    async def test_never_emits_job_completed_or_job_failed(self):
        collector = _FakeCollector()
        middleware = TimingMiddleware(collector)
        context = _make_context("check_code")

        async def call_next(ctx):
            return ToolResult(content=[])

        await middleware.on_call_tool(context, call_next)

        emitted_types = {event_type for event_type, _ in collector.events}
        assert "job_completed" not in emitted_types
        assert "job_failed" not in emitted_types


class TestTimingMiddlewareFailure:
    async def test_records_failure_event_and_reraises(self):
        collector = _FakeCollector()
        middleware = TimingMiddleware(collector)
        context = _make_context("execute_code")

        async def call_next(ctx):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await middleware.on_call_tool(context, call_next)

        assert len(collector.events) == 1
        event_type, details = collector.events[0]
        assert event_type == "tool_call"
        assert details["success"] is False
        assert isinstance(details["duration_ms"], float)
        assert details["duration_ms"] >= 0.0

    async def test_failure_never_emits_job_completed_or_job_failed(self):
        collector = _FakeCollector()
        middleware = TimingMiddleware(collector)
        context = _make_context("execute_code")

        async def call_next(ctx):
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError):
            await middleware.on_call_tool(context, call_next)

        emitted_types = {event_type for event_type, _ in collector.events}
        assert "job_completed" not in emitted_types
        assert "job_failed" not in emitted_types


class TestTimingMiddlewareNoCollector:
    async def test_none_collector_is_a_no_op(self):
        middleware = TimingMiddleware(None)
        context = _make_context("execute_code")
        expected_result = ToolResult(content=[])

        async def call_next(ctx):
            return expected_result

        result = await middleware.on_call_tool(context, call_next)

        assert result is expected_result

    async def test_none_collector_does_not_crash_on_failure_path(self):
        middleware = TimingMiddleware(None)
        context = _make_context("execute_code")

        async def call_next(ctx):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await middleware.on_call_tool(context, call_next)
