"""Health evaluation for MATLAB MCP Server."""
from __future__ import annotations
import time
from typing import Any

def evaluate_health(collector: Any) -> dict[str, Any]:
    issues: list[str] = []
    pool_status = collector.pool.get_status() if collector.pool else {}
    total = pool_status.get("total", 0)
    available = pool_status.get("available", 0)
    busy = pool_status.get("busy", 0)
    max_engines = pool_status.get("max", 0)
    utilization = (busy / total * 100) if total > 0 else 0.0

    active_jobs = 0
    if collector.tracker:
        from matlab_mcp.jobs.models import JobStatus
        jobs = collector.tracker.list_jobs()
        active_jobs = sum(1 for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING))

    active_sessions = collector.sessions.session_count if collector.sessions else 0
    uptime = time.time() - collector.start_time

    status = "healthy"
    counters = collector.get_counters()

    # Unhealthy conditions (checked first, but utilization degraded takes priority)
    if total == 0:
        status = "unhealthy"
        issues.append("No engines running")
    elif available == 0 and total >= max_engines and utilization <= 90:
        status = "unhealthy"
        issues.append(f"All {total} engines busy and pool at max capacity ({max_engines})")

    # Degraded conditions
    if status != "unhealthy":
        if utilization > 90:
            status = "degraded"
            issues.append(f"Pool utilization at {utilization:.0f}% — consider increasing max_engines")
        if counters.get("health_check_failures", 0) > 0:
            status = "degraded"
            issues.append(f"{counters['health_check_failures']} health check failure(s) detected")
        error_total = counters.get("error_total", 0)
        uptime_minutes = max(uptime / 60, 1)
        error_rate = error_total / uptime_minutes
        if error_rate > 5:
            status = "degraded"
            issues.append(f"Error rate {error_rate:.1f}/min exceeds threshold (5/min)")

    return {
        "status": status,
        "uptime_seconds": round(uptime, 1),
        "issues": issues,
        "engines": {"total": total, "available": available, "busy": busy},
        "active_jobs": active_jobs,
        "active_sessions": active_sessions,
    }
