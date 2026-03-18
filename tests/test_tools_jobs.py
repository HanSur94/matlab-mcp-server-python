"""Tests for job management MCP tool implementations (tools/jobs.py).

Covers all four async functions:
- get_job_status_impl
- get_job_result_impl
- cancel_job_impl
- list_jobs_impl

Uses real JobTracker and Job instances — no mocks for the job system itself.
"""
from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock

from matlab_mcp.jobs.models import JobStatus
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.tools.jobs import (
    cancel_job_impl,
    get_job_result_impl,
    get_job_status_impl,
    list_jobs_impl,
)


# ===========================================================================
# get_job_status_impl
# ===========================================================================


class TestGetJobStatusNotFound:
    async def test_returns_not_found_for_missing_job(self):
        tracker = JobTracker()
        result = await get_job_status_impl("j-nonexistent", tracker)
        assert result == {"job_id": "j-nonexistent", "status": "not_found"}

    async def test_not_found_has_no_extra_keys(self):
        tracker = JobTracker()
        result = await get_job_status_impl("j-ghost", tracker)
        assert set(result.keys()) == {"job_id", "status"}


class TestGetJobStatusPending:
    async def test_pending_job_status(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["status"] == "pending"

    async def test_pending_job_includes_session_id(self):
        tracker = JobTracker()
        job = tracker.create_job("my-session", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["session_id"] == "my-session"

    async def test_pending_job_includes_created_at(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["created_at"] == job.created_at

    async def test_pending_job_started_at_is_none(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["started_at"] is None

    async def test_pending_job_completed_at_is_none(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["completed_at"] is None

    async def test_pending_job_elapsed_seconds_is_none(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["elapsed_seconds"] is None


class TestGetJobStatusRunning:
    async def test_running_job_status(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(10);")
        job.mark_running("engine-0")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["status"] == "running"

    async def test_running_job_has_started_at(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(10);")
        job.mark_running("engine-0")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["started_at"] is not None

    async def test_running_job_has_elapsed_seconds(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(10);")
        job.mark_running("engine-0")
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["elapsed_seconds"] is not None
        assert result["elapsed_seconds"] >= 0


class TestGetJobStatusCompleted:
    async def test_completed_job_status(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 42;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "42"})
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["status"] == "completed"

    async def test_completed_job_has_completed_at(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 42;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "42"})
        result = await get_job_status_impl(job.job_id, tracker)
        assert result["completed_at"] is not None


class TestGetJobStatusProgress:
    async def test_reads_progress_file_for_running_job(self, tmp_path):
        tracker = JobTracker()
        job = tracker.create_job("s1", "for i=1:100, end")
        job.mark_running("engine-0")

        progress_file = tmp_path / f"{job.job_id}.progress"
        progress_file.write_text("50/100 iterations complete", encoding="utf-8")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert result["progress"] == "50/100 iterations complete"

    async def test_strips_whitespace_from_progress_file(self, tmp_path):
        tracker = JobTracker()
        job = tracker.create_job("s1", "for i=1:10, end")
        job.mark_running("engine-0")

        progress_file = tmp_path / f"{job.job_id}.progress"
        progress_file.write_text("  75%  \n", encoding="utf-8")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert result["progress"] == "75%"

    async def test_no_progress_key_when_file_missing(self, tmp_path):
        tracker = JobTracker()
        job = tracker.create_job("s1", "for i=1:10, end")
        job.mark_running("engine-0")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert "progress" not in result

    async def test_no_progress_key_when_temp_dir_is_none(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "for i=1:10, end")
        job.mark_running("engine-0")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=None)
        assert "progress" not in result

    async def test_no_progress_for_pending_job(self, tmp_path):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")

        progress_file = tmp_path / f"{job.job_id}.progress"
        progress_file.write_text("should not be read", encoding="utf-8")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert "progress" not in result

    async def test_no_progress_for_completed_job(self, tmp_path):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "done"})

        progress_file = tmp_path / f"{job.job_id}.progress"
        progress_file.write_text("leftover progress", encoding="utf-8")

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert "progress" not in result

    async def test_graceful_on_unreadable_progress_file(self, tmp_path):
        """If the progress file cannot be read, no progress key is returned."""
        tracker = JobTracker()
        job = tracker.create_job("s1", "for i=1:10, end")
        job.mark_running("engine-0")

        # Create a directory with the progress filename so read_text fails
        bad_progress = tmp_path / f"{job.job_id}.progress"
        bad_progress.mkdir()

        result = await get_job_status_impl(job.job_id, tracker, temp_dir=str(tmp_path))
        assert "progress" not in result


# ===========================================================================
# get_job_result_impl
# ===========================================================================


class TestGetJobResultNotFound:
    async def test_returns_not_found_for_missing_job(self):
        tracker = JobTracker()
        result = await get_job_result_impl("j-missing", tracker)
        assert result == {"job_id": "j-missing", "status": "not_found"}


class TestGetJobResultCompleted:
    async def test_completed_job_returns_result(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 42;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "ans = 42", "variables": {"x": 42}})

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "completed"
        assert result["result"] == {"text": "ans = 42", "variables": {"x": 42}}

    async def test_completed_job_with_none_result(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "clear;")
        job.mark_running("engine-0")
        job.mark_completed(None)

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "completed"
        assert result["result"] is None

    async def test_completed_result_has_correct_keys(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "ok"})

        result = await get_job_result_impl(job.job_id, tracker)
        assert set(result.keys()) == {"job_id", "status", "result"}


class TestGetJobResultFailed:
    async def test_failed_job_returns_error(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "error('boom');")
        job.mark_running("engine-0")
        job.mark_failed("MatlabExecutionError", "boom")

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "failed"
        assert result["error"]["type"] == "MatlabExecutionError"
        assert result["error"]["message"] == "boom"

    async def test_failed_result_has_correct_keys(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "error('x');")
        job.mark_running("engine-0")
        job.mark_failed("Error", "x")

        result = await get_job_result_impl(job.job_id, tracker)
        assert set(result.keys()) == {"job_id", "status", "error"}


class TestGetJobResultStillRunning:
    async def test_pending_job_returns_message(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "pending"
        assert "not yet available" in result["message"]

    async def test_running_job_returns_message(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "running"
        assert "not yet available" in result["message"]

    async def test_cancelled_job_returns_message(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_cancelled()

        result = await get_job_result_impl(job.job_id, tracker)
        assert result["status"] == "cancelled"
        assert "not yet available" in result["message"]

    async def test_running_result_has_correct_keys(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        result = await get_job_result_impl(job.job_id, tracker)
        assert set(result.keys()) == {"job_id", "status", "message"}


# ===========================================================================
# cancel_job_impl
# ===========================================================================


class TestCancelJobNotFound:
    async def test_returns_not_found_for_missing_job(self):
        tracker = JobTracker()
        result = await cancel_job_impl("j-nonexistent", tracker)
        assert result["status"] == "not_found"
        assert result["cancelled"] is False

    async def test_not_found_has_correct_keys(self):
        tracker = JobTracker()
        result = await cancel_job_impl("j-nope", tracker)
        assert set(result.keys()) == {"job_id", "status", "cancelled"}


class TestCancelJobAlreadyCompleted:
    async def test_cannot_cancel_completed_job(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "done"})

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is False
        assert result["status"] == "completed"
        assert "Cannot cancel" in result["message"]

    async def test_cannot_cancel_failed_job(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "error('x');")
        job.mark_running("engine-0")
        job.mark_failed("Error", "x")

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is False
        assert result["status"] == "failed"

    async def test_cannot_cancel_already_cancelled_job(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(10);")
        job.mark_cancelled()

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is False
        assert result["status"] == "cancelled"


class TestCancelJobPending:
    async def test_cancel_pending_job_succeeds(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True
        assert result["status"] == "cancelled"

    async def test_cancel_pending_job_marks_cancelled(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")

        await cancel_job_impl(job.job_id, tracker)
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_pending_job_sets_completed_at(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")

        await cancel_job_impl(job.job_id, tracker)
        assert job.completed_at is not None


class TestCancelJobRunning:
    async def test_cancel_running_job_succeeds(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True
        assert result["status"] == "cancelled"

    async def test_cancel_running_job_marks_cancelled(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        await cancel_job_impl(job.job_id, tracker)
        assert job.status == JobStatus.CANCELLED

    async def test_cancel_running_job_with_future(self):
        """When a running job has a future, cancel_job_impl should call future.cancel()."""
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        mock_future = MagicMock(spec=Future)
        job.future = mock_future

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True
        mock_future.cancel.assert_called_once()

    async def test_cancel_running_job_without_future(self):
        """Cancelling a running job with no future should still succeed."""
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")
        assert job.future is None

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True

    async def test_cancel_handles_future_cancel_exception(self):
        """If future.cancel() raises, the job should still be marked cancelled."""
        tracker = JobTracker()
        job = tracker.create_job("s1", "pause(100);")
        job.mark_running("engine-0")

        mock_future = MagicMock(spec=Future)
        mock_future.cancel.side_effect = RuntimeError("cannot cancel")
        job.future = mock_future

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True
        assert job.status == JobStatus.CANCELLED


class TestCancelJobPendingWithFuture:
    async def test_cancel_pending_job_with_future(self):
        """Edge case: a pending job may have a future attached."""
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 1;")

        mock_future = MagicMock(spec=Future)
        job.future = mock_future

        result = await cancel_job_impl(job.job_id, tracker)
        assert result["cancelled"] is True
        mock_future.cancel.assert_called_once()


# ===========================================================================
# list_jobs_impl
# ===========================================================================


class TestListJobsEmpty:
    async def test_empty_session_returns_zero_count(self):
        tracker = JobTracker()
        result = await list_jobs_impl("s1", tracker)
        assert result["count"] == 0
        assert result["jobs"] == []

    async def test_empty_session_includes_session_id(self):
        tracker = JobTracker()
        result = await list_jobs_impl("my-session", tracker)
        assert result["session_id"] == "my-session"

    async def test_result_has_correct_keys(self):
        tracker = JobTracker()
        result = await list_jobs_impl("s1", tracker)
        assert set(result.keys()) == {"session_id", "jobs", "count"}


class TestListJobsMultiple:
    async def test_lists_all_jobs_for_session(self):
        tracker = JobTracker()
        j1 = tracker.create_job("s1", "x = 1;")
        j2 = tracker.create_job("s1", "y = 2;")

        result = await list_jobs_impl("s1", tracker)
        assert result["count"] == 2
        job_ids = {j["job_id"] for j in result["jobs"]}
        assert job_ids == {j1.job_id, j2.job_id}

    async def test_does_not_include_other_session_jobs(self):
        tracker = JobTracker()
        tracker.create_job("s1", "x = 1;")
        tracker.create_job("s2", "y = 2;")
        tracker.create_job("s1", "z = 3;")

        result = await list_jobs_impl("s1", tracker)
        assert result["count"] == 2

    async def test_job_summaries_include_status(self):
        tracker = JobTracker()
        j1 = tracker.create_job("s1", "x = 1;")
        j2 = tracker.create_job("s1", "pause(10);")
        j2.mark_running("engine-0")

        result = await list_jobs_impl("s1", tracker)
        status_map = {j["job_id"]: j["status"] for j in result["jobs"]}
        assert status_map[j1.job_id] == "pending"
        assert status_map[j2.job_id] == "running"

    async def test_job_summaries_have_correct_keys(self):
        tracker = JobTracker()
        tracker.create_job("s1", "x = 1;")

        result = await list_jobs_impl("s1", tracker)
        summary = result["jobs"][0]
        assert set(summary.keys()) == {
            "job_id",
            "status",
            "created_at",
            "started_at",
            "completed_at",
            "elapsed_seconds",
        }

    async def test_count_matches_jobs_length(self):
        tracker = JobTracker()
        for i in range(5):
            tracker.create_job("s1", f"x = {i};")

        result = await list_jobs_impl("s1", tracker)
        assert result["count"] == len(result["jobs"]) == 5

    async def test_completed_job_summary_has_timestamps(self):
        tracker = JobTracker()
        job = tracker.create_job("s1", "x = 42;")
        job.mark_running("engine-0")
        job.mark_completed({"text": "42"})

        result = await list_jobs_impl("s1", tracker)
        summary = result["jobs"][0]
        assert summary["started_at"] is not None
        assert summary["completed_at"] is not None
        assert summary["elapsed_seconds"] is not None
        assert summary["elapsed_seconds"] >= 0

    async def test_mixed_statuses_listed(self):
        tracker = JobTracker()
        tracker.create_job("s1", "a = 1;")
        j_running = tracker.create_job("s1", "b = 2;")
        j_running.mark_running("engine-0")
        j_completed = tracker.create_job("s1", "c = 3;")
        j_completed.mark_running("engine-0")
        j_completed.mark_completed({"text": "3"})
        j_failed = tracker.create_job("s1", "error('x');")
        j_failed.mark_running("engine-0")
        j_failed.mark_failed("Error", "x")
        j_cancelled = tracker.create_job("s1", "pause(99);")
        j_cancelled.mark_cancelled()

        result = await list_jobs_impl("s1", tracker)
        assert result["count"] == 5
        statuses = {j["status"] for j in result["jobs"]}
        assert statuses == {"pending", "running", "completed", "failed", "cancelled"}
