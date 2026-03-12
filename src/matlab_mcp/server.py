"""Main MCP Server entry point for MATLAB MCP Server.

Ties together all components (pool, tracker, executor, sessions, security,
formatter, custom tools) and exposes them as FastMCP tools.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.server.context import Context

from matlab_mcp.config import AppConfig, load_config
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.models import JobStatus
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.output.formatter import ResultFormatter
from matlab_mcp.pool.manager import EnginePoolManager
from matlab_mcp.security.validator import SecurityValidator
from matlab_mcp.session.manager import SessionManager
from matlab_mcp.tools.admin import get_pool_status_impl
from matlab_mcp.tools.core import (
    check_code_impl,
    execute_code_impl,
    get_workspace_impl,
)
from matlab_mcp.tools.custom import load_custom_tools, make_custom_tool_handler
from matlab_mcp.tools.discovery import (
    get_help_impl,
    list_functions_impl,
    list_toolboxes_impl,
)
from matlab_mcp.tools.files import delete_file_impl, list_files_impl, upload_data_impl
from matlab_mcp.tools.jobs import (
    cancel_job_impl,
    get_job_result_impl,
    get_job_status_impl,
    list_jobs_impl,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server state container
# ---------------------------------------------------------------------------


class MatlabMCPServer:
    """Holds all server-level state.

    Parameters
    ----------
    config:
        The full ``AppConfig`` instance.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pool = EnginePoolManager(config)
        self.tracker = JobTracker(
            retention_seconds=config.sessions.job_retention_seconds
        )
        self.executor = JobExecutor(
            pool=self.pool,
            tracker=self.tracker,
            config=config,
        )
        self.sessions = SessionManager(config)
        self.security = SecurityValidator(config.security)
        self.formatter = ResultFormatter(config)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _get_session_id(self, ctx: Context) -> str:
        """Return session ID for the current request.

        For stdio transport a fixed ``"default"`` ID is used.
        For SSE transport the context's ``session_id`` is used.
        """
        transport = self.config.server.transport
        if transport == "sse":
            try:
                sid = ctx.session_id
                if sid:
                    return sid
            except Exception:
                pass
        # stdio or fallback
        session = self.sessions.get_or_create_default()
        return session.session_id

    def _get_temp_dir(self, session_id: str) -> str:
        """Return the temporary directory for *session_id*.

        Creates the session if it does not exist yet.
        """
        session = self.sessions.get_session(session_id)
        if session is None:
            # Create session with fixed ID for SSE clients
            session = self.sessions.get_or_create_default()
        return session.temp_dir


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server(config: AppConfig) -> FastMCP:
    """Create and configure the FastMCP server instance.

    Parameters
    ----------
    config:
        Application configuration.

    Returns
    -------
    FastMCP
        Configured server ready to run.
    """
    state = MatlabMCPServer(config)

    # ------------------------------------------------------------------
    # Lifespan
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def lifespan(mcp: FastMCP):  # type: ignore[type-arg]
        # Security warning for SSE without proxy auth
        if (
            config.server.transport == "sse"
            and not config.security.require_proxy_auth
        ):
            logger.warning(
                "SSE transport enabled without require_proxy_auth=true. "
                "Ensure the server is behind an authenticating reverse proxy."
            )

        # Create necessary directories
        result_dir = Path(config.server.result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = Path(config.execution.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        log_dir = Path(config.server.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # Add matlab_helpers to workspace paths so MATLAB can find helper functions
        helpers_dir = str(Path(__file__).parent / "matlab_helpers")
        if helpers_dir not in config.workspace.default_paths:
            config.workspace.default_paths.insert(0, helpers_dir)

        # Start engine pool
        logger.info("Starting MATLAB engine pool...")
        await state.pool.start()
        logger.info("MATLAB engine pool started")

        # Background task: periodic health checks
        async def health_check_loop() -> None:
            interval = config.pool.health_check_interval
            while True:
                try:
                    await asyncio.sleep(interval)
                    await state.pool.run_health_checks()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Health check error: %s", exc)

        # Background task: session + job cleanup
        async def cleanup_loop() -> None:
            while True:
                try:
                    await asyncio.sleep(60)
                    state.sessions.cleanup_expired(
                        has_active_jobs_fn=state.tracker.has_active_jobs
                    )
                    state.tracker.prune()
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Cleanup loop error: %s", exc)

        health_task = asyncio.create_task(health_check_loop())
        cleanup_task = asyncio.create_task(cleanup_loop())

        try:
            yield
        finally:
            # Cancel background tasks
            health_task.cancel()
            cleanup_task.cancel()
            await asyncio.gather(health_task, cleanup_task, return_exceptions=True)

            # Drain running jobs (wait up to drain_timeout_seconds)
            drain_timeout = config.server.drain_timeout_seconds
            if drain_timeout > 0:
                logger.info(
                    "Draining running jobs (timeout=%ds)...", drain_timeout
                )
                active_statuses = {JobStatus.PENDING, JobStatus.RUNNING}
                deadline = asyncio.get_event_loop().time() + drain_timeout
                while asyncio.get_event_loop().time() < deadline:
                    running = [
                        j
                        for j in state.tracker.list_jobs()
                        if j.status in active_statuses
                    ]
                    if not running:
                        break
                    await asyncio.sleep(0.5)

            # Stop the pool
            logger.info("Stopping MATLAB engine pool...")
            await state.pool.stop()
            logger.info("MATLAB engine pool stopped")

    # ------------------------------------------------------------------
    # Create FastMCP instance
    # ------------------------------------------------------------------

    mcp = FastMCP(
        name=config.server.name,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Tool registrations
    # ------------------------------------------------------------------

    @mcp.tool
    async def execute_code(ctx: Context, code: str) -> dict:
        """Execute MATLAB code.

        Runs the given MATLAB code string in the session's engine.
        Returns a result dict with status, job_id, output, variables, etc.
        """
        session_id = state._get_session_id(ctx)
        state.sessions.get_or_create_default() if session_id == "default" else None
        temp_dir = state._get_temp_dir(session_id)
        return await execute_code_impl(
            code=code,
            session_id=session_id,
            executor=state.executor,
            security=state.security,
        )

    @mcp.tool
    async def check_code(ctx: Context, code: str) -> dict:
        """Lint MATLAB code using checkcode/mlint.

        Writes the code to a temporary file and runs mcp_checkcode() on it,
        returning a list of issues (line, column, message, severity).
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await check_code_impl(
            code=code,
            session_id=session_id,
            executor=state.executor,
            temp_dir=temp_dir,
        )

    @mcp.tool
    async def get_workspace(ctx: Context) -> dict:
        """Get workspace variables for the current session.

        Runs 'whos' in MATLAB and returns the result.
        """
        session_id = state._get_session_id(ctx)
        return await get_workspace_impl(
            session_id=session_id,
            executor=state.executor,
        )

    @mcp.tool
    async def get_job_status(ctx: Context, job_id: str) -> dict:
        """Get the status of a MATLAB execution job.

        Returns status, timing info, and optional progress (from .progress file)
        for running jobs.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await get_job_status_impl(
            job_id=job_id,
            tracker=state.tracker,
            temp_dir=temp_dir,
        )

    @mcp.tool
    async def get_job_result(ctx: Context, job_id: str) -> dict:
        """Get the full result of a completed MATLAB execution job.

        Returns the result dict for completed jobs, or the error dict for
        failed jobs.
        """
        return await get_job_result_impl(
            job_id=job_id,
            tracker=state.tracker,
        )

    @mcp.tool
    async def cancel_job(ctx: Context, job_id: str) -> dict:
        """Cancel a pending or running MATLAB execution job.

        Attempts to cancel the underlying MATLAB future and marks the job
        as cancelled in the tracker.
        """
        return await cancel_job_impl(
            job_id=job_id,
            tracker=state.tracker,
        )

    @mcp.tool
    async def list_jobs(ctx: Context) -> dict:
        """List all jobs for the current session.

        Returns a list of job summaries including status and timing.
        """
        session_id = state._get_session_id(ctx)
        return await list_jobs_impl(
            session_id=session_id,
            tracker=state.tracker,
        )

    @mcp.tool
    async def list_toolboxes(ctx: Context) -> dict:
        """List available MATLAB toolboxes.

        Runs 'ver' in MATLAB and returns the output along with toolbox
        configuration info.
        """
        session_id = state._get_session_id(ctx)
        return await list_toolboxes_impl(
            session_id=session_id,
            executor=state.executor,
            toolbox_config=config.toolboxes,
        )

    @mcp.tool
    async def list_functions(ctx: Context, toolbox_name: str) -> dict:
        """List functions in a MATLAB toolbox.

        Runs 'help <toolbox_name>' in MATLAB and returns the output.
        """
        session_id = state._get_session_id(ctx)
        return await list_functions_impl(
            toolbox_name=toolbox_name,
            session_id=session_id,
            executor=state.executor,
        )

    @mcp.tool
    async def get_help(ctx: Context, function_name: str) -> dict:
        """Get help text for a MATLAB function.

        Runs 'help <function_name>' in MATLAB and returns the documentation.
        """
        session_id = state._get_session_id(ctx)
        return await get_help_impl(
            function_name=function_name,
            session_id=session_id,
            executor=state.executor,
        )

    @mcp.tool
    async def upload_data(
        ctx: Context,
        filename: str,
        content_base64: str,
    ) -> dict:
        """Upload a data file to the session's temporary directory.

        The file content should be base64-encoded. The file is written to the
        session temp dir and can be accessed from MATLAB code.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await upload_data_impl(
            filename=filename,
            content_base64=content_base64,
            session_temp_dir=temp_dir,
            security=state.security,
            max_size_mb=config.security.max_upload_size_mb,
        )

    @mcp.tool
    async def delete_file(ctx: Context, filename: str) -> dict:
        """Delete a file from the session's temporary directory.

        Only files in the session temp directory can be deleted.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await delete_file_impl(
            filename=filename,
            session_temp_dir=temp_dir,
            security=state.security,
        )

    @mcp.tool
    async def list_files(ctx: Context) -> dict:
        """List files in the session's temporary directory.

        Returns names, sizes, and paths for all files in the session temp dir.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await list_files_impl(session_temp_dir=temp_dir)

    @mcp.tool
    async def get_pool_status(ctx: Context) -> dict:
        """Get the current status of the MATLAB engine pool.

        Returns the total, available, busy, and max engine counts.
        """
        return await get_pool_status_impl(pool=state.pool)

    # ------------------------------------------------------------------
    # Custom tools
    # ------------------------------------------------------------------

    custom_tools = load_custom_tools(config.custom_tools.config_file)
    for tool_def in custom_tools:
        try:
            handler = make_custom_tool_handler(tool_def, state)
            mcp.add_tool(handler)
            logger.info("Registered custom tool: %s", tool_def.name)
        except Exception as exc:
            logger.error(
                "Failed to register custom tool %r: %s", tool_def.name, exc
            )

    return mcp


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point.  Load config, set up logging, and run the server."""
    import argparse

    parser = argparse.ArgumentParser(description="MATLAB MCP Server")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config YAML file",
    )
    parser.add_argument(
        "--transport",
        default=None,
        choices=["stdio", "sse"],
        help="Override transport from config",
    )
    args = parser.parse_args()

    # Load config
    config_path = Path(args.config) if args.config else Path("config.yaml")
    config = load_config(config_path if config_path.exists() else None)

    # CLI override
    if args.transport is not None:
        config.server.transport = args.transport  # type: ignore[assignment]

    # Set up logging
    log_level = getattr(logging, config.server.log_level.upper(), logging.INFO)
    log_file = config.server.log_file

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        log_dir = Path(log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except Exception as exc:
        print(f"Warning: could not set up file logging to {log_file}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=handlers,
        force=True,
    )

    transport = config.server.transport
    logger.info("Starting MATLAB MCP Server (transport=%s)", transport)

    server = create_server(config)

    if transport == "sse":
        server.run(
            transport="sse",
            host=config.server.host,
            port=config.server.port,
        )
    else:
        server.run(transport="stdio")
