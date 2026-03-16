"""MATLAB engine pool manager.

Manages a pool of ``MatlabEngineWrapper`` instances, handling:
- Startup of a minimum number of engines in parallel
- Acquire/release with queueing when all engines are busy
- Scale-up on demand up to max_engines
- Scale-down of idle engines beyond min_engines
- Periodic health checks that replace dead engines
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper

logger = logging.getLogger(__name__)


class EnginePoolManager:
    """Manages a pool of MATLAB engine wrappers.

    Parameters
    ----------
    config:
        ``AppConfig`` instance.  Uses ``config.pool`` and ``config.workspace``.
    """

    def __init__(self, config: Any, collector: Any = None) -> None:
        self._config = config
        self._pool_config = config.pool
        self._workspace_config = config.workspace
        self._collector = collector

        # All engines (available + busy)
        self._all_engines: List[MatlabEngineWrapper] = []
        # Queue of engines available for acquisition
        self._available: asyncio.Queue = asyncio.Queue()
        # Lock to guard scale-up logic
        self._scale_lock: asyncio.Lock = asyncio.Lock()
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_engine(self) -> MatlabEngineWrapper:
        engine_id = f"engine-{self._next_id}"
        self._next_id += 1
        return MatlabEngineWrapper(engine_id, self._pool_config, self._workspace_config)

    async def _start_engine_async(self) -> MatlabEngineWrapper:
        """Start a single engine in a thread executor and return it."""
        loop = asyncio.get_running_loop()
        engine = self._make_engine()
        self._all_engines.append(engine)
        await loop.run_in_executor(None, engine.start)
        return engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start min_engines engines in parallel."""
        min_engines = self._pool_config.min_engines
        logger.info("Starting pool with %d engine(s)", min_engines)

        tasks = [self._start_engine_async() for _ in range(min_engines)]
        engines = await asyncio.gather(*tasks)

        for engine in engines:
            await self._available.put(engine)

        logger.info("Pool started: %d engine(s) ready", min_engines)

    async def acquire(self) -> MatlabEngineWrapper:
        """Return an available engine, scaling up if needed.

        Blocks if the pool is at max capacity and all engines are busy.
        """
        # Try to get an immediately available engine
        try:
            engine = self._available.get_nowait()
            engine.mark_busy()
            logger.info("Acquired engine %s (available=%d, busy=%d)",
                        engine.engine_id, self._available.qsize(),
                        len(self._all_engines) - self._available.qsize())
            return engine
        except asyncio.QueueEmpty:
            pass

        # Attempt scale-up under a lock to avoid races
        async with self._scale_lock:
            total = len(self._all_engines)
            if total < self._pool_config.max_engines:
                logger.info("Scaling up pool: starting new engine (%d/%d)",
                            total + 1, self._pool_config.max_engines)
                engine = await self._start_engine_async()
                engine.mark_busy()
                if self._collector:
                    self._collector.record_event("engine_scale_up", {"engine_id": engine.engine_id, "total_after": len(self._all_engines)})
                return engine

        # At max capacity — wait for one to become available
        logger.warning("Pool at max capacity (%d/%d busy) — waiting for available engine",
                        len(self._all_engines), self._pool_config.max_engines)
        engine = await self._available.get()
        engine.mark_busy()
        logger.info("Acquired engine %s after wait (pool was full)", engine.engine_id)
        return engine

    async def release(self, engine: MatlabEngineWrapper) -> None:
        """Return an engine to the pool."""
        logger.info("Releasing engine %s — resetting workspace", engine.engine_id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, engine.reset_workspace)
        engine.mark_idle()
        await self._available.put(engine)
        logger.info("Engine %s returned to pool (available=%d)",
                     engine.engine_id, self._available.qsize())

    async def stop(self) -> None:
        """Stop all engines in the pool."""
        logger.info("Stopping pool (%d engines)", len(self._all_engines))
        loop = asyncio.get_running_loop()
        stop_tasks = [
            loop.run_in_executor(None, engine.stop)
            for engine in self._all_engines
        ]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        self._all_engines.clear()
        # Drain the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("Pool stopped")

    async def run_health_checks(self) -> None:
        """Check idle engines, replace dead ones, scale down excess idle engines.

        - Engines that fail health check are stopped and replaced.
        - Idle engines beyond min_engines are stopped and removed.
        """
        loop = asyncio.get_running_loop()
        min_engines = self._pool_config.min_engines
        idle_timeout = self._pool_config.scale_down_idle_timeout

        # Collect currently available (idle) engines by draining the queue
        idle_engines: List[MatlabEngineWrapper] = []
        while not self._available.empty():
            try:
                idle_engines.append(self._available.get_nowait())
            except asyncio.QueueEmpty:
                break

        to_replace: List[MatlabEngineWrapper] = []
        to_remove: List[MatlabEngineWrapper] = []
        to_keep: List[MatlabEngineWrapper] = []

        # How many busy engines do we have?
        busy_count = sum(1 for e in self._all_engines if e.state == EngineState.BUSY)
        idle_count = len(idle_engines)
        total = busy_count + idle_count

        for engine in idle_engines:
            # Check health
            healthy = await loop.run_in_executor(None, engine.health_check)
            if not healthy:
                logger.warning("[%s] Health check failed; replacing", engine.engine_id)
                if self._collector:
                    self._collector.record_event("health_check_fail", {"engine_id": engine.engine_id, "error": "health check failed"})
                to_replace.append(engine)
                continue

            # Scale down if idle beyond timeout and above min
            if (engine.idle_seconds > idle_timeout
                    and total > min_engines
                    and len(to_keep) + busy_count >= min_engines):
                logger.info("[%s] Scaling down idle engine (idle %.0fs)",
                            engine.engine_id, engine.idle_seconds)
                if self._collector:
                    self._collector.record_event("engine_scale_down", {"engine_id": engine.engine_id, "total_after": total - 1})
                to_remove.append(engine)
                total -= 1
            else:
                to_keep.append(engine)

        # Stop engines to remove / replace
        engines_to_stop = to_replace + to_remove
        stop_tasks = [loop.run_in_executor(None, e.stop) for e in engines_to_stop]
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        for e in engines_to_stop:
            try:
                self._all_engines.remove(e)
            except ValueError:
                pass

        # Start replacement engines for failed ones
        replacement_tasks = [self._start_engine_async() for _ in to_replace]
        new_engines = await asyncio.gather(*replacement_tasks, return_exceptions=True)

        # Return healthy engines + replacements to queue
        for engine in to_keep:
            await self._available.put(engine)
        for old_engine, new_engine in zip(to_replace, new_engines):
            if isinstance(new_engine, Exception):
                logger.error("Replacement engine failed to start: %s", new_engine)
            else:
                if self._collector:
                    self._collector.record_event("engine_replaced", {"old_id": old_engine.engine_id, "new_id": new_engine.engine_id})
                await self._available.put(new_engine)

    def get_status(self) -> Dict[str, int]:
        """Return pool status summary."""
        total = len(self._all_engines)
        available = self._available.qsize()
        busy = total - available
        return {
            "total": total,
            "available": available,
            "busy": max(busy, 0),
            "max": self._pool_config.max_engines,
        }
