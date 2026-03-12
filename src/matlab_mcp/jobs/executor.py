"""Job executor for MATLAB MCP Server.

Orchestrates the full lifecycle of a MATLAB code execution request:
1. Create a job in the tracker
2. Acquire an engine from the pool
3. Inject job context into the MATLAB workspace
4. Execute code (sync or promoted to async)
5. Build and return a structured result dict
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes MATLAB code jobs using a pool of engines.

    Parameters
    ----------
    pool:
        An :class:`~matlab_mcp.pool.manager.EnginePoolManager` instance
        (or any object with async ``acquire()`` / ``release()`` methods).
    tracker:
        A :class:`JobTracker` instance for storing job state.
    config:
        The full :class:`~matlab_mcp.config.AppConfig` instance.
    """

    def __init__(self, pool: Any, tracker: JobTracker, config: Any, collector: Any = None) -> None:
        self._pool = pool
        self._tracker = tracker
        self._config = config
        self._collector = collector

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        session_id: str,
        code: str,
        temp_dir: Optional[str] = None,
    ) -> dict:
        """Execute MATLAB code for a session.

        Hybrid sync/async execution:
        - Creates a job and acquires an engine.
        - Injects job context into the MATLAB workspace.
        - Starts background execution via ``engine.execute(code, background=True)``.
        - Waits up to ``sync_timeout`` seconds.
          - If the future completes: returns result inline (status="completed").
          - If it times out: promotes to async background task (status="pending").
        - On sync execution error: marks job failed and returns error result.

        Returns a dict with at minimum ``status`` and ``job_id`` keys.
        """
        sync_timeout = self._config.execution.sync_timeout

        # 1. Create job
        job = self._tracker.create_job(session_id, code)

        # 2. Acquire engine
        engine = await self._pool.acquire()
        job.mark_running(engine.engine_id)

        # 3. Inject job context
        self._inject_job_context(engine, job, temp_dir)

        # 4. Start background execution
        try:
            future = engine.execute(code, background=True)
            job.future = future
        except Exception as exc:
            job.mark_failed(
                error_type=type(exc).__name__,
                message=str(exc),
            )
            await self._pool.release(engine)
            if self._collector:
                self._collector.record_event("job_failed", {"job_id": job.job_id, "error": str(exc)[:200]})
            return self._error_result(job)

        # 5. Wait for sync_timeout
        if sync_timeout > 0:
            try:
                loop = asyncio.get_running_loop()
                raw_result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: future.result(timeout=sync_timeout)),
                    timeout=sync_timeout + 1,
                )
                # Completed within timeout
                result = self._build_result(engine, raw_result, job, temp_dir)
                job.mark_completed(result)
                await self._pool.release(engine)
                if self._collector:
                    elapsed_ms = (job.completed_at - job.started_at) * 1000 if job.started_at and job.completed_at else 0
                    self._collector.record_event("job_completed", {"job_id": job.job_id, "execution_ms": elapsed_ms})
                return {"status": "completed", "job_id": job.job_id, **result}
            except (TimeoutError, concurrent.futures.TimeoutError, asyncio.TimeoutError):
                # Promote to async
                asyncio.create_task(
                    self._wait_for_completion(job, engine, future, temp_dir)
                )
                return {"status": "pending", "job_id": job.job_id}
            except Exception as exc:
                job.mark_failed(
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                await self._pool.release(engine)
                if self._collector:
                    self._collector.record_event("job_failed", {"job_id": job.job_id, "error": str(exc)[:200]})
                return self._error_result(job)
        else:
            # sync_timeout == 0: immediately promote to async
            asyncio.create_task(
                self._wait_for_completion(job, engine, future, temp_dir)
            )
            return {"status": "pending", "job_id": job.job_id}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _inject_job_context(
        self,
        engine: Any,
        job: Job,
        temp_dir: Optional[str],
    ) -> None:
        """Inject job metadata into the MATLAB workspace."""
        try:
            engine._engine.workspace["__mcp_job_id__"] = job.job_id
        except Exception:
            logger.debug("Could not inject __mcp_job_id__ into workspace")

        if temp_dir is not None:
            try:
                os.environ["MCP_TEMP_DIR"] = str(temp_dir)
            except Exception:
                logger.debug("Could not set MCP_TEMP_DIR env var")

    async def _wait_for_completion(
        self,
        job: Job,
        engine: Any,
        future: Any,
        temp_dir: Optional[str],
    ) -> None:
        """Background task that waits for an async job to complete."""
        max_time = self._config.execution.max_execution_time
        loop = asyncio.get_running_loop()
        try:
            raw_result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: future.result(timeout=max_time)),
                timeout=max_time + 1,
            )
            result = self._build_result(engine, raw_result, job, temp_dir)
            job.mark_completed(result)
            if self._collector:
                elapsed_ms = (job.completed_at - job.started_at) * 1000 if job.started_at and job.completed_at else 0
                self._collector.record_event("job_completed", {"job_id": job.job_id, "execution_ms": elapsed_ms})
        except asyncio.CancelledError:
            job.mark_cancelled()
        except Exception as exc:
            job.mark_failed(
                error_type=type(exc).__name__,
                message=str(exc),
            )
            if self._collector:
                self._collector.record_event("job_failed", {"job_id": job.job_id, "error": str(exc)[:200]})
        finally:
            try:
                await self._pool.release(engine)
            except Exception:
                logger.warning("Failed to release engine after async job %s", job.job_id)

    def _build_result(
        self,
        engine: Any,
        raw_result: Any,
        job: Job,
        temp_dir: Optional[str],
    ) -> dict:
        """Build a structured result dict from the engine's output.

        Collects:
        - text: captured stdout from the engine
        - variables: key/value pairs from the workspace (excluding internal vars)
        - figures: Plotly-converted figures if configured
        - files: any files written to temp_dir
        - warnings / errors: empty lists by default (extended by real engine)
        """
        # Capture text output
        text = ""
        try:
            text = getattr(engine._engine, "last_output", "") or ""
        except Exception:
            pass

        # Capture workspace variables (excluding internal MCP variables)
        variables: dict = {}
        try:
            for k, v in engine._engine.workspace.items():
                if not k.startswith("__mcp_"):
                    variables[k] = v
        except Exception:
            pass

        # Figures (placeholder — Plotly conversion would go here)
        figures: list = []
        if self._config.output.plotly_conversion:
            # Real implementation would scan for figure handles
            pass

        # Files in temp_dir
        files: list = []
        if temp_dir is not None:
            try:
                td = Path(temp_dir)
                if td.exists():
                    files = [str(p) for p in td.iterdir() if p.is_file()]
            except Exception:
                pass

        return {
            "text": text,
            "variables": variables,
            "figures": figures,
            "files": files,
            "warnings": [],
            "errors": [],
        }

    @staticmethod
    def _error_result(job: Job) -> dict:
        """Return a failure result dict from a failed job."""
        return {
            "status": "failed",
            "job_id": job.job_id,
            "error": job.error,
        }
