"""Dashboard Starlette sub-app with API routes and static file serving."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from matlab_mcp.monitoring.health import evaluate_health
from matlab_mcp.monitoring.routes import (
    build_health_response,
    build_metrics_response,
    get_health_status_code,
)

STATIC_DIR = Path(__file__).parent / "static"


def create_monitoring_app(state: Any) -> Starlette:
    """Create a Starlette app for monitoring endpoints + dashboard."""

    async def health_handler(request: Request) -> JSONResponse:
        response = build_health_response(state)
        return JSONResponse(response, status_code=get_health_status_code(response))

    async def metrics_handler(request: Request) -> JSONResponse:
        return JSONResponse(build_metrics_response(state))

    async def dashboard_handler(request: Request) -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text())
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    async def api_current(request: Request) -> JSONResponse:
        return JSONResponse(build_metrics_response(state))

    async def api_history(request: Request) -> JSONResponse:
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
