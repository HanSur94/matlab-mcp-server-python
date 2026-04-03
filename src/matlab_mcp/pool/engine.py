"""MATLAB engine wrapper with lifecycle management.

Wraps a single matlab.engine instance with state tracking, health checks,
and workspace reset capabilities. Uses lazy import so tests can mock the
matlab.engine module.
"""
from __future__ import annotations

import importlib
import logging
import time
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class EngineState(Enum):
    """Possible lifecycle states of a MATLAB engine wrapper.

    States follow the progression: STOPPED -> STARTING -> IDLE <-> BUSY.
    """

    STOPPED = auto()
    STARTING = auto()
    IDLE = auto()
    BUSY = auto()


class MatlabEngineWrapper:
    """Wraps a single MATLAB engine instance.

    Parameters
    ----------
    engine_id:
        Unique identifier for this engine (e.g., ``"engine-0"``).
    pool_config:
        ``PoolConfig`` instance (used for matlab_root if needed).
    workspace_config:
        ``WorkspaceConfig`` instance with default_paths and startup_commands.
    """

    def __init__(self, engine_id: str, pool_config: Any, workspace_config: Any) -> None:
        self.engine_id = engine_id
        self._pool_config = pool_config
        self._workspace_config = workspace_config

        self._engine: Any = None
        self._state: EngineState = EngineState.STOPPED
        self._idle_since: float = time.monotonic()
        # Set by release() when reset_workspace() fails; health check retires this engine.
        self._needs_replacement: bool = False

    # ------------------------------------------------------------------
    # State properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> EngineState:
        """Current lifecycle state of the engine."""
        return self._state

    @property
    def idle_seconds(self) -> float:
        """Seconds since the engine last became idle (0 if not idle)."""
        if self._state == EngineState.IDLE:
            return time.monotonic() - self._idle_since
        return 0.0

    @property
    def is_alive(self) -> bool:
        """True if the underlying engine object exists and reports alive."""
        if self._engine is None:
            return False
        alive_attr = getattr(self._engine, "is_alive", None)
        if alive_attr is None:
            # Real matlab.engine doesn't have is_alive — assume alive
            return True
        if callable(alive_attr):
            return bool(alive_attr())
        return bool(alive_attr)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _get_matlab_engine_module(self) -> Any:
        """Lazily import matlab.engine so tests can mock it."""
        return importlib.import_module("matlab.engine")

    def start(self) -> None:
        """Start the MATLAB engine and apply default paths and startup commands."""
        logger.info("[%s] Starting MATLAB engine", self.engine_id)
        self._state = EngineState.STARTING

        matlab_engine = self._get_matlab_engine_module()
        self._engine = matlab_engine.start_matlab()

        # Apply default workspace paths
        for path in self._workspace_config.default_paths:
            try:
                self._engine.addpath(path)
            except Exception:
                logger.warning("[%s] Failed to addpath: %s", self.engine_id, path)

        # Run startup commands
        for cmd in self._workspace_config.startup_commands:
            try:
                self._engine.eval(cmd, nargout=0)
            except Exception:
                logger.warning("[%s] Startup command failed: %s", self.engine_id, cmd)

        self._state = EngineState.IDLE
        self._idle_since = time.monotonic()
        logger.info("[%s] MATLAB engine started", self.engine_id)

    def stop(self) -> None:
        """Quit the MATLAB engine."""
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                logger.warning("[%s] Exception during engine quit", self.engine_id)
            finally:
                self._engine = None
        self._state = EngineState.STOPPED
        logger.info("[%s] MATLAB engine stopped", self.engine_id)

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def health_check(self) -> bool:
        """Run a trivial eval to confirm the engine is responsive."""
        if self._engine is None:
            return False
        try:
            self._engine.eval("1", nargout=0)
            return True
        except Exception:
            return False

    def execute(self, code: str, nargout: int = 0, background: bool = False,
                stdout: Any = None, stderr: Any = None) -> Any:
        """Run MATLAB code on the engine.

        Parameters
        ----------
        code:       MATLAB code to evaluate.
        nargout:    Number of output arguments expected.
        background: If True, return a future-like object immediately.
        stdout:     Stream to capture standard output (e.g. ``io.StringIO``).
        stderr:     Stream to capture standard error (e.g. ``io.StringIO``).
        """
        if self._engine is None:
            raise RuntimeError(f"[{self.engine_id}] Engine is not started")
        kwargs: dict[str, Any] = {"nargout": nargout, "background": background}
        if stdout is not None:
            kwargs["stdout"] = stdout
        if stderr is not None:
            kwargs["stderr"] = stderr
        return self._engine.eval(code, **kwargs)

    def reset_workspace(self) -> None:
        """Reset the MATLAB workspace to a clean state.

        Sequence: clear all, clear global, clear functions, fclose all,
        restoredefaultpath, re-add configured paths, re-run startup commands.
        """
        if self._engine is None:
            raise RuntimeError(f"[{self.engine_id}] Engine is not started")

        cleanup_commands = [
            "clear all",
            "clear global",
            "clear functions",
            "fclose all",
        ]
        for cmd in cleanup_commands:
            try:
                self._engine.eval(cmd, nargout=0)
            except Exception:
                logger.warning("[%s] Reset command failed: %s", self.engine_id, cmd)

        try:
            self._engine.restoredefaultpath()
        except Exception:
            logger.warning("[%s] restoredefaultpath failed", self.engine_id)

        # Re-apply configured paths
        for path in self._workspace_config.default_paths:
            try:
                self._engine.addpath(path)
            except Exception:
                logger.warning("[%s] Re-addpath failed: %s", self.engine_id, path)

        # Re-run startup commands
        for cmd in self._workspace_config.startup_commands:
            try:
                self._engine.eval(cmd, nargout=0)
            except Exception:
                logger.warning("[%s] Startup command failed on reset: %s", self.engine_id, cmd)

        logger.debug("[%s] Workspace reset complete", self.engine_id)

    def set_workspace_var(self, name: str, value: Any) -> None:
        """Set a variable in the MATLAB workspace via the engine API.

        Parameters
        ----------
        name:
            MATLAB variable name.
        value:
            Python value to assign; must be compatible with the MATLAB Engine API.

        Raises
        ------
        RuntimeError
            If the engine has not been started.
        """
        if self._engine is None:
            raise RuntimeError(f"[{self.engine_id}] Engine is not started")
        self._engine.workspace[name] = value

    def get_workspace_vars(self) -> Any:
        """Return the workspace proxy object for reading variables.

        Returns
        -------
        Any
            The matlab.engine workspace proxy; supports ``__getitem__`` and
            ``__contains__`` so callers can read variables by name.

        Raises
        ------
        RuntimeError
            If the engine has not been started.
        """
        if self._engine is None:
            raise RuntimeError(f"[{self.engine_id}] Engine is not started")
        return self._engine.workspace

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def mark_busy(self) -> None:
        """Transition engine to BUSY state."""
        self._state = EngineState.BUSY

    def mark_idle(self) -> None:
        """Transition engine to IDLE state and record timestamp."""
        self._state = EngineState.IDLE
        self._idle_since = time.monotonic()

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover
        return f"MatlabEngineWrapper(id={self.engine_id!r}, state={self._state.name})"
