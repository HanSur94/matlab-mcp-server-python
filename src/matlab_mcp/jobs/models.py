"""Job models for MATLAB MCP Server.

Defines the Job data model and JobStatus enum used to track the lifecycle
of MATLAB code execution requests.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobStatus(Enum):
    """Lifecycle status of a MATLAB execution job.

    Terminal statuses: COMPLETED, FAILED, CANCELLED.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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

    def mark_running(self, engine_id: str) -> None:
        """Transition job to RUNNING state."""
        self.status = JobStatus.RUNNING
        self.engine_id = engine_id
        self.started_at = time.time()

    def mark_completed(self, result: Any) -> None:
        """Transition job to COMPLETED state with a result."""
        self.status = JobStatus.COMPLETED
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
        self.status = JobStatus.FAILED
        self.error = {
            "type": error_type,
            "message": message,
            "matlab_id": matlab_id,
            "stack_trace": stack_trace,
        }
        self.completed_at = time.time()

    def mark_cancelled(self) -> None:
        """Transition job to CANCELLED state."""
        self.status = JobStatus.CANCELLED
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
