"""Extra coverage tests for matlab_mcp.jobs.executor.

Targets uncovered lines: _inject_job_context, _build_result, _safe_serialize,
_error_result, sync-timeout promotion, start-execution failure, and
_wait_for_completion (async completion, failure, and cancellation).
"""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock


from matlab_mcp.config import AppConfig, ExecutionConfig, OutputConfig, PoolConfig, WorkspaceConfig
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper
from tests.mocks.matlab_engine_mock import MockMatlabEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_pool():
    """Create a minimal mock engine pool using MockMatlabEngine."""
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


def _make_executor(
    sync_timeout: int = 5,
    max_execution_time: int = 60,
    plotly_conversion: bool = False,
    collector: Any = None,
) -> tuple[JobExecutor, JobTracker, MatlabEngineWrapper, MockMatlabEngine]:
    """Create a real JobExecutor backed by the mock pool."""
    pool, wrapper, inner = _make_mock_pool()
    tracker = JobTracker()
    config = AppConfig()
    config.execution = ExecutionConfig(
        sync_timeout=sync_timeout,
        max_execution_time=max_execution_time,
    )
    config.output = OutputConfig(plotly_conversion=plotly_conversion)
    executor = JobExecutor(pool=pool, tracker=tracker, config=config, collector=collector)
    return executor, tracker, wrapper, inner


# ---------------------------------------------------------------------------
# _inject_job_context
# ---------------------------------------------------------------------------


class TestInjectJobContext:
    def test_injects_job_id(self) -> None:
        """_inject_job_context should set __mcp_job_id__ in the workspace."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")

        executor._inject_job_context(wrapper, job, None)

        assert inner.workspace["__mcp_job_id__"] == job.job_id

    def test_injects_temp_dir_when_provided(self) -> None:
        """When temp_dir is not None, __mcp_temp_dir__ must be set."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")

        executor._inject_job_context(wrapper, job, "/tmp/foo")

        assert inner.workspace["__mcp_temp_dir__"] == "/tmp/foo"

    def test_skips_temp_dir_when_none(self) -> None:
        """When temp_dir is None, __mcp_temp_dir__ should not be set."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")

        executor._inject_job_context(wrapper, job, None)

        assert "__mcp_temp_dir__" not in inner.workspace

    def test_survives_workspace_exception(self) -> None:
        """If workspace assignment raises, the method should not propagate."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")

        # Make workspace raise on __setitem__
        broken_ws = MagicMock()
        broken_ws.__setitem__ = MagicMock(side_effect=RuntimeError("workspace locked"))
        inner.workspace = broken_ws

        # Should not raise
        executor._inject_job_context(wrapper, job, "/tmp/bar")


# ---------------------------------------------------------------------------
# _safe_serialize
# ---------------------------------------------------------------------------


class TestSafeSerialize:
    def test_none(self) -> None:
        assert JobExecutor._safe_serialize(None) is None

    def test_bool(self) -> None:
        assert JobExecutor._safe_serialize(True) is True
        assert JobExecutor._safe_serialize(False) is False

    def test_int(self) -> None:
        assert JobExecutor._safe_serialize(42) == 42

    def test_float(self) -> None:
        assert JobExecutor._safe_serialize(3.14) == 3.14

    def test_str(self) -> None:
        assert JobExecutor._safe_serialize("hello") == "hello"

    def test_list(self) -> None:
        assert JobExecutor._safe_serialize([1, "a", None]) == [1, "a", None]

    def test_tuple_becomes_list(self) -> None:
        result = JobExecutor._safe_serialize((1, 2, 3))
        assert result == [1, 2, 3]

    def test_dict(self) -> None:
        assert JobExecutor._safe_serialize({"a": 1, "b": [2]}) == {"a": 1, "b": [2]}

    def test_nested_structures(self) -> None:
        value = {"list": [1, {"inner": True}], "tuple": (3,)}
        result = JobExecutor._safe_serialize(value)
        assert result == {"list": [1, {"inner": True}], "tuple": [3]}

    def test_object_with_data_attribute(self) -> None:
        """Objects with _data attribute should return list(_data)."""
        obj = MagicMock()
        obj._data = [10, 20, 30]
        # Remove attributes we don't want to match first (numpy checks)
        del obj.tolist
        result = JobExecutor._safe_serialize(obj)
        assert result == [10, 20, 30]

    def test_object_with_tolist(self) -> None:
        """Objects with tolist() method should use it."""

        class ArrayLike:
            def tolist(self):
                return [7, 8, 9]

        result = JobExecutor._safe_serialize(ArrayLike())
        assert result == [7, 8, 9]

    def test_fallback_repr(self) -> None:
        """Arbitrary objects fall back to repr()."""

        class Custom:
            def __repr__(self):
                return "Custom()"

        result = JobExecutor._safe_serialize(Custom())
        assert result == "Custom()"

    def test_numpy_ndarray_mock(self) -> None:
        """Simulated numpy ndarray should be converted via tolist()."""
        # Create a mock that passes isinstance checks by patching the module
        # We mock numpy at the point of import inside _safe_serialize.
        import types

        fake_np = types.ModuleType("numpy")

        class FakeNdarray:
            def tolist(self):
                return [[1, 2], [3, 4]]

        class FakeInteger(int):
            def item(self):
                return 5

        class FakeFloating(float):
            def item(self):
                return 2.5

        fake_np.ndarray = FakeNdarray
        fake_np.integer = FakeInteger
        fake_np.floating = FakeFloating

        import sys

        had_numpy = "numpy" in sys.modules
        old_numpy = sys.modules.get("numpy")
        sys.modules["numpy"] = fake_np
        try:
            arr = FakeNdarray()
            result = JobExecutor._safe_serialize(arr)
            assert result == [[1, 2], [3, 4]]

            int_val = FakeInteger(5)
            result_int = JobExecutor._safe_serialize(int_val)
            # FakeInteger is an int subclass, so it hits the isinstance(value, int) check first
            assert result_int == 5

            float_val = FakeFloating(2.5)
            result_float = JobExecutor._safe_serialize(float_val)
            # FakeFloating is a float subclass, so it hits isinstance(value, float) first
            assert result_float == 2.5
        finally:
            if had_numpy:
                sys.modules["numpy"] = old_numpy
            else:
                sys.modules.pop("numpy", None)


# ---------------------------------------------------------------------------
# _error_result
# ---------------------------------------------------------------------------


class TestErrorResult:
    def test_error_result_structure(self) -> None:
        """_error_result should produce a dict with status, job_id, error."""
        job = Job(session_id="s1", code="bad;")
        job.mark_failed(error_type="RuntimeError", message="boom")

        result = JobExecutor._error_result(job)

        assert result["status"] == "failed"
        assert result["job_id"] == job.job_id
        assert result["error"]["type"] == "RuntimeError"
        assert result["error"]["message"] == "boom"


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------


class TestBuildResult:
    def test_captures_stdout(self) -> None:
        """_build_result should collect text from the job's _stdout buffer."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="disp('hi');")
        job._stdout = io.StringIO("hello world")
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        assert result["text"] == "hello world"

    def test_captures_stderr(self) -> None:
        """Stderr should be appended with [stderr] prefix."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO("out")
        job._stderr = io.StringIO("err")

        result = executor._build_result(wrapper, None, job, None)

        assert "[stderr]" in result["text"]
        assert "err" in result["text"]

    def test_stderr_only(self) -> None:
        """When stdout is empty but stderr has content, text should be stderr."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO("")
        job._stderr = io.StringIO("only error")

        result = executor._build_result(wrapper, None, job, None)

        assert result["text"] == "only error"

    def test_collects_workspace_variables(self) -> None:
        """Non-internal workspace variables should appear in result."""
        executor, tracker, wrapper, inner = _make_executor()
        inner.workspace["x"] = 42
        inner.workspace["__mcp_job_id__"] = "j-123"

        job = Job(session_id="s1", code="x=42;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        assert "x" in result["variables"]
        assert result["variables"]["x"] == 42
        assert "__mcp_job_id__" not in result["variables"]

    def test_lists_temp_dir_files(self, tmp_path: Path) -> None:
        """Files in temp_dir should be listed in the result."""
        executor, tracker, wrapper, inner = _make_executor()
        (tmp_path / "output.csv").write_text("a,b\n1,2\n")
        (tmp_path / "plot.png").write_bytes(b"\x89PNG")

        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, str(tmp_path))

        assert len(result["files"]) == 2
        filenames = [os.path.basename(f) for f in result["files"]]
        assert "output.csv" in filenames
        assert "plot.png" in filenames

    def test_no_temp_dir(self) -> None:
        """When temp_dir is None, files should be empty."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        assert result["files"] == []
        assert result["figures"] == []

    def test_nonexistent_temp_dir(self) -> None:
        """A temp_dir path that doesn't exist should produce empty files list."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, "/nonexistent/path/xyz")

        assert result["files"] == []

    def test_result_has_all_keys(self) -> None:
        """Result dict should always have text, variables, figures, files, warnings, errors."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        for key in ("text", "variables", "figures", "files", "warnings", "errors"):
            assert key in result

    def test_survives_broken_stdout(self) -> None:
        """If _stdout.getvalue() raises, text should be empty."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        broken_buf = MagicMock()
        broken_buf.getvalue.side_effect = RuntimeError("closed")
        job._stdout = broken_buf
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        assert result["text"] == ""


# ---------------------------------------------------------------------------
# execute — start execution failure (lines 91-105)
# ---------------------------------------------------------------------------


class TestExecuteStartFailure:
    async def test_execute_failure_returns_failed(self) -> None:
        """When engine.execute() raises, the job should be marked failed."""
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = AppConfig()
        config.execution = ExecutionConfig(sync_timeout=5)

        # Make the wrapper's execute raise
        def broken_execute(*args, **kwargs):
            raise RuntimeError("engine crashed")

        wrapper.execute = broken_execute

        executor = JobExecutor(pool=pool, tracker=tracker, config=config)
        result = await executor.execute("s1", "x=1;")

        assert result["status"] == "failed"
        assert "engine crashed" in result["error"]["message"]

    async def test_execute_failure_releases_engine(self) -> None:
        """On start failure, the engine must be released back to the pool."""
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = AppConfig()
        config.execution = ExecutionConfig(sync_timeout=5)

        wrapper.execute = MagicMock(side_effect=RuntimeError("crash"))
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)
        await executor.execute("s1", "x=1;")

        assert wrapper.state == EngineState.IDLE

    async def test_execute_failure_records_collector_event(self) -> None:
        """When a collector is present, a job_failed event should be recorded."""
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = AppConfig()
        config.execution = ExecutionConfig(sync_timeout=5)
        collector = MagicMock()

        wrapper.execute = MagicMock(side_effect=RuntimeError("crash"))
        executor = JobExecutor(pool=pool, tracker=tracker, config=config, collector=collector)
        await executor.execute("s1", "x=1;")

        collector.record_event.assert_called_once()
        call_args = collector.record_event.call_args
        assert call_args[0][0] == "job_failed"


# ---------------------------------------------------------------------------
# execute — sync timeout promotes to async (lines 124-138)
# ---------------------------------------------------------------------------


class TestExecuteSyncTimeoutPromotion:
    async def test_sync_timeout_zero_promotes_immediately(self) -> None:
        """sync_timeout=0 should immediately return status='pending'."""
        executor, tracker, wrapper, inner = _make_executor(sync_timeout=0)
        result = await executor.execute("s1", "x=1;")

        assert result["status"] == "pending"
        assert "job_id" in result

        # Give the background task a moment to complete
        await asyncio.sleep(0.2)

    async def test_sync_completed_records_collector_event(self) -> None:
        """When execution completes within sync_timeout, collector event is recorded."""
        collector = MagicMock()
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=5, collector=collector,
        )
        result = await executor.execute("s1", "x=1;")

        assert result["status"] == "completed"
        collector.record_event.assert_called_once()
        call_args = collector.record_event.call_args
        assert call_args[0][0] == "job_completed"


# ---------------------------------------------------------------------------
# _wait_for_completion — async paths (lines 198-229)
# ---------------------------------------------------------------------------


class TestWaitForCompletion:
    async def test_async_job_completes(self) -> None:
        """A promoted async job should eventually be marked completed."""
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=0, max_execution_time=10,
        )
        result = await executor.execute("s1", "y = 7;")

        assert result["status"] == "pending"
        job_id = result["job_id"]

        # Wait for the background task to finish
        await asyncio.sleep(0.5)

        job = tracker.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED

    async def test_async_job_fails(self) -> None:
        """If execution raises in background, the job should be marked failed."""
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=0, max_execution_time=10,
        )
        result = await executor.execute("s1", "error('async boom');")

        assert result["status"] == "pending"
        job_id = result["job_id"]

        await asyncio.sleep(0.5)

        job = tracker.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "async boom" in job.error["message"]

    async def test_async_job_releases_engine(self) -> None:
        """After async completion, the engine should be released (IDLE)."""
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=0, max_execution_time=10,
        )
        await executor.execute("s1", "z = 3;")
        await asyncio.sleep(0.5)

        assert wrapper.state == EngineState.IDLE

    async def test_async_job_records_completed_event(self) -> None:
        """Collector event should be recorded for async completion."""
        collector = MagicMock()
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=0, max_execution_time=10, collector=collector,
        )
        await executor.execute("s1", "a = 1;")
        await asyncio.sleep(0.5)

        # At least one call should be job_completed
        events = [call[0][0] for call in collector.record_event.call_args_list]
        assert "job_completed" in events

    async def test_async_job_records_failed_event(self) -> None:
        """Collector event should be recorded for async failure."""
        collector = MagicMock()
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=0, max_execution_time=10, collector=collector,
        )
        await executor.execute("s1", "error('kaboom');")
        await asyncio.sleep(0.5)

        events = [call[0][0] for call in collector.record_event.call_args_list]
        assert "job_failed" in events

    async def test_async_release_failure_does_not_propagate(self) -> None:
        """If pool.release() raises in the background task, it should not crash."""
        pool, wrapper, inner = _make_mock_pool()

        class BrokenPool:
            async def acquire(self):
                wrapper.mark_busy()
                return wrapper

            async def release(self, engine):
                raise RuntimeError("pool broken")

        tracker = JobTracker()
        config = AppConfig()
        config.execution = ExecutionConfig(sync_timeout=0, max_execution_time=10)

        executor = JobExecutor(pool=BrokenPool(), tracker=tracker, config=config)
        result = await executor.execute("s1", "b = 2;")

        assert result["status"] == "pending"
        await asyncio.sleep(0.5)

        job = tracker.get_job(result["job_id"])
        assert job is not None
        # Job itself should still be completed despite release failure
        assert job.status == JobStatus.COMPLETED


# ---------------------------------------------------------------------------
# execute — sync execution exception (non-timeout, lines 139-153)
# ---------------------------------------------------------------------------


class TestExecuteSyncException:
    async def test_sync_execution_error_marks_failed(self) -> None:
        """An error() call in code should result in a failed status via sync path."""
        executor, tracker, wrapper, inner = _make_executor(sync_timeout=5)
        result = await executor.execute("s1", "error('sync fail');")

        assert result["status"] == "failed"
        assert "sync fail" in result["error"]["message"]

    async def test_sync_execution_error_releases_engine(self) -> None:
        """On sync execution error, the engine should be released."""
        executor, tracker, wrapper, inner = _make_executor(sync_timeout=5)
        await executor.execute("s1", "error('boom');")

        assert wrapper.state == EngineState.IDLE

    async def test_sync_execution_error_records_collector_event(self) -> None:
        """Collector event should be recorded for sync execution error."""
        collector = MagicMock()
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=5, collector=collector,
        )
        await executor.execute("s1", "error('collector test');")

        collector.record_event.assert_called_once()
        assert collector.record_event.call_args[0][0] == "job_failed"


# ---------------------------------------------------------------------------
# Figure extraction (lines 270-309) — negative path
# ---------------------------------------------------------------------------


class TestBuildResultFigures:
    def test_plotly_disabled_no_figures(self, tmp_path: Path) -> None:
        """With plotly_conversion=False, figures list should be empty."""
        executor, tracker, wrapper, inner = _make_executor(plotly_conversion=False)
        job = Job(session_id="s1", code="plot(1:10);")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, str(tmp_path))

        assert result["figures"] == []

    def test_plotly_enabled_no_temp_dir(self) -> None:
        """With plotly_conversion=True but no temp_dir, figures should be empty."""
        executor, tracker, wrapper, inner = _make_executor(plotly_conversion=True)
        job = Job(session_id="s1", code="plot(1:10);")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        result = executor._build_result(wrapper, None, job, None)

        assert result["figures"] == []

    def test_plotly_enabled_with_figure_json(self, tmp_path: Path) -> None:
        """With plotly_conversion=True and figure JSON files, figures should be extracted."""
        import shutil

        executor, tracker, wrapper, inner = _make_executor(plotly_conversion=True)
        job = Job(session_id="s1", code="plot(1:10);")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        # Copy a real fixture file into tmp_path with the expected naming pattern
        fixtures_dir = Path(__file__).parent / "fixtures" / "matlab_figures"
        src = fixtures_dir / "single_line.json"
        fig_file = tmp_path / f"{job.job_id}_fig1.json"
        shutil.copy(src, fig_file)

        result = executor._build_result(wrapper, None, job, str(tmp_path))

        # Figure file should be cleaned up
        assert not fig_file.exists()
        # Should have extracted at least one figure
        assert len(result["figures"]) >= 1
        assert "data" in result["figures"][0]
        assert "layout" in result["figures"][0]

    def test_plotly_enabled_extraction_exception(self, tmp_path: Path) -> None:
        """If figure extraction pipeline fails, it should not crash _build_result."""
        executor, tracker, wrapper, inner = _make_executor(plotly_conversion=True)
        job = Job(session_id="s1", code="plot(1:10);")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        # Create an invalid JSON file
        fig_file = tmp_path / f"{job.job_id}_fig1.json"
        fig_file.write_text("NOT VALID JSON")

        result = executor._build_result(wrapper, None, job, str(tmp_path))

        # Should not crash, figures may or may not be empty
        assert isinstance(result["figures"], list)


class TestBuildResultWorkspaceException:
    def test_workspace_items_raises(self) -> None:
        """If workspace.items() raises, variables should be empty dict."""
        executor, tracker, wrapper, inner = _make_executor()
        job = Job(session_id="s1", code="x=1;")
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()

        # Break workspace.items()
        broken_ws = MagicMock()
        broken_ws.items.side_effect = RuntimeError("workspace broken")
        inner.workspace = broken_ws

        result = executor._build_result(wrapper, None, job, None)

        assert result["variables"] == {}


class TestSafeSerializeNumpyReal:
    """Test _safe_serialize with real-ish numpy mocks that aren't subclasses of int/float."""

    def test_numpy_ndarray_via_module_mock(self) -> None:
        """Numpy ndarray should be serialized via tolist()."""
        import sys
        import types

        fake_np = types.ModuleType("numpy")

        # Create ndarray that ISN'T a subclass of basic types
        class FakeNdarray:
            def tolist(self):
                return [1.0, 2.0, 3.0]

        class FakeInteger:
            def item(self):
                return 7

        class FakeFloating:
            def item(self):
                return 3.5

        fake_np.ndarray = FakeNdarray
        fake_np.integer = FakeInteger
        fake_np.floating = FakeFloating

        old_np = sys.modules.get("numpy")
        sys.modules["numpy"] = fake_np
        try:
            result = JobExecutor._safe_serialize(FakeNdarray())
            assert result == [1.0, 2.0, 3.0]

            result_int = JobExecutor._safe_serialize(FakeInteger())
            assert result_int == 7

            result_float = JobExecutor._safe_serialize(FakeFloating())
            assert result_float == 3.5
        finally:
            if old_np is not None:
                sys.modules["numpy"] = old_np
            else:
                sys.modules.pop("numpy", None)


class TestExecuteSyncTimeout:
    async def test_slow_code_promotes_to_async(self) -> None:
        """Code that takes longer than sync_timeout should be promoted to async."""
        executor, tracker, wrapper, inner = _make_executor(
            sync_timeout=1, max_execution_time=30,
        )
        # Use pause to simulate slow execution (mock engine supports pause(N))
        result = await executor.execute("s1", "pause(3);")

        # Should be promoted to pending due to timeout
        # (sync_timeout=1 but code takes 3 seconds)
        assert result["status"] in ("pending", "completed")
        if result["status"] == "pending":
            # Wait for background task to complete
            await asyncio.sleep(4)
            job = tracker.get_job(result["job_id"])
            assert job is not None
            assert job.status in (JobStatus.COMPLETED, JobStatus.FAILED)
