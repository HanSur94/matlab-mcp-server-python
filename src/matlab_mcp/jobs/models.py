"""Job models for MATLAB MCP Server.

Defines the Job data model and JobStatus enum used to track the lifecycle
of MATLAB code execution requests.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Lifecycle status of a MATLAB execution job.

    Terminal statuses: COMPLETED, FAILED, CANCELLED.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions for each status.
# Terminal states (COMPLETED, FAILED, CANCELLED) have no allowed successors.
_VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.RUNNING, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}


@dataclass
class Job:
    """Represents a single MATLAB code execution job.

    Parameters
    ----------
    session_id:
        ID of the session that owns this job.
    code:
        MATLAB code to execute.

    Attributes
    ----------
    job_id:
        Auto-generated unique identifier (``j-<uuid>``).
    status:
        Current lifecycle status; starts as PENDING.
    engine_id:
        ID of the engine executing this job (set when RUNNING).
    result:
        Structured result dict populated on completion.
    error:
        Error details dict populated on failure.
    created_at:
        Epoch timestamp when the job was created.
    started_at:
        Epoch timestamp when execution began.
    completed_at:
        Epoch timestamp when the job reached a terminal state.
    future:
        Handle to the background MATLAB future, if applicable.
    """

    session_id: str
    code: str
    job_id: str = field(default_factory=lambda: f"j-{uuid.uuid4()}")
    status: JobStatus = field(default=JobStatus.PENDING)
    engine_id: Optional[str] = field(default=None)
    result: Optional[Any] = field(default=None)
    error: Optional[dict] = field(default=None)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = field(default=None)
    completed_at: Optional[float] = field(default=None)
    future: Optional[Any] = field(default=None)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _transition_to(self, new_status: JobStatus) -> bool:
        """Attempt a state transition. Returns True if allowed, False if no-op.

        Parameters
        ----------
        new_status:
            The target status to transition to.

        Returns
        -------
        bool
            True when the transition was applied; False when it is not valid
            from the current state (e.g. cancel on an already-completed job).
        """
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            logger.debug(
                "[%s] Ignoring transition %s -> %s (not allowed)",
                self.job_id[:8], self.status.name, new_status.name,
            )
            return False
        self.status = new_status
        return True

    def mark_running(self, engine_id: str) -> None:
        """Transition job to RUNNING state."""
        if not self._transition_to(JobStatus.RUNNING):
            return
        self.engine_id = engine_id
        self.started_at = time.time()

    def mark_completed(self, result: Any) -> None:
        """Transition job to COMPLETED state with a result."""
        if not self._transition_to(JobStatus.COMPLETED):
            return
        self.result = result
        self.completed_at = time.time()

    def mark_failed(
        self,
        error_type: str,
        message: str,
        matlab_id: Optional[str] = None,
        stack_trace: Optional[str] = None,
    ) -> None:
        """Transition job to FAILED state with error details."""
        if not self._transition_to(JobStatus.FAILED):
            return
        self.error = {
            "type": error_type,
            "message": message,
            "matlab_id": matlab_id,
            "stack_trace": stack_trace,
        }
        self.completed_at = time.time()

    def mark_cancelled(self) -> None:
        """Transition job to CANCELLED state."""
        if not self._transition_to(JobStatus.CANCELLED):
            return
        self.completed_at = time.time()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def elapsed_seconds(self) -> Optional[float]:
        """Elapsed time in seconds since job started, or None if not started."""
        if self.started_at is None:
            return None
        end = self.completed_at if self.completed_at is not None else time.time()
        return end - self.started_at
