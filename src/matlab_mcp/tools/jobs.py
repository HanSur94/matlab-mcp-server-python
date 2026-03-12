"""Job management MCP tool implementations.

Provides:
- get_job_status_impl  — status of a single job (with .progress file support)
- get_job_result_impl  — full result for completed jobs
- cancel_job_impl      — cancel pending/running jobs
- list_jobs_impl       — list all jobs for a session
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def get_job_status_impl(
    job_id: str,
    tracker: Any,
    temp_dir: Optional[str] = None,
) -> dict:
    """Return the status of a job, reading a .progress file if running.

    Parameters
    ----------
    job_id:
        The job ID to query.
    tracker:
        A :class:`~matlab_mcp.jobs.tracker.JobTracker` instance.
    temp_dir:
        Optional directory to look for a ``<job_id>.progress`` file.

    Returns
    -------
    dict
        Status dict including ``job_id``, ``status``, and optional ``progress``.
    """
    job = tracker.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "not_found"}

    result: dict = {
        "job_id": job.job_id,
        "status": job.status.value,
        "session_id": job.session_id,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "elapsed_seconds": job.elapsed_seconds,
    }

    # Read progress file if the job is running
    if job.status.value == "running" and temp_dir is not None:
        progress_file = Path(temp_dir) / f"{job_id}.progress"
        try:
            if progress_file.exists():
                result["progress"] = progress_file.read_text(encoding="utf-8").strip()
        except Exception:
            logger.debug("Could not read progress file %s", progress_file)

    return result


async def get_job_result_impl(
    job_id: str,
    tracker: Any,
) -> dict:
    """Return the full result for a completed job.

    Parameters
    ----------
    job_id:
        The job ID to query.
    tracker:
        A :class:`~matlab_mcp.jobs.tracker.JobTracker` instance.

    Returns
    -------
    dict
        Full result dict, or an error dict if not found / not completed.
    """
    job = tracker.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "not_found"}

    status = job.status.value
    if status == "completed":
        return {
            "job_id": job.job_id,
            "status": status,
            "result": job.result,
        }
    elif status == "failed":
        return {
            "job_id": job.job_id,
            "status": status,
            "error": job.error,
        }
    else:
        return {
            "job_id": job.job_id,
            "status": status,
            "message": f"Job is {status}; result not yet available",
        }


async def cancel_job_impl(
    job_id: str,
    tracker: Any,
) -> dict:
    """Cancel a pending or running job.

    Parameters
    ----------
    job_id:
        The job ID to cancel.
    tracker:
        A :class:`~matlab_mcp.jobs.tracker.JobTracker` instance.

    Returns
    -------
    dict
        Result dict with ``job_id``, ``status``, and ``cancelled`` boolean.
    """
    job = tracker.get_job(job_id)
    if job is None:
        return {"job_id": job_id, "status": "not_found", "cancelled": False}

    status = job.status.value
    if status not in ("pending", "running"):
        return {
            "job_id": job_id,
            "status": status,
            "cancelled": False,
            "message": f"Cannot cancel job in state '{status}'",
        }

    # Attempt to cancel the underlying future if available
    if job.future is not None:
        try:
            job.future.cancel()
        except Exception:
            logger.debug("Failed to cancel future for job %s", job_id)

    job.mark_cancelled()
    return {"job_id": job_id, "status": "cancelled", "cancelled": True}


async def list_jobs_impl(
    session_id: str,
    tracker: Any,
) -> dict:
    """List all jobs for a session.

    Parameters
    ----------
    session_id:
        The session to list jobs for.
    tracker:
        A :class:`~matlab_mcp.jobs.tracker.JobTracker` instance.

    Returns
    -------
    dict
        Dict containing a ``jobs`` list of job summary dicts.
    """
    jobs = tracker.list_jobs(session_id=session_id)
    job_summaries = [
        {
            "job_id": j.job_id,
            "status": j.status.value,
            "created_at": j.created_at,
            "started_at": j.started_at,
            "completed_at": j.completed_at,
            "elapsed_seconds": j.elapsed_seconds,
        }
        for j in jobs
    ]
    return {
        "session_id": session_id,
        "jobs": job_summaries,
        "count": len(job_summaries),
    }
