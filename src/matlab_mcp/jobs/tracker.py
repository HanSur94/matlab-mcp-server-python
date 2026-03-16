"""Job tracker for managing in-flight and historical MATLAB execution jobs."""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

from matlab_mcp.jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)

# Active statuses — jobs that are not yet terminal
_ACTIVE_STATUSES = {JobStatus.PENDING, JobStatus.RUNNING}


class JobTracker:
    """Tracks all jobs (active and historical) keyed by job_id.

    Parameters
    ----------
    retention_seconds:
        How long completed/failed/cancelled jobs are retained before pruning.
        Defaults to 86400 (24 hours).
    """

    def __init__(self, retention_seconds: int = 86400) -> None:
        self._jobs: Dict[str, Job] = {}
        self._retention_seconds = retention_seconds
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_job(self, session_id: str, code: str) -> Job:
        """Create a new PENDING job and register it in the tracker.

        Returns the newly created :class:`Job`.
        """
        job = Job(session_id=session_id, code=code)
        with self._lock:
            self._jobs[job.job_id] = job
        logger.debug("Created job %s for session %s", job.job_id, session_id)
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Return the job with the given ID, or None if not found."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, session_id: Optional[str] = None) -> List[Job]:
        """Return all jobs, optionally filtered by session_id."""
        with self._lock:
            jobs = list(self._jobs.values())
        if session_id is not None:
            jobs = [j for j in jobs if j.session_id == session_id]
        return jobs

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_active_jobs(self, session_id: str) -> bool:
        """Return True if the session has any PENDING or RUNNING jobs."""
        with self._lock:
            return any(
                j.status in _ACTIVE_STATUSES
                for j in self._jobs.values()
                if j.session_id == session_id
            )

    def prune(self) -> int:
        """Remove completed/failed/cancelled jobs older than retention_seconds.

        Returns the number of jobs removed.
        """
        now = time.time()
        cutoff = now - self._retention_seconds
        terminal_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

        with self._lock:
            to_delete = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in terminal_statuses
                and job.completed_at is not None
                and job.completed_at < cutoff
            ]
            for job_id in to_delete:
                del self._jobs[job_id]

        if to_delete:
            logger.debug("Pruned %d expired jobs", len(to_delete))
        return len(to_delete)
