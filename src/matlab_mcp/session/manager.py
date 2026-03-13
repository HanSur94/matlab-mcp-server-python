"""Session manager for MATLAB MCP Server.

Manages the lifecycle of user sessions, each of which owns a temporary
directory and a set of associated jobs.
"""
from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_ID = "default"


@dataclass
class Session:
    """Represents a single user session.

    Parameters
    ----------
    session_id:
        Unique identifier for this session.
    temp_dir:
        Path to the session's temporary working directory.
    """

    session_id: str
    temp_dir: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def touch(self) -> None:
        """Update last_active to the current time."""
        self.last_active = time.time()

    @property
    def idle_seconds(self) -> float:
        """Seconds since the session was last active."""
        return time.time() - self.last_active


class SessionManager:
    """Manages the lifecycle of user sessions.

    Parameters
    ----------
    config:
        The full :class:`~matlab_mcp.config.AppConfig` instance.
    """

    def __init__(self, config: Any = None, collector: Any = None) -> None:
        self._config = config
        self._collector = collector
        self._sessions: Dict[str, Session] = {}

        # Derive limits from config or use sensible defaults
        if config is not None:
            self._max_sessions: int = config.sessions.max_sessions
            self._session_timeout: int = config.sessions.session_timeout
            base_temp: str = config.execution.temp_dir
        else:
            self._max_sessions = 50
            self._session_timeout = 3600
            base_temp = "/tmp/matlab_mcp"

        self._base_temp = Path(base_temp)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(self) -> Session:
        """Create a new session with a unique ID and a temporary directory.

        Raises
        ------
        RuntimeError
            If the maximum number of sessions has been reached.
        """
        if len(self._sessions) >= self._max_sessions:
            raise RuntimeError(
                f"Maximum number of sessions reached ({self._max_sessions})"
            )

        session_id = str(uuid.uuid4())
        temp_dir = self._base_temp / session_id
        temp_dir.mkdir(parents=True, exist_ok=True)

        session = Session(session_id=session_id, temp_dir=str(temp_dir))
        self._sessions[session_id] = session
        logger.info("Session created: %s (temp_dir=%s, total=%d/%d)",
                     session_id[:8], temp_dir, len(self._sessions), self._max_sessions)
        if self._collector:
            self._collector.record_event("session_created", {"session_id_short": session.session_id[-8:]})
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return the session with the given ID, or None if not found."""
        return self._sessions.get(session_id)

    def get_or_create_default(self) -> Session:
        """Return (or create) the default session for single-user stdio mode."""
        session = self._sessions.get(_DEFAULT_SESSION_ID)
        if session is not None:
            return session

        # Create with a fixed ID
        temp_dir = self._base_temp / _DEFAULT_SESSION_ID
        temp_dir.mkdir(parents=True, exist_ok=True)

        session = Session(session_id=_DEFAULT_SESSION_ID, temp_dir=str(temp_dir))
        self._sessions[_DEFAULT_SESSION_ID] = session
        logger.info("Default session created (temp_dir=%s)", temp_dir)
        if self._collector:
            self._collector.record_event("session_created", {"session_id_short": session.session_id[-8:]})
        return session

    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session and remove its temporary directory.

        Returns True if the session existed and was destroyed, False otherwise.
        """
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False

        idle_s = session.idle_seconds
        logger.info("Destroying session %s (idle=%.0fs, remaining=%d)",
                     session_id[:8], idle_s, len(self._sessions))

        # Clean up temp directory
        temp_path = Path(session.temp_dir)
        if temp_path.exists():
            try:
                shutil.rmtree(temp_path)
                logger.info("Removed temp dir %s for session %s", temp_path, session_id[:8])
            except Exception:
                logger.warning(
                    "Failed to remove temp dir %s for session %s",
                    temp_path,
                    session_id[:8],
                )
        return True

    def cleanup_expired(
        self,
        has_active_jobs_fn: Optional[Callable[[str], bool]] = None,
    ) -> int:
        """Remove sessions that have been idle beyond the session timeout.

        Sessions with active jobs are skipped.

        Parameters
        ----------
        has_active_jobs_fn:
            A callable that takes a session_id and returns True if the session
            has active (PENDING or RUNNING) jobs.  If None, all idle sessions
            are eligible for removal.

        Returns
        -------
        int
            The number of sessions removed.
        """
        to_destroy = []
        for session_id, session in list(self._sessions.items()):
            if session.idle_seconds < self._session_timeout:
                continue
            if has_active_jobs_fn is not None and has_active_jobs_fn(session_id):
                logger.debug(
                    "Skipping cleanup of session %s — has active jobs", session_id
                )
                continue
            to_destroy.append(session_id)

        for session_id in to_destroy:
            self.destroy_session(session_id)

        if to_destroy:
            logger.info("Cleaned up %d expired sessions", len(to_destroy))
        return len(to_destroy)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_count(self) -> int:
        """Current number of active sessions."""
        return len(self._sessions)
