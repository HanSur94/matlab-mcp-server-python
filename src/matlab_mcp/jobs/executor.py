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
import io
import logging
import os
from pathlib import Path
from typing import Any, Optional

from matlab_mcp.jobs.models import Job
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
        logger.info("[job %s] Created for session=%s  code=%s",
                    job.job_id[:8], session_id[:8], repr(code[:120]))

        # 2. Acquire engine
        engine = await self._pool.acquire()
        job.mark_running(engine.engine_id)
        logger.info("[job %s] Acquired engine %s — executing", job.job_id[:8], engine.engine_id)

        # 3. Inject job context
        self._inject_job_context(engine, job, temp_dir)

        # 4. Start background execution with stdout/stderr capture
        job._stdout = io.StringIO()
        job._stderr = io.StringIO()
        try:
            future = engine.execute(code, background=True,
                                    stdout=job._stdout, stderr=job._stderr)
            job.future = future
        except Exception as exc:
            logger.error("[job %s] Failed to start execution: %s: %s",
                         job.job_id[:8], type(exc).__name__, exc)
            job.mark_failed(
                error_type=type(exc).__name__,
                message=str(exc),
            )
            await self._pool.release(engine)
            if self._collector:
                self._collector.record_event("job_failed", {
                    "job_id": job.job_id,
                    "code": code[:500],
                    "error": str(exc)[:500],
                })
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
                elapsed_ms = (job.completed_at - job.started_at) * 1000 if job.started_at and job.completed_at else 0
                output_preview = (result.get("text") or "")[:200]
                logger.info("[job %s] Completed in %.1fms  output=%s",
                            job.job_id[:8], elapsed_ms, repr(output_preview))
                await self._pool.release(engine)
                if self._collector:
                    self._collector.record_event("job_completed", {
                        "job_id": job.job_id,
                        "execution_ms": elapsed_ms,
                        "code": code[:500],
                        "output": (result.get("text") or "")[:2000],
                    })
                return {"status": "completed", "job_id": job.job_id, **result}
            except (TimeoutError, concurrent.futures.TimeoutError, asyncio.TimeoutError):
                # Promote to async
                logger.info("[job %s] Sync timeout (%ds) — promoting to async background job",
                            job.job_id[:8], sync_timeout)
                asyncio.create_task(
                    self._wait_for_completion(job, engine, future, temp_dir)
                )
                return {"status": "pending", "job_id": job.job_id}
            except Exception as exc:
                logger.error("[job %s] Execution failed: %s: %s",
                             job.job_id[:8], type(exc).__name__, exc)
                job.mark_failed(
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
                await self._pool.release(engine)
                if self._collector:
                    self._collector.record_event("job_failed", {
                        "job_id": job.job_id,
                        "code": code[:500],
                        "error": str(exc)[:500],
                    })
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
        """Inject job metadata into the MATLAB workspace.

        Sets ``__mcp_job_id__`` and optionally ``__mcp_temp_dir__`` as
        workspace variables so that MATLAB scripts can reference them.
        Failures are silently logged at DEBUG level.
        """
        try:
            engine._engine.workspace["__mcp_job_id__"] = job.job_id
        except Exception:
            logger.debug("Could not inject __mcp_job_id__ into workspace")

        if temp_dir is not None:
            try:
                engine._engine.workspace["__mcp_temp_dir__"] = str(temp_dir)
            except Exception:
                logger.debug("Could not inject __mcp_temp_dir__ into workspace")

    async def _wait_for_completion(
        self,
        job: Job,
        engine: Any,
        future: Any,
        temp_dir: Optional[str],
    ) -> None:
        """Background task that waits for an async job to complete.

        Blocks (in a thread executor) until the MATLAB future resolves
        or ``max_execution_time`` is exceeded.  On completion the job is
        marked completed or failed, and the engine is released back to
        the pool regardless of outcome.
        """
        max_time = self._config.execution.max_execution_time
        loop = asyncio.get_running_loop()
        try:
            raw_result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: future.result(timeout=max_time)),
                timeout=max_time + 1,
            )
            result = self._build_result(engine, raw_result, job, temp_dir)
            job.mark_completed(result)
            elapsed_ms = (job.completed_at - job.started_at) * 1000 if job.started_at and job.completed_at else 0
            logger.info("[job %s] Async job completed in %.1fms", job.job_id[:8], elapsed_ms)
            if self._collector:
                self._collector.record_event("job_completed", {
                    "job_id": job.job_id,
                    "execution_ms": elapsed_ms,
                    "code": job.code[:500] if job.code else "",
                    "output": (result.get("text") or "")[:2000],
                })
        except asyncio.CancelledError:
            logger.warning("[job %s] Async job cancelled", job.job_id[:8])
            job.mark_cancelled()
        except Exception as exc:
            logger.error("[job %s] Async job failed: %s: %s",
                         job.job_id[:8], type(exc).__name__, exc)
            job.mark_failed(
                error_type=type(exc).__name__,
                message=str(exc),
            )
            if self._collector:
                self._collector.record_event("job_failed", {
                    "job_id": job.job_id,
                    "code": job.code[:500] if job.code else "",
                    "error": str(exc)[:500],
                })
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
        # Capture text output from StringIO buffers
        text = ""
        try:
            stdout_buf = getattr(job, "_stdout", None)
            if stdout_buf is not None:
                text = stdout_buf.getvalue()
            stderr_buf = getattr(job, "_stderr", None)
            if stderr_buf is not None:
                err_text = stderr_buf.getvalue()
                if err_text:
                    text = text + "\n[stderr]\n" + err_text if text else err_text
        except Exception:
            pass

        # Capture workspace variables (excluding internal MCP variables)
        variables: dict = {}
        try:
            for k, v in engine._engine.workspace.items():
                if not k.startswith("__mcp_"):
                    variables[k] = self._safe_serialize(v)
        except Exception:
            pass

        # Figures — extract properties and convert to Plotly
        figures: list = []
        if self._config.output.plotly_conversion and temp_dir is not None:
            try:
                import glob as glob_mod
                from matlab_mcp.output.plotly_convert import load_plotly_json
                from matlab_mcp.output.plotly_style_mapper import convert_figure

                # Run MATLAB-side figure extraction
                # Note: MATLAB eval() rejects identifiers starting with __
                escaped_dir = str(temp_dir).replace("\\", "\\\\").replace("'", "''")
                extract_code = (
                    f"mcpFigs_ = findobj(0, 'Type', 'figure'); "
                    f"for mcpIdx_ = 1:length(mcpFigs_), "
                    f"mcp_extract_props(mcpFigs_(mcpIdx_), "
                    f"fullfile('{escaped_dir}', sprintf('{job.job_id}_fig%d.json', mcpIdx_))); "
                    f"close(mcpFigs_(mcpIdx_)); "
                    f"end; "
                    f"clear mcpFigs_ mcpIdx_;"
                )
                logger.debug("Figure extraction code: %r", extract_code)
                try:
                    engine.execute(extract_code, background=False)
                except Exception as exc:
                    logger.warning("Figure extraction failed: %s", exc)
                    logger.debug("Extraction code was: %r", extract_code)

                # Load and convert each figure JSON
                fig_pattern = os.path.join(temp_dir, f"{job.job_id}_fig*.json")
                for fig_file in sorted(glob_mod.glob(fig_pattern)):
                    matlab_data = load_plotly_json(fig_file)
                    if matlab_data:
                        plotly_fig = convert_figure(matlab_data)
                        figures.append(plotly_fig)
                    try:
                        os.remove(fig_file)
                    except OSError:
                        pass
            except Exception as exc:
                logger.warning("Figure conversion pipeline failed: %s", exc)

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
    def _safe_serialize(value: Any) -> Any:
        """Convert a MATLAB workspace value to a JSON-serializable Python type.

        Handles primitives, nested lists/dicts, numpy arrays/scalars,
        and MATLAB array types.  Falls back to ``repr()`` for unknown types.
        """
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (list, tuple)):
            return [JobExecutor._safe_serialize(v) for v in value]
        if isinstance(value, dict):
            return {k: JobExecutor._safe_serialize(v) for k, v in value.items()}
        # numpy arrays
        try:
            import numpy as np
            if isinstance(value, np.ndarray):
                return value.tolist()
            if isinstance(value, (np.integer, np.floating)):
                return value.item()
        except ImportError:
            pass
        # MATLAB arrays / matrices
        try:
            if hasattr(value, '_data'):
                return list(value._data)
            if hasattr(value, 'tolist'):
                return value.tolist()
        except Exception:
            pass
        # Fallback: repr
        return repr(value)

    @staticmethod
    def _error_result(job: Job) -> dict:
        """Return a failure result dict from a failed job."""
        return {
            "status": "failed",
            "job_id": job.job_id,
            "error": job.error,
        }
