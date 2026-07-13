"""Wire-compat + output-schema + error-path tests for F6 structured output.

Verifies that ``ExecuteResult``/``CheckResult`` (schema-additive Pydantic
models) round-trip the exact pre-change dict keys produced by
``execute_code_impl``/``check_code_impl`` and the ``JobExecutor``, and that
the ``execute_code``/``check_code`` tool wrappers emit an output schema while
preserving the legacy wire shape.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Mock matlab.engine before any production import touches it (server.py
# imports pool/engine modules transitively at collection time).
# ---------------------------------------------------------------------------
_matlab_pkg = types.ModuleType("matlab")
_engine_mod = types.ModuleType("matlab.engine")

from tests.mocks.matlab_engine_mock import (  # noqa: E402
    MatlabExecutionError,
    start_matlab as _mock_start_matlab,
)

_engine_mod.start_matlab = _mock_start_matlab
_engine_mod.MatlabExecutionError = MatlabExecutionError
_matlab_pkg.engine = _engine_mod

sys.modules.setdefault("matlab", _matlab_pkg)
sys.modules.setdefault("matlab.engine", _engine_mod)

from matlab_mcp.config import (  # noqa: E402
    AppConfig,
    ExecutionConfig,
    MonitoringConfig,
    ServerConfig,
    SessionsConfig,
)
from matlab_mcp.tools.core import CheckResult, ExecuteResult  # noqa: E402


@pytest.fixture
def stdio_config(tmp_path: Path) -> AppConfig:
    """A minimal stdio AppConfig rooted in tmp_path, monitoring disabled."""
    return AppConfig(
        server=ServerConfig(
            transport="stdio",
            log_file=str(tmp_path / "logs" / "server.log"),
            result_dir=str(tmp_path / "results"),
        ),
        execution=ExecutionConfig(temp_dir=str(tmp_path / "temp")),
        sessions=SessionsConfig(max_sessions=10, session_timeout=3600),
        monitoring=MonitoringConfig(
            enabled=False,
            db_path=str(tmp_path / "monitoring" / "metrics.db"),
        ),
    )

# ---------------------------------------------------------------------------
# Representative fixtures — the exact dict shapes produced today by
# JobExecutor / execute_code_impl / check_code_impl for each code path.
# ---------------------------------------------------------------------------

_COMPLETED = {
    "status": "completed",
    "job_id": "j-abc123",
    "text": "ans = 42\n",
    "variables": {"x": 42},
    "figures": [],
    "files": [],
    "warnings": [],
    "errors": [],
}

_PENDING = {
    "status": "pending",
    "job_id": "j-def456",
}

_FAILED_POST_JOB = {
    "status": "failed",
    "job_id": "j-ghi789",
    "error": {
        "type": "MatlabExecutionError",
        "message": "Undefined function 'foo'.",
        "matlab_id": "MATLAB:undefinedFunction",
        "stack_trace": None,
    },
}

_FAILED_PRE_JOB = {
    "status": "failed",
    "error": {
        "type": "ValidationError",
        "message": "Blocked: system",
        "matlab_id": None,
        "stack_trace": None,
    },
}

_DENIED = {
    "status": "denied",
    "message": "Operation blocked by HITL approval",
}

_CHECK_COMPLETED_ISSUES = {
    "status": "completed",
    "issues": [{"line": 3, "column": 1, "message": "unused variable", "severity": "warning"}],
}

_CHECK_COMPLETED_RAW_FALLBACK = {
    "status": "completed",
    "issues": [],
    "raw": "not valid json",
}

_CHECK_PENDING = {
    "status": "pending",
    "job_id": "j-check-1",
}

_CHECK_FAILED = {
    "status": "failed",
    "job_id": "j-check-2",
    "error": {
        "type": "MatlabExecutionError",
        "message": "boom",
        "matlab_id": None,
        "stack_trace": None,
    },
}


class TestExecuteResultWireCompat:
    """ExecuteResult must reproduce the exact legacy dict keys/values."""

    def test_completed_round_trips_exact_keys(self):
        model = ExecuteResult(**_COMPLETED)
        assert model.to_wire_dict() == _COMPLETED

    def test_pending_round_trips_exact_keys(self):
        model = ExecuteResult(**_PENDING)
        assert model.to_wire_dict() == _PENDING

    def test_failed_post_job_preserves_nested_error_keys(self):
        """Nested error dict keeps its None-valued keys (matlab_id/stack_trace)."""
        model = ExecuteResult(**_FAILED_POST_JOB)
        wire = model.to_wire_dict()
        assert wire == _FAILED_POST_JOB
        assert set(wire["error"].keys()) == {"type", "message", "matlab_id", "stack_trace"}
        assert wire["error"]["matlab_id"] == "MATLAB:undefinedFunction"
        assert wire["error"]["stack_trace"] is None

    def test_failed_pre_job_has_no_job_id_key(self):
        """No job_id key present when security rejects before job creation."""
        model = ExecuteResult(**_FAILED_PRE_JOB)
        wire = model.to_wire_dict()
        assert wire == _FAILED_PRE_JOB
        assert "job_id" not in wire
        assert wire["error"]["matlab_id"] is None
        assert wire["error"]["stack_trace"] is None

    def test_denied_round_trips_exact_keys(self):
        model = ExecuteResult(**_DENIED)
        assert model.to_wire_dict() == _DENIED

    def test_no_unexpected_keys_added(self):
        """Only the keys present in the source dict appear on the wire."""
        for fixture in (_COMPLETED, _PENDING, _FAILED_POST_JOB, _FAILED_PRE_JOB, _DENIED):
            wire = ExecuteResult(**fixture).to_wire_dict()
            assert set(wire.keys()) == set(fixture.keys())


class TestCheckResultWireCompat:
    """CheckResult must reproduce the exact legacy dict keys/values."""

    def test_completed_with_issues_round_trips(self):
        model = CheckResult(**_CHECK_COMPLETED_ISSUES)
        assert model.to_wire_dict() == _CHECK_COMPLETED_ISSUES

    def test_completed_raw_fallback_round_trips(self):
        model = CheckResult(**_CHECK_COMPLETED_RAW_FALLBACK)
        assert model.to_wire_dict() == _CHECK_COMPLETED_RAW_FALLBACK

    def test_pending_passthrough_round_trips(self):
        model = CheckResult(**_CHECK_PENDING)
        assert model.to_wire_dict() == _CHECK_PENDING

    def test_failed_passthrough_round_trips(self):
        model = CheckResult(**_CHECK_FAILED)
        wire = model.to_wire_dict()
        assert wire == _CHECK_FAILED
        assert wire["error"]["matlab_id"] is None

    def test_no_unexpected_keys_added(self):
        for fixture in (
            _CHECK_COMPLETED_ISSUES,
            _CHECK_COMPLETED_RAW_FALLBACK,
            _CHECK_PENDING,
            _CHECK_FAILED,
        ):
            wire = CheckResult(**fixture).to_wire_dict()
            assert set(wire.keys()) == set(fixture.keys())


class TestOutputSchemaEmission:
    """execute_code/check_code wrappers emit an output schema (Task 2)."""

    async def _get_tool(self, mcp, name: str):
        tools = await mcp.list_tools()
        return next(t for t in tools if t.name == name)

    async def test_execute_code_emits_output_schema(self, stdio_config):
        from matlab_mcp.server import create_server

        mcp = create_server(stdio_config)
        tool = await self._get_tool(mcp, "execute_code")
        assert tool.output_schema is not None

    async def test_check_code_emits_output_schema(self, stdio_config):
        from matlab_mcp.server import create_server

        mcp = create_server(stdio_config)
        tool = await self._get_tool(mcp, "check_code")
        assert tool.output_schema is not None


class TestToolResultErrorPath:
    """MATLAB execution errors surface as ToolResult(is_error=True) (Task 2).

    Calls the tool's raw ``fn`` directly (bypassing FastMCP's context
    dependency-injection machinery, which requires a live request context)
    with a stubbed ``ctx`` — mirroring how ``tests/test_tools.py`` calls
    ``execute_code_impl`` directly.
    """

    async def test_execute_code_error_returns_tool_result_is_error(self, stdio_config):
        from unittest.mock import AsyncMock, MagicMock

        from fastmcp.tools.tool import ToolResult

        import matlab_mcp.server as server_mod
        from matlab_mcp.server import create_server

        mcp = create_server(stdio_config)
        tool = await mcp.get_tool("execute_code")

        async def fake_impl(*args, **kwargs):
            return dict(_FAILED_POST_JOB)

        original = server_mod.execute_code_impl
        server_mod.execute_code_impl = AsyncMock(side_effect=fake_impl)
        try:
            result = await tool.fn(ctx=MagicMock(), code="error('boom')")
        finally:
            server_mod.execute_code_impl = original

        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert result.structured_content is not None
        assert result.structured_content["status"] == "failed"
        assert result.structured_content["error"]["matlab_id"] == "MATLAB:undefinedFunction"

    async def test_execute_code_success_returns_plain_dict_keys(self, stdio_config):
        """Completed executions still serialize to the exact legacy dict keys."""
        from unittest.mock import AsyncMock, MagicMock

        import matlab_mcp.server as server_mod
        from matlab_mcp.server import create_server

        mcp = create_server(stdio_config)
        tool = await mcp.get_tool("execute_code")

        async def fake_impl(*args, **kwargs):
            return dict(_COMPLETED)

        original = server_mod.execute_code_impl
        server_mod.execute_code_impl = AsyncMock(side_effect=fake_impl)
        try:
            result = await tool.fn(ctx=MagicMock(), code="x = 42;")
        finally:
            server_mod.execute_code_impl = original

        # Wrapper may return a plain dict or a model with the same wire keys.
        wire = result if isinstance(result, dict) else result.to_wire_dict()
        assert wire == _COMPLETED

    async def test_check_code_error_returns_tool_result_is_error(self, stdio_config):
        from unittest.mock import AsyncMock, MagicMock

        from fastmcp.tools.tool import ToolResult

        import matlab_mcp.server as server_mod
        from matlab_mcp.server import create_server

        mcp = create_server(stdio_config)
        tool = await mcp.get_tool("check_code")

        async def fake_impl(*args, **kwargs):
            return dict(_CHECK_FAILED)

        original = server_mod.check_code_impl
        server_mod.check_code_impl = AsyncMock(side_effect=fake_impl)
        try:
            result = await tool.fn(ctx=MagicMock(), code="x = 1")
        finally:
            server_mod.check_code_impl = original

        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert result.structured_content["status"] == "failed"
