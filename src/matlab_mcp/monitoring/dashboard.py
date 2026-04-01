"""Dashboard Starlette sub-app with API routes and static file serving."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from matlab_mcp.monitoring.routes import (
    build_health_response,
    build_metrics_response,
    get_health_status_code,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_monitoring_app(state: Any) -> Starlette:
    """Create a Starlette sub-application for monitoring endpoints and the dashboard.

    Registers the following routes:

    * ``/health`` -- JSON health status (200 or 503).
    * ``/metrics`` -- Live metrics snapshot.
    * ``/dashboard`` -- Static HTML dashboard page.
    * ``/dashboard/api/current`` -- Current metrics JSON for the dashboard.
    * ``/dashboard/api/history`` -- Historical time-series data.
    * ``/dashboard/api/events`` -- Recent event log.
    * ``/dashboard/static/`` -- Static file mount (CSS, JS, images).

    Args:
        state: A :class:`~matlab_mcp.server.MatlabMCPServer` instance
            providing access to the collector and metrics store.
    """

    # Cache index.html at startup to avoid blocking the event loop
    index_path = STATIC_DIR / "index.html"
    _cached_html = index_path.read_text() if index_path.exists() else None

    async def health_handler(request: Request) -> JSONResponse:
        """Handle GET /health."""
        response = build_health_response(state)
        return JSONResponse(response, status_code=get_health_status_code(response))

    async def metrics_handler(request: Request) -> JSONResponse:
        """Handle GET /metrics."""
        return JSONResponse(build_metrics_response(state))

    async def dashboard_handler(request: Request) -> HTMLResponse:
        """Handle GET /dashboard -- serve the cached HTML page."""
        if _cached_html is not None:
            return HTMLResponse(_cached_html)
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    async def api_current(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/current -- live metrics snapshot."""
        return JSONResponse(build_metrics_response(state))

    async def api_history(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/history -- time-series history.

        Query params: ``metric`` (default ``pool.utilization_pct``),
        ``hours`` (default ``1``).
        """
        metric = request.query_params.get("metric", "pool.utilization_pct")
        try:
            hours = float(request.query_params.get("hours", "1"))
        except (ValueError, TypeError):
            hours = 1.0
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"data": [], "warning": "metrics unavailable"})
        data = await store.get_history(metric, hours)
        return JSONResponse({"data": data})

    async def api_events(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/events -- recent event log.

        Query params: ``limit`` (default ``100``), ``type`` (optional
        event type filter).
        """
        try:
            limit = int(request.query_params.get("limit", "100"))
        except (ValueError, TypeError):
            limit = 100
        event_type = request.query_params.get("type")
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"events": [], "warning": "metrics unavailable"})
        events = await store.get_events(limit=limit, event_type=event_type)
        return JSONResponse({"events": events})

    routes = [
        Route("/health", health_handler),
        Route("/metrics", metrics_handler),
        Route("/dashboard", dashboard_handler),
        Route("/dashboard/api/current", api_current),
        Route("/dashboard/api/history", api_history),
        Route("/dashboard/api/events", api_events),
    ]

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        routes.append(
            Mount("/dashboard/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static")
        )

    return Starlette(routes=routes)


def register_monitoring_routes(mcp: FastMCP, state: Any) -> None:
    """Register monitoring endpoints on a FastMCP instance via ``custom_route()``.

    Registers the following routes using the public ``@mcp.custom_route()`` API:

    * ``GET /health`` -- JSON health status (200 or 503).
    * ``GET /metrics`` -- Live metrics snapshot.
    * ``GET /dashboard`` -- Static HTML dashboard page.
    * ``GET /dashboard/api/current`` -- Current metrics JSON.
    * ``GET /dashboard/api/history`` -- Historical time-series data.
    * ``GET /dashboard/api/events`` -- Recent event log.
    * ``GET /dashboard/static/{path:path}`` -- Static files (CSS, JS).

    Args:
        mcp: The :class:`~fastmcp.FastMCP` server instance to register routes on.
        state: A :class:`~matlab_mcp.server.MatlabMCPServer` instance providing
            access to the collector and metrics store.
    """
    # Cache index.html at registration time to avoid blocking the event loop
    index_path = STATIC_DIR / "index.html"
    _cached_html = index_path.read_text() if index_path.exists() else None

    @mcp.custom_route("/health", methods=["GET"])
    async def health_handler(request: Request) -> JSONResponse:
        """Handle GET /health."""
        response = build_health_response(state)
        return JSONResponse(response, status_code=get_health_status_code(response))

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics_handler(request: Request) -> JSONResponse:
        """Handle GET /metrics."""
        return JSONResponse(build_metrics_response(state))

    @mcp.custom_route("/dashboard", methods=["GET"])
    async def dashboard_handler(request: Request) -> HTMLResponse:
        """Handle GET /dashboard -- serve the cached HTML page."""
        if _cached_html is not None:
            return HTMLResponse(_cached_html)
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    @mcp.custom_route("/dashboard/api/current", methods=["GET"])
    async def api_current(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/current -- live metrics snapshot."""
        return JSONResponse(build_metrics_response(state))

    @mcp.custom_route("/dashboard/api/history", methods=["GET"])
    async def api_history(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/history -- time-series history.

        Query params: ``metric`` (default ``pool.utilization_pct``),
        ``hours`` (default ``1``).
        """
        metric = request.query_params.get("metric", "pool.utilization_pct")
        try:
            hours = float(request.query_params.get("hours", "1"))
        except (ValueError, TypeError):
            hours = 1.0
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"data": [], "warning": "metrics unavailable"})
        data = await store.get_history(metric, hours)
        return JSONResponse({"data": data})

    @mcp.custom_route("/dashboard/api/events", methods=["GET"])
    async def api_events(request: Request) -> JSONResponse:
        """Handle GET /dashboard/api/events -- recent event log.

        Query params: ``limit`` (default ``100``), ``type`` (optional
        event type filter).
        """
        try:
            limit = int(request.query_params.get("limit", "100"))
        except (ValueError, TypeError):
            limit = 100
        event_type = request.query_params.get("type")
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"events": [], "warning": "metrics unavailable"})
        events = await store.get_events(limit=limit, event_type=event_type)
        return JSONResponse({"events": events})

    @mcp.custom_route("/dashboard/static/{path:path}", methods=["GET"])
    async def static_handler(request: Request) -> FileResponse | HTMLResponse:
        """Handle GET /dashboard/static/{path} -- serve static files.

        Rejects path-traversal attempts (paths containing ``..``).
        Returns 404 for missing files.
        """
        path_str = request.path_params.get("path", "")
        if ".." in path_str:
            return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
        file_path = STATIC_DIR / path_str
        if not file_path.exists() or not file_path.is_file():
            return HTMLResponse("<h1>Not Found</h1>", status_code=404)
        return FileResponse(str(file_path))

    logger.debug("Registered 7 monitoring routes via custom_route()")
