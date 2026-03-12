"""Tests for the jobs system: models, tracker, and executor."""
from __future__ import annotations

import asyncio
import time
import types
import unittest.mock as mock
from typing import Any

import pytest

from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker


# ===========================================================================
# Task 7: Job Models
# ===========================================================================

class TestJobStatus:
    def test_all_statuses_exist(self):
        assert JobStatus.PENDING
        assert JobStatus.RUNNING
        assert JobStatus.COMPLETED
        assert JobStatus.FAILED
        assert JobStatus.CANCELLED

    def test_statuses_are_distinct(self):
        statuses = {JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED,
                    JobStatus.FAILED, JobStatus.CANCELLED}
        assert len(statuses) == 5


class TestJobCreation:
    def test_job_has_auto_generated_id(self):
        job = Job(session_id="s1", code="x = 1;")
        assert job.job_id.startswith("j-")
        assert len(job.job_id) > 2

    def test_two_jobs_have_different_ids(self):
        j1 = Job(session_id="s1", code="x = 1;")
        j2 = Job(session_id="s1", code="x = 1;")
        assert j1.job_id != j2.job_id

    def test_initial_status_is_pending(self):
        job = Job(session_id="s1", code="x = 1;")
        assert job.status == JobStatus.PENDING

    def test_session_id_stored(self):
        job = Job(session_id="my-session", code="disp('hi');")
        assert job.session_id == "my-session"

    def test_code_stored(self):
        code = "x = 42;"
        job = Job(session_id="s1", code=code)
        assert job.code == code

    def test_initial_fields_are_none(self):
        job = Job(session_id="s1", code="x = 1;")
        assert job.engine_id is None
        assert job.result is None
        assert job.error is None
        assert job.started_at is None
        assert job.completed_at is None
        assert job.future is None

    def test_created_at_is_set(self):
        before = time.time()
        job = Job(session_id="s1", code="x = 1;")
        after = time.time()
        assert before <= job.created_at <= after

    def test_elapsed_seconds_none_before_start(self):
        job = Job(session_id="s1", code="x = 1;")
        assert job.elapsed_seconds is None


class TestJobMarkRunning:
    def test_mark_running_sets_status(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        assert job.status == JobStatus.RUNNING

    def test_mark_running_sets_engine_id(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-7")
        assert job.engine_id == "engine-7"

    def test_mark_running_sets_started_at(self):
        before = time.time()
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        after = time.time()
        assert before <= job.started_at <= after

    def test_elapsed_seconds_increases_after_start(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        time.sleep(0.05)
        assert job.elapsed_seconds >= 0.04


class TestJobMarkCompleted:
    def test_mark_completed_sets_status(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "done"})
        assert job.status == JobStatus.COMPLETED

    def test_mark_completed_stores_result(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        result = {"text": "output", "variables": {}}
        job.mark_completed(result)
        assert job.result == result

    def test_mark_completed_sets_completed_at(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        before = time.time()
        job.mark_completed(None)
        after = time.time()
        assert before <= job.completed_at <= after

    def test_elapsed_seconds_fixed_after_completion(self):
        job = Job(session_id="s1", code="x = 1;")
        job.mark_running("engine-0")
        time.sleep(0.05)
        job.mark_completed(None)
        elapsed_at_completion = job.elapsed_seconds
        time.sleep(0.05)
        # elapsed_seconds should not grow after completion
        assert job.elapsed_seconds == elapsed_at_completion


class TestJobMarkFailed:
    def test_mark_failed_sets_status(self):
        job = Job(session_id="s1", code="error('boom');")
        job.mark_running("engine-0")
        job.mark_failed("MatlabExecutionError", "boom")
        assert job.status == JobStatus.FAILED

    def test_mark_failed_stores_error(self):
        job = Job(session_id="s1", code="error('boom');")
        job.mark_running("engine-0")
        job.mark_failed("MatlabExecutionError", "boom", matlab_id="MATLAB:error",
                        stack_trace="line 1")
        assert job.error["type"] == "MatlabExecutionError"
        assert job.error["message"] == "boom"
        assert job.error["matlab_id"] == "MATLAB:error"
        assert job.error["stack_trace"] == "line 1"

    def test_mark_failed_sets_completed_at(self):
        job = Job(session_id="s1", code="error('boom');")
        job.mark_running("engine-0")
        before = time.time()
        job.mark_failed("Error", "msg")
        after = time.time()
        assert before <= job.completed_at <= after

    def test_mark_failed_optional_fields_default_none(self):
        job = Job(session_id="s1", code="error('boom');")
        job.mark_running("engine-0")
        job.mark_failed("SomeError", "something went wrong")
        assert job.error["matlab_id"] is None
        assert job.error["stack_trace"] is None


class TestJobMarkCancelled:
    def test_mark_cancelled_sets_status(self):
        job = Job(session_id="s1", code="pause(100);")
        job.mark_cancelled()
        assert job.status == JobStatus.CANCELLED

    def test_mark_cancelled_sets_completed_at(self):
        job = Job(session_id="s1", code="pause(100);")
        before = time.time()
        job.mark_cancelled()
        after = time.time()
        assert before <= job.completed_at <= after


# ===========================================================================
# Task 7: Job Tracker
# ===========================================================================

class TestJobTrackerCreate:
    def test_create_job_returns_job(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        assert isinstance(job, Job)

    def test_create_job_stores_session_id(self):
        tracker = JobTracker()
        job = tracker.create_job("my-session", "x = 1;")
        assert job.session_id == "my-session"

    def test_create_job_stores_code(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "disp('hello');")
        assert job.code == "disp('hello');"

    def test_create_job_is_pending(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        assert job.status == JobStatus.PENDING


class TestJobTrackerGet:
    def test_get_existing_job(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        retrieved = tracker.get_job(job.job_id)
        assert retrieved is job

    def test_get_nonexistent_job_returns_none(self):
        tracker = JobTracker()
        assert tracker.get_job("j-nonexistent") is None


class TestJobTrackerList:
    def test_list_all_jobs(self):
        tracker = JobTracker()
        j1 = tracker.create_job("s1", "x = 1;")
        j2 = tracker.create_job("s2", "y = 2;")
        jobs = tracker.list_jobs()
        assert j1 in jobs
        assert j2 in jobs

    def test_list_jobs_by_session(self):
        tracker = JobTracker()
        j1 = tracker.create_job("s1", "x = 1;")
        j2 = tracker.create_job("s2", "y = 2;")
        j3 = tracker.create_job("s1", "z = 3;")
        s1_jobs = tracker.list_jobs("s1")
        assert j1 in s1_jobs
        assert j3 in s1_jobs
        assert j2 not in s1_jobs

    def test_list_jobs_empty_session_returns_empty(self):
        tracker = JobTracker()
        tracker.create_job("s1", "x = 1;")
        assert tracker.list_jobs("unknown-session") == []

    def test_list_jobs_no_filter_returns_all(self):
        tracker = JobTracker()
        for i in range(5):
            tracker.create_job(f"s{i}", "x = 1;")
        assert len(tracker.list_jobs()) == 5


class TestJobTrackerHasActiveJobs:
    def test_pending_job_is_active(self):
        tracker = JobTracker()
        tracker.create_job("s1", "x = 1;")
        assert tracker.has_active_jobs("s1") is True

    def test_running_job_is_active(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        assert tracker.has_active_jobs("s1") is True

    def test_completed_job_not_active(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed(None)
        assert tracker.has_active_jobs("s1") is False

    def test_failed_job_not_active(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "error('bad');")
        job.mark_running("engine-0")
        job.mark_failed("Error", "bad")
        assert tracker.has_active_jobs("s1") is False

    def test_cancelled_job_not_active(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_cancelled()
        assert tracker.has_active_jobs("s1") is False

    def test_no_jobs_for_session_returns_false(self):
        tracker = JobTracker()
        assert tracker.has_active_jobs("nonexistent") is False

    def test_other_session_active_not_reported(self):
        tracker = JobTracker()
        tracker.create_job("s2", "x = 1;")  # pending in s2
        assert tracker.has_active_jobs("s1") is False


class TestJobTrackerPrune:
    def test_prune_removes_expired_completed_jobs(self):
        tracker = JobTracker(retention_seconds=1)
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed(None)
        # Backdate completed_at
        job.completed_at = time.time() - 2
        removed = tracker.prune()
        assert removed == 1
        assert tracker.get_job(job.job_id) is None

    def test_prune_keeps_recent_completed_jobs(self):
        tracker = JobTracker(retention_seconds=3600)
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed(None)
        removed = tracker.prune()
        assert removed == 0
        assert tracker.get_job(job.job_id) is not None

    def test_prune_removes_expired_failed_jobs(self):
        tracker = JobTracker(retention_seconds=1)
        job = tracker.create_job("s1", "error('x');")
        job.mark_running("engine-0")
        job.mark_failed("Error", "x")
        job.completed_at = time.time() - 2
        removed = tracker.prune()
        assert removed == 1

    def test_prune_removes_expired_cancelled_jobs(self):
        tracker = JobTracker(retention_seconds=1)
        job = tracker.create_job("s1", "pause(100);")
        job.mark_cancelled()
        job.completed_at = time.time() - 2
        removed = tracker.prune()
        assert removed == 1

    def test_prune_keeps_active_jobs(self):
        tracker = JobTracker(retention_seconds=0)
        job = tracker.create_job("s1", "x = 1;")
        # Job is still PENDING with no completed_at — should not be pruned
        removed = tracker.prune()
        assert removed == 0
        assert tracker.get_job(job.job_id) is not None

    def test_prune_returns_count(self):
        tracker = JobTracker(retention_seconds=1)
        for _ in range(3):
            job = tracker.create_job("s1", "x = 1;")
            job.mark_running("engine-0")
            job.mark_completed(None)
            job.completed_at = time.time() - 2
        assert tracker.prune() == 3


# ===========================================================================
# Task 8: Job Executor
# ===========================================================================

def _make_mock_pool():
    """Create a minimal mock EnginePoolManager for executor tests."""
    from tests.mocks.matlab_engine_mock import MockMatlabEngine

    mock_engine_inner = MockMatlabEngine()

    # Wrap it in a MatlabEngineWrapper-like object
    from matlab_mcp.config import PoolConfig, WorkspaceConfig
    from matlab_mcp.pool.engine import MatlabEngineWrapper

    pool_cfg = PoolConfig(min_engines=1, max_engines=2)
    workspace_cfg = WorkspaceConfig()
    wrapper = MatlabEngineWrapper("engine-0", pool_cfg, workspace_cfg)
    wrapper._engine = mock_engine_inner
    wrapper._state = __import__("matlab_mcp.pool.engine", fromlist=["EngineState"]).EngineState.IDLE

    class MockPool:
        async def acquire(self):
            wrapper.mark_busy()
            return wrapper

        async def release(self, engine):
            engine.mark_idle()

    return MockPool(), wrapper, mock_engine_inner


def _make_app_config(sync_timeout: int = 5):
    from matlab_mcp.config import AppConfig, ExecutionConfig
    cfg = AppConfig()
    cfg.execution = ExecutionConfig(sync_timeout=sync_timeout)
    return cfg


class TestJobExecutorSync:
    async def test_sync_execution_returns_result(self):
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=5)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        result = await executor.execute("s1", "x = 42;")

        assert result["status"] == "completed"
        assert "job_id" in result

    async def test_sync_execution_job_is_completed(self):
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=5)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        result = await executor.execute("s1", "x = 42;")
        job = tracker.get_job(result["job_id"])
        assert job is not None
        assert job.status == JobStatus.COMPLETED

    async def test_sync_execution_injects_job_context(self):
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=5)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        await executor.execute("s1", "x = 1;")
        # __mcp_job_id__ should have been injected into workspace
        assert "__mcp_job_id__" in inner.workspace


class TestJobExecutorAsync:
    async def test_async_promotion_when_timeout_zero(self):
        """With sync_timeout=0, execution should be promoted to async."""
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=0)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        result = await executor.execute("s1", "x = 1;")
        assert result["status"] == "pending"
        assert "job_id" in result

    async def test_async_promotion_job_tracked(self):
        """With sync_timeout=0, the job should be in the tracker."""
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=0)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        result = await executor.execute("s1", "x = 1;")
        job_id = result["job_id"]
        job = tracker.get_job(job_id)
        assert job is not None


class TestJobExecutorError:
    async def test_execution_error_marks_job_failed(self):
        from matlab_mcp.jobs.executor import JobExecutor
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=5)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        result = await executor.execute("s1", "error('test failure');")
        assert result["status"] == "failed"
        job = tracker.get_job(result["job_id"])
        assert job.status == JobStatus.FAILED

    async def test_execution_error_engine_released(self):
        """After a sync error, engine should be back in pool (IDLE state)."""
        from matlab_mcp.jobs.executor import JobExecutor
        from matlab_mcp.pool.engine import EngineState
        pool, wrapper, inner = _make_mock_pool()
        tracker = JobTracker()
        config = _make_app_config(sync_timeout=5)
        executor = JobExecutor(pool=pool, tracker=tracker, config=config)

        await executor.execute("s1", "error('oops');")
        assert wrapper.state == EngineState.IDLE
