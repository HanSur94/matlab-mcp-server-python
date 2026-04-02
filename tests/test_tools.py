"""Tests for core MCP tool implementations."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from matlab_mcp.config import AppConfig, ExecutionConfig, HITLConfig, SecurityConfig
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.security.validator import SecurityValidator


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_mock_pool():
    """Create a minimal mock engine pool using the MockMatlabEngine."""
    from tests.mocks.matlab_engine_mock import MockMatlabEngine
    from matlab_mcp.config import PoolConfig, WorkspaceConfig
    from matlab_mcp.pool.engine import MatlabEngineWrapper, EngineState

    mock_engine_inner = MockMatlabEngine()
    pool_cfg = PoolConfig(min_engines=1, max_engines=2)
    workspace_cfg = WorkspaceConfig()
    wrapper = MatlabEngineWrapper("engine-0", pool_cfg, workspace_cfg)
    wrapper._engine = mock_engine_inner
    wrapper._state = EngineState.IDLE

    class MockPool:
        async def acquire(self):
            wrapper.mark_busy()
            return wrapper

        async def release(self, engine):
            engine.mark_idle()

    return MockPool(), wrapper, mock_engine_inner


def _make_executor(sync_timeout: int = 5):
    """Create a real JobExecutor backed by the mock pool."""
    pool, wrapper, inner = _make_mock_pool()
    tracker = JobTracker()
    config = AppConfig()
    config.execution = ExecutionConfig(sync_timeout=sync_timeout)
    executor = JobExecutor(pool=pool, tracker=tracker, config=config)
    return executor, tracker


def _make_security(enabled: bool = True, blocked: list | None = None):
    """Create a SecurityValidator instance."""
    if blocked is None:
        blocked = ["system", "unix", "dos", "!"]
    cfg = SecurityConfig(
        blocked_functions_enabled=enabled,
        blocked_functions=blocked,
    )
    return SecurityValidator(cfg)


# ---------------------------------------------------------------------------
# Task 10: execute_code_impl
# ---------------------------------------------------------------------------

class TestExecuteCodeImpl:
    async def test_normal_code_succeeds(self, tmp_path):
        """Normal MATLAB code should execute and return completed status."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="x = 42;",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert result["status"] == "completed"
        assert "job_id" in result

    async def test_normal_code_job_tracked(self):
        """After successful execution, the job should be in the tracker."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="y = 99;",
            session_id="s1",
            executor=executor,
            security=security,
        )

        job = tracker.get_job(result["job_id"])
        assert job is not None

    async def test_blocked_system_call_returns_failed(self):
        """system() call should be blocked and return failed status."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="system('ls');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert result["status"] == "failed"

    async def test_blocked_code_contains_blocked_message(self):
        """Blocked code error message should contain 'Blocked'."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="system('ls');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert "Blocked" in result["error"]["message"]

    async def test_blocked_code_error_type_is_validation_error(self):
        """Error type for blocked code should be 'ValidationError'."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="unix('ls');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert result["error"]["type"] == "ValidationError"

    async def test_blocked_code_does_not_create_job(self):
        """Blocked code should not create any job in the tracker."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="system('rm -rf /');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        # No job_id in result (security was rejected before job creation)
        assert "job_id" not in result
        assert len(tracker.list_jobs("s1")) == 0

    async def test_security_disabled_allows_system(self):
        """With security disabled, system() should execute normally."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security(enabled=False)

        result = await execute_code_impl(
            code="system('ls');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        # Security disabled → the code goes to executor (mock handles it)
        assert result["status"] in ("completed", "pending", "failed")
        # Should NOT be a ValidationError
        if result["status"] == "failed":
            assert result.get("error", {}).get("type") != "ValidationError"

    async def test_shell_escape_blocked(self):
        """Shell escape ! should also be blocked."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="!ls -la",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert result["status"] == "failed"
        assert "Blocked" in result["error"]["message"]

    async def test_error_code_returns_failed_status(self):
        """MATLAB error() call should result in a failed job."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, tracker = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="error('something went wrong');",
            session_id="s1",
            executor=executor,
            security=security,
        )

        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Task 10: check_code_impl
# ---------------------------------------------------------------------------

class TestCheckCodeImpl:
    async def test_check_code_returns_dict(self, tmp_path):
        """check_code_impl should return a dict."""
        from matlab_mcp.tools.core import check_code_impl

        executor, _ = _make_executor()

        result = await check_code_impl(
            code="x = 1;",
            session_id="s1",
            executor=executor,
            temp_dir=str(tmp_path),
        )

        assert isinstance(result, dict)

    async def test_check_code_temp_file_cleaned_up(self, tmp_path):
        """Temp .m file should be removed after check_code_impl."""
        from matlab_mcp.tools.core import check_code_impl

        executor, _ = _make_executor()

        await check_code_impl(
            code="x = 1;",
            session_id="s1",
            executor=executor,
            temp_dir=str(tmp_path),
        )

        # The temp file should have been deleted
        m_files = list(tmp_path.glob("_check_*.m"))
        assert len(m_files) == 0


# ---------------------------------------------------------------------------
# Task 10: get_workspace_impl
# ---------------------------------------------------------------------------

class TestGetWorkspaceImpl:
    async def test_get_workspace_returns_dict(self):
        """get_workspace_impl should return a result dict."""
        from matlab_mcp.tools.core import get_workspace_impl

        executor, _ = _make_executor()

        result = await get_workspace_impl(
            session_id="s1",
            executor=executor,
        )

        assert isinstance(result, dict)
        assert "status" in result

    async def test_get_workspace_has_job_id(self):
        """get_workspace_impl result should contain a job_id."""
        from matlab_mcp.tools.core import get_workspace_impl

        executor, _ = _make_executor()

        result = await get_workspace_impl(
            session_id="s1",
            executor=executor,
        )

        assert "job_id" in result


# ---------------------------------------------------------------------------
# HITL integration tests for execute_code_impl
# ---------------------------------------------------------------------------


def _make_accepted_ctx(approved: bool) -> MagicMock:
    """Return a mock ctx whose elicit() returns an AcceptedElicitation."""
    from fastmcp.server.context import AcceptedElicitation
    from matlab_mcp.hitl.gate import HumanApproval

    accepted = MagicMock(spec=AcceptedElicitation)
    accepted.data = HumanApproval(approved=approved)
    ctx = MagicMock()
    ctx.elicit = AsyncMock(return_value=accepted)
    return ctx


def _make_declined_ctx() -> MagicMock:
    """Return a mock ctx whose elicit() returns a DeclinedElicitation."""
    from fastmcp.server.context import DeclinedElicitation

    declined = MagicMock(spec=DeclinedElicitation)
    ctx = MagicMock()
    ctx.elicit = AsyncMock(return_value=declined)
    return ctx


class TestExecuteCodeHITL:
    """Integration tests for HITL gate wired into execute_code_impl."""

    async def test_execute_code_hitl_disabled_no_prompt(self):
        """With HITL disabled (default), ctx.elicit is never called."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, _ = _make_executor()
        security = _make_security()
        ctx = MagicMock()
        ctx.elicit = AsyncMock()

        result = await execute_code_impl(
            code="x = 1;",
            session_id="s1",
            executor=executor,
            security=security,
            ctx=ctx,
            hitl_config=HITLConfig(),
        )

        ctx.elicit.assert_not_called()
        assert result["status"] == "completed"

    async def test_execute_code_hitl_protected_denied(self):
        """With a protected function in code, a declined elicitation blocks execution."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, _ = _make_executor()
        security = _make_security()
        ctx = _make_declined_ctx()

        result = await execute_code_impl(
            code="delete(x)",
            session_id="s1",
            executor=executor,
            security=security,
            ctx=ctx,
            hitl_config=HITLConfig(enabled=True, protected_functions=["delete"]),
        )

        assert result["status"] == "denied"
        ctx.elicit.assert_called_once()

    async def test_execute_code_hitl_protected_approved(self):
        """With a protected function in code, an approved elicitation allows execution."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, _ = _make_executor()
        security = _make_security()
        ctx = _make_accepted_ctx(approved=True)

        result = await execute_code_impl(
            code="delete(x)",
            session_id="s1",
            executor=executor,
            security=security,
            ctx=ctx,
            hitl_config=HITLConfig(enabled=True, protected_functions=["delete"]),
        )

        # Code passes HITL and is executed (mock executor returns completed)
        ctx.elicit.assert_called_once()
        assert result["status"] == "completed"

    async def test_execute_code_hitl_no_ctx_no_prompt(self):
        """With ctx=None, even enabled HITL is skipped and executor is called."""
        from matlab_mcp.tools.core import execute_code_impl

        executor, _ = _make_executor()
        security = _make_security()

        result = await execute_code_impl(
            code="delete(x)",
            session_id="s1",
            executor=executor,
            security=security,
            ctx=None,
            hitl_config=HITLConfig(enabled=True, protected_functions=["delete"]),
        )

        # No ctx means no HITL check — executor runs normally
        assert result["status"] == "completed"
