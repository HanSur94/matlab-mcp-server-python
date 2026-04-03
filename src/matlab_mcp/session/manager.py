"""Session manager for MATLAB MCP Server.

Manages the lifecycle of user sessions, each of which owns a temporary
directory and a set of associated jobs.
"""
from __future__ import annotations

import logging
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_SESSION_ID = "default"

# Allow only safe characters in session IDs to prevent filesystem path traversal.
# UUIDs, simple identifiers, and "default" all match this pattern.
_SAFE_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-\.]{1,128}$')


def _sanitize_session_id(session_id: str) -> str:
    """Validate session_id is safe for use as a filesystem path component.

    Parameters
    ----------
    session_id:
        The session identifier to validate.

    Returns
    -------
    str
        The unchanged session_id if it passes validation.

    Raises
    ------
    ValueError
        If session_id contains unsafe characters, slashes, is empty, or
        exceeds 128 characters.
    """
    if not _SAFE_SESSION_ID_RE.match(session_id):
        raise ValueError(f"Invalid session_id: {session_id!r}")
    return session_id


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
            base_temp = str(Path(tempfile.gettempdir()) / "matlab_mcp")

        self._base_temp = Path(base_temp)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(self, *, session_id: Optional[str] = None) -> Session:
        """Create a new session with a temporary directory.

        Parameters
        ----------
        session_id
            Optional explicit ID for the session.  When *None* (the default),
            a random UUID is generated.

        Raises
        ------
        RuntimeError
            If the maximum number of sessions has been reached.
        """
        with self._lock:
            if len(self._sessions) >= self._max_sessions:
                raise RuntimeError(
                    f"Maximum number of sessions reached ({self._max_sessions})"
                )

            # Generate a UUID when no session_id is provided (None), but pass
            # explicit empty or invalid strings through to _sanitize_session_id
            # so they are rejected with a clear error message.
            effective_id = str(uuid.uuid4()) if session_id is None else session_id
            session_id = _sanitize_session_id(effective_id)
            temp_dir = self._base_temp / session_id

            # Defense-in-depth: verify resolved path stays under base directory
            resolved = temp_dir.resolve()
            base_resolved = self._base_temp.resolve()
            if not str(resolved).startswith(str(base_resolved)):
                raise ValueError(f"Session path escapes base directory: {session_id!r}")

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
        with self._lock:
            return self._sessions.get(session_id)

    def get_or_create_default(self) -> Session:
        """Return (or create) the default session for single-user stdio mode."""
        with self._lock:
            session = self._sessions.get(_DEFAULT_SESSION_ID)
            if session is not None:
                return session
        return self.create_session(session_id=_DEFAULT_SESSION_ID)

    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session and remove its temporary directory.

        Returns True if the session existed and was destroyed, False otherwise.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
            remaining = len(self._sessions)
        if session is None:
            return False

        idle_s = session.idle_seconds
        logger.info("Destroying session %s (idle=%.0fs, remaining=%d)",
                     session_id[:8], idle_s, remaining)

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
        # Collect idle candidates under lock, then check external callback outside
        # to avoid holding self._lock while calling into JobTracker.
        with self._lock:
            candidates = [
                sid for sid, s in self._sessions.items()
                if s.idle_seconds >= self._session_timeout
            ]

        to_destroy = []
        for session_id in candidates:
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
        with self._lock:
            return len(self._sessions)
