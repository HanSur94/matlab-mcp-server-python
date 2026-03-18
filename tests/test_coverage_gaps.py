"""Targeted tests for remaining coverage gaps across modules.

Covers:
- tools/core.py: check_code JSON parsing, non-completed result, cleanup exception
- session/manager.py: config=None defaults, destroy temp dir cleanup failure
- monitoring/health.py: degraded health check failure counter
- pool/engine.py: is_alive property, stop exception, addpath exception
- pool/manager.py: scale up with collector
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch


from matlab_mcp.config import AppConfig, ExecutionConfig, PoolConfig, SecurityConfig, WorkspaceConfig
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper
from matlab_mcp.security.validator import SecurityValidator
from tests.mocks.matlab_engine_mock import MockMatlabEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pool():
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


def _make_executor(sync_timeout=5):
    pool, wrapper, inner = _make_mock_pool()
    tracker = JobTracker()
    config = AppConfig()
    config.execution = ExecutionConfig(sync_timeout=sync_timeout)
    executor = JobExecutor(pool=pool, tracker=tracker, config=config)
    return executor, tracker


def _make_security(enabled=True, blocked=None):
    if blocked is None:
        blocked = ["system", "unix", "dos", "!"]
    cfg = SecurityConfig(
        blocked_functions_enabled=enabled,
        blocked_functions=blocked,
    )
    return SecurityValidator(cfg)


# ---------------------------------------------------------------------------
# tools/core.py — check_code_impl branches
# ---------------------------------------------------------------------------


class TestCheckCodeImplBranches:
    async def test_check_code_valid_json_output(self, tmp_path):
        """When executor returns valid JSON, check_code should parse it."""
        from matlab_mcp.tools.core import check_code_impl

        class JsonExecutor:
            async def execute(self, session_id, code, temp_dir=None):
                return {
                    "status": "completed",
                    "job_id": "j-1",
                    "text": json.dumps([{"line": 1, "message": "unused var"}]),
                }

        result = await check_code_impl(
            code="x = 1;",
            session_id="s1",
            executor=JsonExecutor(),
            temp_dir=str(tmp_path),
        )
        assert result["status"] == "completed"
        assert isinstance(result["issues"], list)
        assert len(result["issues"]) == 1

    async def test_check_code_non_completed_status(self, tmp_path):
        """When executor returns non-completed status, return as-is."""
        from matlab_mcp.tools.core import check_code_impl

        class FailExecutor:
            async def execute(self, session_id, code, temp_dir=None):
                return {
                    "status": "failed",
                    "job_id": "j-1",
                    "error": {"type": "MatlabError", "message": "crash"},
                }

        result = await check_code_impl(
            code="x = 1;",
            session_id="s1",
            executor=FailExecutor(),
            temp_dir=str(tmp_path),
        )
        assert result["status"] == "failed"

    async def test_check_code_temp_file_cleanup_exception(self, tmp_path):
        """If temp file cleanup fails, check_code should still return result."""
        from matlab_mcp.tools.core import check_code_impl

        executor, _ = _make_executor()

        # Make a read-only dir so unlink might fail on some systems
        # Use patching instead for reliability
        with patch("pathlib.Path.unlink", side_effect=PermissionError("read-only")):
            result = await check_code_impl(
                code="x = 1;",
                session_id="s1",
                executor=executor,
                temp_dir=str(tmp_path),
            )
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# session/manager.py — config=None defaults
# ---------------------------------------------------------------------------


class TestSessionManagerConfigNone:
    def test_creates_with_none_config(self):
        """SessionManager(None) should use default values."""
        from matlab_mcp.session.manager import SessionManager

        manager = SessionManager(None)
        assert manager._max_sessions == 50
        assert manager._session_timeout == 3600

    def test_destroy_session_with_rmtree_failure(self, tmp_path):
        """destroy_session should handle rmtree failure gracefully."""
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config

        manager = SessionManager(load_config(None))
        session = manager.create_session()
        sid = session.session_id

        with patch("shutil.rmtree", side_effect=OSError("permission denied")):
            result = manager.destroy_session(sid)
        assert result is True


# ---------------------------------------------------------------------------
# monitoring/health.py — degraded conditions
# ---------------------------------------------------------------------------


class TestHealthDegradedConditions:
    def test_health_check_failures_trigger_degraded(self):
        """Health check failures > 0 should trigger degraded status."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = MagicMock()
        collector.pool = MagicMock()
        collector.pool.get_status.return_value = {
            "total": 4, "available": 2, "busy": 2, "max": 8,
        }
        collector.tracker = MagicMock()
        collector.tracker.list_jobs.return_value = []
        collector.sessions = MagicMock()
        collector.sessions.session_count = 1
        collector.start_time = time.time() - 3600  # 1 hour uptime
        collector.get_counters.return_value = {
            "completed_total": 10,
            "failed_total": 0,
            "cancelled_total": 0,
            "total_created_sessions": 5,
            "error_total": 0,
            "blocked_attempts": 0,
            "health_check_failures": 3,  # This triggers degraded
        }

        result = evaluate_health(collector)
        assert result["status"] == "degraded"
        assert any("health check" in issue.lower() for issue in result["issues"])


# ---------------------------------------------------------------------------
# pool/engine.py — additional coverage
# ---------------------------------------------------------------------------


class TestEngineWrapperAdditional:
    def test_is_alive_callable_is_alive(self):
        """is_alive should call engine.is_alive() when it's callable."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig()
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)
        mock_engine = MockMatlabEngine()
        wrapper._engine = mock_engine
        wrapper._state = EngineState.IDLE

        # MockMatlabEngine.is_alive is a property that returns bool
        assert wrapper.is_alive is True

    def test_is_alive_no_engine(self):
        """is_alive should return False when engine is None."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig()
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)
        assert wrapper.is_alive is False

    def test_stop_with_quit_exception(self):
        """stop() should handle quit() exception gracefully."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig()
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)
        mock_engine = MagicMock()
        mock_engine.quit.side_effect = RuntimeError("quit failed")
        wrapper._engine = mock_engine
        wrapper._state = EngineState.IDLE

        wrapper.stop()
        assert wrapper._state == EngineState.STOPPED
        assert wrapper._engine is None

    def test_start_addpath_exception(self):
        """start() should handle addpath exception without crashing."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig(default_paths=["/some/path"])

        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)

        mock_module = MagicMock()
        mock_engine = MockMatlabEngine()
        # Make addpath raise for the first path
        mock_engine.addpath = MagicMock(side_effect=RuntimeError("path error"))
        mock_module.start_matlab.return_value = mock_engine
        wrapper._get_matlab_engine_module = lambda: mock_module

        wrapper.start()
        assert wrapper._state == EngineState.IDLE

    def test_start_startup_command_exception(self):
        """start() should handle startup command exception."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig(startup_commands=["cd /nonexistent"])

        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)

        mock_module = MagicMock()
        mock_engine = MockMatlabEngine()
        # eval will ignore unrecognized commands, so mock it to raise
        original_eval = mock_engine.eval
        def raising_eval(code, **kwargs):
            if code == "cd /nonexistent":
                raise RuntimeError("command failed")
            return original_eval(code, **kwargs)
        mock_engine.eval = raising_eval
        mock_module.start_matlab.return_value = mock_engine
        wrapper._get_matlab_engine_module = lambda: mock_module

        wrapper.start()
        assert wrapper._state == EngineState.IDLE

    def test_reset_workspace_restoredefaultpath_exception(self):
        """reset_workspace should handle restoredefaultpath exception."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig()
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)

        mock_engine = MockMatlabEngine()
        mock_engine.restoredefaultpath = MagicMock(side_effect=RuntimeError("restore failed"))
        wrapper._engine = mock_engine
        wrapper._state = EngineState.IDLE

        wrapper.reset_workspace()  # should not raise

    def test_reset_workspace_readdpath_exception(self):
        """reset_workspace should handle re-addpath exception."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig(default_paths=["/bad/path"])
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)

        mock_engine = MockMatlabEngine()
        mock_engine.addpath = MagicMock(side_effect=RuntimeError("addpath failed"))
        wrapper._engine = mock_engine
        wrapper._state = EngineState.IDLE

        wrapper.reset_workspace()  # should not raise

    def test_reset_workspace_startup_command_exception(self):
        """reset_workspace should handle startup command exception."""
        pool_cfg = PoolConfig(min_engines=1, max_engines=2)
        workspace_cfg = WorkspaceConfig(startup_commands=["bad_cmd"])
        wrapper = MatlabEngineWrapper("e-test", pool_cfg, workspace_cfg)

        mock_engine = MockMatlabEngine()
        original_eval = mock_engine.eval
        def raising_eval(code, **kwargs):
            if code == "bad_cmd":
                raise RuntimeError("bad command")
            return original_eval(code, **kwargs)
        mock_engine.eval = raising_eval
        wrapper._engine = mock_engine
        wrapper._state = EngineState.IDLE

        wrapper.reset_workspace()  # should not raise
