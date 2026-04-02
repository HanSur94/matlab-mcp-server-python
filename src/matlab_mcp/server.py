"""Main MCP Server entry point for MATLAB MCP Server.

Ties together all components (pool, tracker, executor, sessions, security,
formatter, custom tools) and exposes them as FastMCP tools.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
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
from matlab_mcp.tools.files import (
    delete_file_impl,
    list_files_impl,
    read_data_impl,
    read_image_impl,
    read_script_impl,
    upload_data_impl,
)
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
        """Initialize server state and all sub-components.

        Creates the engine pool, job tracker, executor, session manager,
        security validator, and (when monitoring is enabled) the metrics
        collector.  The metrics store is wired up later during the
        server lifespan.
        """
        self.config = config
        # Collector and store always initialised (None when disabled)
        self.collector: Optional[Any] = None
        self.store: Optional[Any] = None  # Set in lifespan when monitoring enabled
        if config.monitoring.enabled:
            from matlab_mcp.monitoring.collector import MetricsCollector
            self.collector = MetricsCollector(config)

        self.pool = EnginePoolManager(config, collector=self.collector)
        self.tracker = JobTracker(
            retention_seconds=config.sessions.job_retention_seconds
        )
        self.executor = JobExecutor(
            pool=self.pool,
            tracker=self.tracker,
            config=config,
            collector=self.collector,
        )
        self.sessions = SessionManager(config, collector=self.collector)
        self.security = SecurityValidator(config.security, collector=self.collector)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _get_session_id(self, ctx: Context) -> str:
        """Return session ID for the current request.

        For stdio transport a fixed ``"default"`` ID is used.
        For SSE/streamable-HTTP the context's ``session_id`` is preferred,
        falling back to ``client_id`` when ``session_id`` is unavailable
        (issue #956).
        """
        transport = self.config.server.transport
        if transport in ("sse", "streamablehttp"):
            try:
                sid = ctx.session_id
                if sid:
                    return sid
            except Exception:
                pass
            # Fallback for issue #956: try client_id when session_id unavailable
            try:
                cid = ctx.client_id
                if cid:
                    return cid
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
            if self.config.server.transport in ("sse", "streamablehttp"):
                # In SSE/streamable-HTTP mode, create a per-client session
                session = self.sessions.create_session(session_id=session_id)
            else:
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
        """Manage server startup and graceful shutdown.

        On startup: creates directories, starts the engine pool, wires
        the monitoring subsystem, and launches background tasks for
        health checks and session/job cleanup.

        On shutdown: stops the metrics collector, closes the store,
        cancels background tasks, drains running jobs, and stops the
        engine pool.
        """
        # Security warning for SSE without proxy auth or bearer token
        if (
            config.server.transport == "sse"
            and not config.security.require_proxy_auth
            and not os.environ.get("MATLAB_MCP_AUTH_TOKEN")
        ):
            logger.warning(
                "SSE transport enabled without authentication. "
                "Set MATLAB_MCP_AUTH_TOKEN env var to enable bearer token auth."
            )

        # Create necessary directories
        logger.info("Initializing directories...")
        result_dir = Path(config.server.result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("  Result dir: %s", result_dir)

        temp_dir = Path(config.execution.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("  Temp dir:   %s", temp_dir)

        log_dir = Path(config.server.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("  Log dir:    %s", log_dir)

        # Add matlab_helpers to workspace paths so MATLAB can find helper functions
        helpers_dir = str(Path(__file__).parent / "matlab_helpers")
        if helpers_dir not in config.workspace.default_paths:
            config.workspace.default_paths.insert(0, helpers_dir)

        # Initialize monitoring store and connect collector
        collector_task = None
        monitoring_server = None
        monitoring_task = None

        if config.monitoring.enabled and state.collector:
            logger.info("Initializing monitoring subsystem...")
            from matlab_mcp.monitoring.store import MetricsStore

            monitoring_dir = Path(config.monitoring.db_path).parent
            monitoring_dir.mkdir(parents=True, exist_ok=True)

            state.store = MetricsStore(config.monitoring.db_path)
            await state.store.initialize()
            logger.info("  Metrics store: %s (initialized)", config.monitoring.db_path)

            state.collector.store = state.store

        # Start engine pool (skip in inspect mode)
        if getattr(config, '_inspect_mode', False):
            logger.info('Inspect mode: skipping MATLAB engine pool startup')
        else:
            logger.info('Starting MATLAB engine pool...')
            try:
                await state.pool.start()
                logger.info('MATLAB engine pool started')
            except Exception as exc:
                logger.warning(
                    'MATLAB engine pool failed to start: %s. '
                    'Tools will be unavailable until MATLAB is configured.',
                    exc,
                )

        # Wire collector to live components
        if state.collector:
            state.collector.pool = state.pool
            state.collector.tracker = state.tracker
            state.collector.sessions = state.sessions
            collector_task = asyncio.create_task(state.collector.start_sampling())
            logger.info("  Metrics collector sampling every %ds", config.monitoring.sample_interval)

        # Start monitoring HTTP server for stdio transport
        if (
            config.server.transport == "stdio"
            and config.monitoring.enabled
            and state.collector
        ):
            try:
                import uvicorn
                from matlab_mcp.monitoring.dashboard import create_monitoring_app

                monitoring_app = create_monitoring_app(state)
                uvi_config = uvicorn.Config(
                    monitoring_app,
                    host="127.0.0.1",
                    port=config.monitoring.http_port,
                    log_level="warning",
                )
                monitoring_server = uvicorn.Server(uvi_config)
                monitoring_task = asyncio.create_task(monitoring_server.serve())
                logger.info(
                    "Monitoring dashboard at http://127.0.0.1:%d/dashboard",
                    config.monitoring.http_port,
                )
            except ImportError:
                logger.warning("uvicorn not installed — monitoring HTTP server disabled")

        # Background task: periodic health checks
        async def health_check_loop() -> None:
            """Periodically run engine health checks at the configured interval."""
            interval = config.pool.health_check_interval
            while True:
                try:
                    await asyncio.sleep(interval)
                    await state.pool.run_health_checks()
                    status_after = state.pool.get_status()
                    logger.debug("Health check done: engines %d/%d (avail=%d)",
                                 status_after["busy"], status_after["total"],
                                 status_after["available"])
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Health check error: %s", exc)

        # Background task: session + job cleanup
        async def cleanup_loop() -> None:
            """Periodically expire idle sessions, prune old jobs, and trim metrics."""
            while True:
                try:
                    await asyncio.sleep(60)
                    removed = state.sessions.cleanup_expired(
                        has_active_jobs_fn=state.tracker.has_active_jobs
                    )
                    pruned = state.tracker.prune()
                    if state.store:
                        await state.store.prune(config.monitoring.retention_days)
                    if removed or pruned:
                        logger.info("Cleanup: %d sessions expired, %d jobs pruned",
                                     removed, pruned)
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error("Cleanup loop error: %s", exc)

        health_task = asyncio.create_task(health_check_loop())
        logger.info("Background task started: health checks (every %ds)", config.pool.health_check_interval)
        cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Background task started: session/job cleanup (every 60s)")
        logger.info("=" * 60)
        logger.info("Server ready — accepting connections")
        logger.info("=" * 60)

        try:
            yield
        finally:
            logger.info("=" * 60)
            logger.info("Server shutting down...")
            logger.info("=" * 60)

            # Stop monitoring (order: collector → store → HTTP server)
            if collector_task:
                logger.info("Stopping metrics collector...")
                collector_task.cancel()
                await asyncio.gather(collector_task, return_exceptions=True)
            if state.store:
                logger.info("Closing metrics store...")
                await state.store.close()
            if monitoring_server is not None:
                logger.info("Stopping monitoring HTTP server...")
                monitoring_server.should_exit = True
            if monitoring_task is not None:
                await monitoring_task

            # Cancel background tasks
            logger.info("Cancelling background tasks...")
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
            logger.info("=" * 60)
            logger.info("Shutdown complete")
            logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Create FastMCP instance
    # ------------------------------------------------------------------

    mcp = FastMCP(
        name=config.server.name,
        lifespan=lifespan,
    )

    # Register monitoring routes for SSE transport
    if config.server.transport == "sse" and config.monitoring.enabled:
        try:
            from matlab_mcp.monitoring.dashboard import register_monitoring_routes

            register_monitoring_routes(mcp, state)
            logger.info("Monitoring routes registered for SSE transport (/dashboard, /health)")
        except Exception as exc:
            logger.warning("Failed to register monitoring routes for SSE: %s", exc)

    # ------------------------------------------------------------------
    # Tool registrations
    # ------------------------------------------------------------------

    @mcp.tool
    async def execute_code(ctx: Context, code: str) -> dict:
        """Execute MATLAB code.

        Runs the given MATLAB code string in the session's engine.
        Returns a result dict with status, job_id, output, variables, etc.
        """
        logger.info("Tool call: execute_code  session=%s  code=%s",
                     state._get_session_id(ctx)[:8], repr(code[:120]))
        session_id = state._get_session_id(ctx)
        state.sessions.get_or_create_default() if session_id == "default" else None
        temp_dir = state._get_temp_dir(session_id)
        result = await execute_code_impl(
            code=code,
            session_id=session_id,
            executor=state.executor,
            security=state.security,
            temp_dir=temp_dir,
            ctx=ctx,
            hitl_config=config.hitl,
        )
        logger.info("Tool result: execute_code  status=%s  job=%s",
                     result.get("status"), result.get("job_id", "")[:8])
        return result

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
            ctx=ctx,
            hitl_config=config.hitl,
            session_id=session_id,
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
            ctx=ctx,
            hitl_config=config.hitl,
            session_id=session_id,
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
    async def read_script(ctx: Context, filename: str) -> dict:
        """Read a MATLAB .m script file from the session's temporary directory.

        Returns the file content as text. Use list_files to see available files.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_script_impl(
            filename=filename,
            session_temp_dir=temp_dir,
            security=state.security,
            max_inline_text_length=config.output.max_inline_text_length,
        )

    @mcp.tool
    async def read_data(
        ctx: Context,
        filename: str,
        format: str = "summary",
    ) -> dict:
        """Read a data file (.mat, .csv, .json, .txt, .xlsx) from the session temp directory.

        For .mat files, 'summary' mode shows variable names/sizes/types via MATLAB,
        'raw' mode returns base64-encoded content. Text files return inline content.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_data_impl(
            filename=filename,
            format=format,
            session_temp_dir=temp_dir,
            security=state.security,
            max_size_mb=config.security.max_upload_size_mb,
            max_inline_text_length=config.output.max_inline_text_length,
            executor=state.executor,
            session_id=session_id,
        )

    @mcp.tool
    async def read_image(ctx: Context, filename: str):
        """Read an image file (.png, .jpg, .gif) from the session temp directory.

        Returns the image as an inline content block that renders in agent UIs.
        """
        session_id = state._get_session_id(ctx)
        temp_dir = state._get_temp_dir(session_id)
        return await read_image_impl(
            filename=filename,
            session_temp_dir=temp_dir,
            security=state.security,
            max_size_mb=config.security.max_upload_size_mb,
        )

    @mcp.tool
    async def get_pool_status(ctx: Context) -> dict:
        """Get the current status of the MATLAB engine pool.

        Returns the total, available, busy, and max engine counts.
        """
        return await get_pool_status_impl(pool=state.pool)

    # ------------------------------------------------------------------
    # Monitoring tools
    # ------------------------------------------------------------------

    from matlab_mcp.tools.monitoring import (
        get_error_log_impl,
        get_server_health_impl,
        get_server_metrics_impl,
    )

    @mcp.tool
    async def get_server_metrics(ctx: Context) -> dict:
        """Get comprehensive server metrics including pool, jobs, sessions, and system stats."""
        return await get_server_metrics_impl(state)

    @mcp.tool
    async def get_server_health(ctx: Context) -> dict:
        """Get server health status with issue detection. Returns healthy/degraded/unhealthy."""
        return await get_server_health_impl(state)

    @mcp.tool
    async def get_error_log(ctx: Context, limit: int = 20) -> dict:
        """Get recent server errors and notable events for diagnosing issues."""
        return await get_error_log_impl(state, limit=limit)

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
    """CLI entry point for the MATLAB MCP Server.

    Parses ``--config`` and ``--transport`` arguments, loads the
    configuration, configures logging (stderr + file), prints a
    startup banner, and runs the FastMCP server in the selected
    transport mode (stdio or SSE).
    """
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
        choices=["stdio", "sse", "streamablehttp"],
        help="Override transport from config",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Start in inspection mode (no MATLAB required)",
    )
    parser.add_argument(
        "--generate-token",
        action="store_true",
        help="Generate a bearer token and print env var snippet, then exit",
    )
    args = parser.parse_args()

    if args.generate_token:
        import secrets
        token = secrets.token_hex(32)
        print(f"Generated MATLAB MCP auth token (64 hex chars):\n")
        print(f"  {token}\n")
        print(f"Set the environment variable:\n")
        print(f"  # Linux / macOS:")
        print(f"  export MATLAB_MCP_AUTH_TOKEN={token}\n")
        print(f"  # Windows (cmd):")
        print(f"  set MATLAB_MCP_AUTH_TOKEN={token}\n")
        print(f"  # Windows (PowerShell):")
        print(f"  $env:MATLAB_MCP_AUTH_TOKEN=\"{token}\"\n")
        sys.exit(0)

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

    # Startup banner with full config summary
    logger.info("=" * 60)
    logger.info("MATLAB MCP Server starting")
    logger.info("=" * 60)
    logger.info("  Transport:       %s", transport)
    if transport == "sse":
        logger.info("  SSE endpoint:    http://%s:%d/sse", config.server.host, config.server.port)
        logger.warning(
            "SSE transport is deprecated; use 'streamablehttp' instead. "
            "SSE support will be removed in a future release."
        )
    elif transport == "streamablehttp":
        logger.info("  HTTP endpoint:   http://%s:%d/mcp", config.server.host, config.server.port)
    logger.info("  Log level:       %s", config.server.log_level)
    logger.info("  Log file:        %s", config.server.log_file)
    logger.info("  Config file:     %s", config_path if config_path.exists() else "(defaults)")
    logger.info("--- Pool ---")
    logger.info("  Min engines:     %d", config.pool.min_engines)
    logger.info("  Max engines:     %d", config.pool.max_engines)
    logger.info("  Health interval: %ds", config.pool.health_check_interval)
    logger.info("  Idle timeout:    %ds", config.pool.scale_down_idle_timeout)
    logger.info("  MATLAB root:     %s", config.pool.matlab_root or "(auto-detect)")
    logger.info("--- Execution ---")
    logger.info("  Sync timeout:    %ds", config.execution.sync_timeout)
    logger.info("  Max exec time:   %ds", config.execution.max_execution_time)
    logger.info("  Workspace iso:   %s", config.execution.workspace_isolation)
    logger.info("  Temp dir:        %s", config.execution.temp_dir)
    logger.info("--- Security ---")
    logger.info("  Blocked funcs:   %s", config.security.blocked_functions if config.security.blocked_functions_enabled else "(disabled)")
    logger.info("  Max upload:      %d MB", config.security.max_upload_size_mb)
    logger.info("  Proxy auth:      %s", config.security.require_proxy_auth)
    logger.info("--- Sessions ---")
    logger.info("  Max sessions:    %d", config.sessions.max_sessions)
    logger.info("  Session timeout: %ds", config.sessions.session_timeout)
    logger.info("--- Monitoring ---")
    logger.info("  Enabled:         %s", config.monitoring.enabled)
    if config.monitoring.enabled:
        logger.info("  Sample interval: %ds", config.monitoring.sample_interval)
        logger.info("  Retention:       %d days", config.monitoring.retention_days)
        logger.info("  DB path:         %s", config.monitoring.db_path)
        if transport == "stdio":
            logger.info("  Dashboard:       http://127.0.0.1:%d/dashboard", config.monitoring.http_port)
        else:
            logger.info("  Dashboard:       http://%s:%d/dashboard", config.server.host, config.server.port)
    logger.info("=" * 60)

    # Auth status
    if transport in ("sse", "streamablehttp"):
        if os.environ.get("MATLAB_MCP_AUTH_TOKEN"):
            logger.info("  Auth:            Bearer token enabled")
        else:
            logger.warning(
                "%s transport enabled without MATLAB_MCP_AUTH_TOKEN set. "
                "All HTTP requests will be accepted without authentication.",
                transport,
            )

    # Windows non-loopback warning (PLAT-01/PLAT-02)
    if (platform.system() == "Windows"
            and config.server.host not in ("127.0.0.1", "localhost")):
        logger.warning(
            "Server is bound to %s on Windows. Binding to a non-loopback "
            "address requires an admin-created inbound firewall rule and "
            "may trigger a Windows Firewall UAC prompt.",
            config.server.host,
        )

    if args.inspect:
        config.pool.min_engines = 0
        config._inspect_mode = True  # type: ignore[attr-defined]

    server = create_server(config)

    if transport in ("sse", "streamablehttp"):
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware
        from matlab_mcp.auth.middleware import BearerAuthMiddleware

        middleware: list[Middleware] = [
            Middleware(BearerAuthMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "Accept"],
            ),
        ]

        if transport == "streamablehttp":
            server.run(
                transport="streamable-http",
                host=config.server.host,
                port=config.server.port,
                middleware=middleware,
                stateless_http=config.server.stateless_http,
            )
        else:
            server.run(
                transport="sse",
                host=config.server.host,
                port=config.server.port,
                middleware=middleware,
            )
    else:
        server.run(transport="stdio", show_banner=False)
