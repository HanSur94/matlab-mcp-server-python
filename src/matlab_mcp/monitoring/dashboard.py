"""Dashboard Starlette sub-app with API routes and static file serving."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from matlab_mcp.monitoring.routes import (
    build_health_response,
    build_metrics_response,
    get_health_status_code,
)

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
