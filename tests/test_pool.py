"""Tests for the MATLAB engine wrapper and pool manager."""
from __future__ import annotations

import asyncio
import time
import types

import pytest

from matlab_mcp.config import AppConfig, PoolConfig, WorkspaceConfig
from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper


# ---------------------------------------------------------------------------
# Helpers — inject mock matlab.engine module
# ---------------------------------------------------------------------------

def _make_mock_matlab_engine_module():
    """Build a fake 'matlab.engine' module backed by the real mock engine."""
    from tests.mocks.matlab_engine_mock import start_matlab as real_start_matlab

    matlab_pkg = types.ModuleType("matlab")
    engine_mod = types.ModuleType("matlab.engine")
    engine_mod.start_matlab = real_start_matlab

    # Also expose MatlabExecutionError so wrapper can import it if needed
    from tests.mocks.matlab_engine_mock import MatlabExecutionError
    engine_mod.MatlabExecutionError = MatlabExecutionError

    matlab_pkg.engine = engine_mod
    return matlab_pkg, engine_mod


def _patch_matlab_engine(wrapper: MatlabEngineWrapper):
    """Patch the wrapper so it uses the mock matlab.engine module."""
    _, engine_mod = _make_mock_matlab_engine_module()
    wrapper._get_matlab_engine_module = lambda: engine_mod
    return wrapper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pool_config():
    return PoolConfig(min_engines=1, max_engines=3)


@pytest.fixture
def workspace_config():
    return WorkspaceConfig(
        default_paths=["/mock/path"],
        startup_commands=["format long"],
    )


@pytest.fixture
def engine_wrapper(pool_config, workspace_config):
    wrapper = MatlabEngineWrapper("engine-0", pool_config, workspace_config)
    _patch_matlab_engine(wrapper)
    return wrapper


@pytest.fixture
def started_engine(engine_wrapper):
    engine_wrapper.start()
    yield engine_wrapper
    if engine_wrapper.state != EngineState.STOPPED:
        engine_wrapper.stop()


@pytest.fixture
def app_config(pool_config, workspace_config):
    """AppConfig with small pool settings for testing."""
    cfg = AppConfig()
    cfg.pool = pool_config
    cfg.workspace = workspace_config
    return cfg


# ---------------------------------------------------------------------------
# Task 4: MatlabEngineWrapper
# ---------------------------------------------------------------------------


class TestEngineState:
    def test_enum_values_exist(self):
        assert EngineState.STOPPED
        assert EngineState.STARTING
        assert EngineState.IDLE
        assert EngineState.BUSY

    def test_states_are_distinct(self):
        states = {EngineState.STOPPED, EngineState.STARTING, EngineState.IDLE, EngineState.BUSY}
        assert len(states) == 4


class TestEngineWrapperInit:
    def test_initial_state_stopped(self, engine_wrapper):
        assert engine_wrapper.state == EngineState.STOPPED

    def test_engine_id_stored(self, engine_wrapper):
        assert engine_wrapper.engine_id == "engine-0"

    def test_not_alive_before_start(self, engine_wrapper):
        assert engine_wrapper.is_alive is False

    def test_idle_seconds_zero_when_not_idle(self, engine_wrapper):
        assert engine_wrapper.idle_seconds == 0.0


class TestEngineWrapperStart:
    def test_start_transitions_to_idle(self, engine_wrapper):
        engine_wrapper.start()
        assert engine_wrapper.state == EngineState.IDLE
        engine_wrapper.stop()

    def test_start_makes_engine_alive(self, engine_wrapper):
        engine_wrapper.start()
        assert engine_wrapper.is_alive is True
        engine_wrapper.stop()

    def test_start_applies_paths(self, engine_wrapper):
        engine_wrapper.start()
        assert "/mock/path" in engine_wrapper._engine._paths
        engine_wrapper.stop()

    def test_start_runs_startup_commands(self, engine_wrapper):
        """format long is the startup command; engine should have been called."""
        engine_wrapper.start()
        # The mock engine silently ignores unrecognised commands; just verify no exception
        assert engine_wrapper.state == EngineState.IDLE
        engine_wrapper.stop()


class TestEngineWrapperStop:
    def test_stop_transitions_to_stopped(self, started_engine):
        started_engine.stop()
        assert started_engine.state == EngineState.STOPPED

    def test_stop_makes_engine_not_alive(self, started_engine):
        started_engine.stop()
        assert started_engine.is_alive is False

    def test_stop_when_already_stopped_is_safe(self, engine_wrapper):
        # Should not raise even if never started
        engine_wrapper.stop()
        assert engine_wrapper.state == EngineState.STOPPED


class TestEngineWrapperHealthCheck:
    def test_health_check_returns_true_when_alive(self, started_engine):
        assert started_engine.health_check() is True

    def test_health_check_returns_false_when_not_started(self, engine_wrapper):
        assert engine_wrapper.health_check() is False

    def test_health_check_returns_false_after_stop(self, started_engine):
        started_engine.stop()
        assert started_engine.health_check() is False


class TestEngineWrapperExecute:
    def test_execute_runs_code(self, started_engine):
        started_engine.execute("x = 42;")
        assert started_engine._engine.workspace["x"] == 42

    def test_execute_raises_if_not_started(self, engine_wrapper):
        with pytest.raises(RuntimeError, match="not started"):
            engine_wrapper.execute("x = 1;")

    def test_execute_background_returns_future(self, started_engine):
        from tests.mocks.matlab_engine_mock import MockFuture
        fut = started_engine.execute("x = 1;", background=True)
        assert isinstance(fut, MockFuture)
        fut.result(timeout=5)

    def test_execute_with_error_propagates(self, started_engine):
        from tests.mocks.matlab_engine_mock import MatlabExecutionError
        with pytest.raises(MatlabExecutionError):
            started_engine.execute("error('boom');")


class TestEngineWrapperResetWorkspace:
    def test_reset_clears_workspace(self, started_engine):
        started_engine.execute("x = 99;")
        assert started_engine._engine.workspace["x"] == 99
        started_engine.reset_workspace()
        # After clear all, x should be gone
        assert "x" not in started_engine._engine.workspace

    def test_reset_reapplies_paths(self, started_engine):
        started_engine.reset_workspace()
        assert "/mock/path" in started_engine._engine._paths

    def test_reset_raises_if_not_started(self, engine_wrapper):
        with pytest.raises(RuntimeError, match="not started"):
            engine_wrapper.reset_workspace()


class TestEngineStateTransitions:
    def test_mark_busy(self, started_engine):
        started_engine.mark_busy()
        assert started_engine.state == EngineState.BUSY

    def test_mark_idle(self, started_engine):
        started_engine.mark_busy()
        started_engine.mark_idle()
        assert started_engine.state == EngineState.IDLE

    def test_idle_seconds_increases_over_time(self, started_engine):
        started_engine.mark_idle()
        time.sleep(0.05)
        assert started_engine.idle_seconds >= 0.04

    def test_idle_seconds_zero_when_busy(self, started_engine):
        started_engine.mark_busy()
        assert started_engine.idle_seconds == 0.0


# ---------------------------------------------------------------------------
# Task 5: EnginePoolManager
# ---------------------------------------------------------------------------

# We need to patch MatlabEngineWrapper so pool tests use the mock engine.

def _patched_engine_wrapper_factory(pool_cfg, workspace_cfg):
    """Factory that creates engine wrappers pre-patched with mock matlab.engine."""
    class PatchedEngineWrapper(MatlabEngineWrapper):
        def __init__(self, engine_id, pool_config, workspace_config):
            super().__init__(engine_id, pool_config, workspace_config)
            _patch_matlab_engine(self)

    return PatchedEngineWrapper


@pytest.fixture
def patched_pool_manager(app_config):
    """EnginePoolManager where all wrappers use the mock matlab.engine."""
    from matlab_mcp.pool.manager import EnginePoolManager

    PatchedWrapper = _patched_engine_wrapper_factory(app_config.pool, app_config.workspace)

    manager = EnginePoolManager(app_config)
    # Monkey-patch _make_engine to produce patched wrappers
    def patched_make_engine():
        engine_id = f"engine-{manager._next_id}"
        manager._next_id += 1
        wrapper = PatchedWrapper(engine_id, manager._pool_config, manager._workspace_config)
        return wrapper
    manager._make_engine = patched_make_engine
    return manager


class TestPoolManagerStart:
    async def test_start_creates_min_engines(self, patched_pool_manager):
        await patched_pool_manager.start()
        status = patched_pool_manager.get_status()
        assert status["total"] == 1  # min_engines=1
        await patched_pool_manager.stop()

    async def test_start_engines_are_available(self, patched_pool_manager):
        await patched_pool_manager.start()
        status = patched_pool_manager.get_status()
        assert status["available"] == 1
        assert status["busy"] == 0
        await patched_pool_manager.stop()

    async def test_start_max_reported_correctly(self, patched_pool_manager):
        await patched_pool_manager.start()
        status = patched_pool_manager.get_status()
        assert status["max"] == 3  # max_engines=3
        await patched_pool_manager.stop()


class TestPoolManagerAcquireRelease:
    async def test_acquire_returns_engine(self, patched_pool_manager):
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()
        assert isinstance(engine, MatlabEngineWrapper)
        assert engine.state == EngineState.BUSY
        await patched_pool_manager.release(engine)
        await patched_pool_manager.stop()

    async def test_acquire_marks_engine_busy(self, patched_pool_manager):
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()
        assert engine.state == EngineState.BUSY
        await patched_pool_manager.release(engine)
        await patched_pool_manager.stop()

    async def test_release_makes_engine_available(self, patched_pool_manager):
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()
        await patched_pool_manager.release(engine)
        status = patched_pool_manager.get_status()
        assert status["available"] == 1
        await patched_pool_manager.stop()

    async def test_release_resets_workspace(self, patched_pool_manager):
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()
        engine.execute("x = 42;")
        await patched_pool_manager.release(engine)
        # After release, workspace should be cleared
        assert "x" not in engine._engine.workspace
        await patched_pool_manager.stop()


class TestPoolManagerScaleUp:
    async def test_scale_up_when_all_busy(self, patched_pool_manager):
        """Acquiring beyond min_engines should start new engines up to max."""
        await patched_pool_manager.start()
        # min_engines=1; acquire 2 — should scale up
        e1 = await patched_pool_manager.acquire()
        e2 = await patched_pool_manager.acquire()
        status = patched_pool_manager.get_status()
        assert status["total"] == 2
        await patched_pool_manager.release(e1)
        await patched_pool_manager.release(e2)
        await patched_pool_manager.stop()

    async def test_max_engines_ceiling(self, patched_pool_manager):
        """Pool must not exceed max_engines (=3)."""
        await patched_pool_manager.start()

        # Acquire max_engines worth of engines concurrently
        engines = []
        for _ in range(3):
            e = await patched_pool_manager.acquire()
            engines.append(e)

        assert patched_pool_manager.get_status()["total"] == 3

        # Release one, then the status should show it available
        await patched_pool_manager.release(engines.pop())
        status = patched_pool_manager.get_status()
        assert status["total"] == 3
        assert status["available"] >= 1

        # Release the rest
        for e in engines:
            await patched_pool_manager.release(e)
        await patched_pool_manager.stop()

    async def test_acquire_blocks_at_max_until_released(self, patched_pool_manager):
        """When pool is full, acquire should wait until an engine is released."""
        await patched_pool_manager.start()
        # Exhaust pool (max=3)
        engines = [await patched_pool_manager.acquire() for _ in range(3)]

        # Schedule a release after a short delay
        async def release_one():
            await asyncio.sleep(0.05)
            await patched_pool_manager.release(engines[0])

        task = asyncio.create_task(release_one())
        # This should unblock after the release
        extra = await patched_pool_manager.acquire()
        assert extra is not None
        await task
        for e in engines[1:]:
            await patched_pool_manager.release(e)
        await patched_pool_manager.release(extra)
        await patched_pool_manager.stop()


class TestPoolManagerStop:
    async def test_stop_empties_pool(self, patched_pool_manager):
        await patched_pool_manager.start()
        await patched_pool_manager.stop()
        assert patched_pool_manager.get_status()["total"] == 0

    async def test_stop_marks_engines_stopped(self, patched_pool_manager):
        await patched_pool_manager.start()
        engines = list(patched_pool_manager._all_engines)
        await patched_pool_manager.stop()
        for e in engines:
            assert e.state == EngineState.STOPPED


class TestPoolManagerStatus:
    async def test_status_keys(self, patched_pool_manager):
        await patched_pool_manager.start()
        status = patched_pool_manager.get_status()
        assert set(status.keys()) == {"total", "available", "busy", "max"}
        await patched_pool_manager.stop()

    async def test_status_counts_busy_correctly(self, patched_pool_manager):
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()
        status = patched_pool_manager.get_status()
        assert status["busy"] == 1
        assert status["available"] == 0
        await patched_pool_manager.release(engine)
        await patched_pool_manager.stop()


class TestPoolManagerReleaseAndStartTimeout:
    async def test_release_returns_engine_on_reset_failure(self, patched_pool_manager):
        """Engine must be returned to pool even when reset_workspace() raises."""
        await patched_pool_manager.start()
        engine = await patched_pool_manager.acquire()

        # Force reset_workspace to raise
        original_reset = engine.reset_workspace
        def failing_reset():
            raise RuntimeError("workspace reset failed")
        engine.reset_workspace = failing_reset

        before_qsize = patched_pool_manager._available.qsize()
        await patched_pool_manager.release(engine)

        # Engine must have been put back in the queue
        assert patched_pool_manager._available.qsize() == before_qsize + 1
        assert engine._needs_replacement is True

        engine.reset_workspace = original_reset
        await patched_pool_manager.stop()

    async def test_start_engine_timeout(self, patched_pool_manager):
        """_start_engine_async should raise RuntimeError when start exceeds timeout."""
        # Override _make_engine to produce a wrapper whose start() sleeps forever
        original_make = patched_pool_manager._make_engine

        def slow_start_engine():
            wrapper = original_make()
            def slow_start():
                import time as _time
                _time.sleep(10)
            wrapper.start = slow_start
            return wrapper

        patched_pool_manager._make_engine = slow_start_engine
        patched_pool_manager._pool_config.engine_start_timeout = 0.05

        with pytest.raises(RuntimeError, match="failed to start"):
            await patched_pool_manager._start_engine_async()

    async def test_acquire_repoll_after_scale_lock(self, patched_pool_manager):
        """acquire() should pick up an engine placed in the queue after scale lock."""
        await patched_pool_manager.start()

        # Fill pool to max so scale-up path is taken
        engines = []
        for _ in range(patched_pool_manager._pool_config.max_engines):
            engines.append(await patched_pool_manager.acquire())

        # Put one engine directly into the available queue (simulating release
        # that happened while acquire() was inside the scale lock)
        released = engines.pop()
        released.mark_idle()
        await patched_pool_manager._available.put(released)

        # acquire() should get_nowait() the engine without blocking indefinitely
        acquired = await patched_pool_manager.acquire()
        assert acquired is released

        for e in engines:
            await patched_pool_manager.release(e)
        await patched_pool_manager.release(acquired)
        await patched_pool_manager.stop()

    async def test_get_status_counts_busy_from_state(self, patched_pool_manager):
        """get_status() busy_engines must reflect actual engine state, not arithmetic."""
        await patched_pool_manager.start()

        # Start with all idle; busy should be 0
        assert patched_pool_manager.get_status()["busy"] == 0

        # Manually mark one engine busy
        engine = patched_pool_manager._all_engines[0]
        engine.mark_busy()
        assert patched_pool_manager.get_status()["busy"] == 1

        # Mark it idle again
        engine.mark_idle()
        assert patched_pool_manager.get_status()["busy"] == 0

        await patched_pool_manager.stop()


class TestPoolManagerHealthChecks:
    async def test_health_check_keeps_healthy_engines(self, patched_pool_manager):
        await patched_pool_manager.start()
        before = patched_pool_manager.get_status()["total"]
        await patched_pool_manager.run_health_checks()
        after = patched_pool_manager.get_status()["total"]
        assert after == before
        await patched_pool_manager.stop()

    async def test_health_check_replaces_dead_engine(self, patched_pool_manager):
        await patched_pool_manager.start()
        # Kill the engine's underlying mock engine
        for engine in list(patched_pool_manager._all_engines):
            engine._engine.quit()  # marks mock as not alive

        await patched_pool_manager.run_health_checks()
        # Should have replaced the dead engine
        status = patched_pool_manager.get_status()
        assert status["total"] >= 1
        # All remaining engines should be alive
        for e in patched_pool_manager._all_engines:
            assert e.is_alive is True
        await patched_pool_manager.stop()


# ---------------------------------------------------------------------------
# Task 2 (Issue 37): Scale-down logic
# ---------------------------------------------------------------------------


class TestScaleDown:
    async def test_scale_down_removes_idle_engine(self, app_config):
        """An idle engine beyond the timeout should be stopped and removed."""
        from matlab_mcp.pool.manager import EnginePoolManager

        # Use min=1, max=3 so scale-down can remove above min
        app_config.pool = PoolConfig(min_engines=1, max_engines=3, scale_down_idle_timeout=900)
        PatchedWrapper = _patched_engine_wrapper_factory(app_config.pool, app_config.workspace)

        manager = EnginePoolManager(app_config)

        def patched_make_engine():
            engine_id = f"engine-{manager._next_id}"
            manager._next_id += 1
            return PatchedWrapper(engine_id, manager._pool_config, manager._workspace_config)

        manager._make_engine = patched_make_engine

        await manager.start()
        # Scale up to 3 engines by acquiring then releasing
        e1 = await manager.acquire()
        e2 = await manager.acquire()
        e3 = await manager.acquire()
        await manager.release(e1)
        await manager.release(e2)
        await manager.release(e3)
        assert manager.get_status()["total"] == 3

        # Force ALL idle engines' _idle_since far into the past to exceed scale_down_idle_timeout.
        # The scale-down condition uses len(to_keep)+busy_count >= min_engines, so at least
        # one engine must stay in to_keep before any can be removed. Setting all to long-idle
        # ensures the second and beyond get pruned.
        for eng in list(manager._all_engines):
            eng._idle_since = time.monotonic() - 1000  # 1000s > 900s timeout

        before_total = manager.get_status()["total"]
        await manager.run_health_checks()
        after_total = manager.get_status()["total"]

        # At least one engine should have been removed (min_engines=1, had 3)
        assert after_total < before_total
        assert after_total >= 1  # must respect min_engines
        await manager.stop()

    async def test_scale_down_respects_min_engines(self, app_config):
        """Idle engines at or below min_engines must not be removed."""
        from matlab_mcp.pool.manager import EnginePoolManager

        app_config.pool = PoolConfig(min_engines=2, max_engines=4, scale_down_idle_timeout=900)
        PatchedWrapper = _patched_engine_wrapper_factory(app_config.pool, app_config.workspace)

        manager = EnginePoolManager(app_config)

        def patched_make_engine():
            engine_id = f"engine-{manager._next_id}"
            manager._next_id += 1
            return PatchedWrapper(engine_id, manager._pool_config, manager._workspace_config)

        manager._make_engine = patched_make_engine

        await manager.start()
        # Bring up to exactly min_engines (2) — scale up if needed
        e1 = await manager.acquire()
        e2 = await manager.acquire()
        await manager.release(e1)
        await manager.release(e2)
        assert manager.get_status()["total"] == 2

        # Force all engines to appear long-idle beyond scale_down_idle_timeout
        for eng in list(manager._all_engines):
            eng._idle_since = time.monotonic() - 2000

        before_total = manager.get_status()["total"]
        await manager.run_health_checks()
        after_total = manager.get_status()["total"]

        # None should be removed because we are at min_engines (2)
        assert after_total == before_total
        assert after_total == 2
        await manager.stop()

    async def test_scale_down_only_targets_idle_engines(self, app_config):
        """Busy engines must never be removed; only idle-beyond-timeout engines above min."""
        from matlab_mcp.pool.manager import EnginePoolManager

        app_config.pool = PoolConfig(min_engines=1, max_engines=4, scale_down_idle_timeout=900)
        PatchedWrapper = _patched_engine_wrapper_factory(app_config.pool, app_config.workspace)

        manager = EnginePoolManager(app_config)

        def patched_make_engine():
            engine_id = f"engine-{manager._next_id}"
            manager._next_id += 1
            return PatchedWrapper(engine_id, manager._pool_config, manager._workspace_config)

        manager._make_engine = patched_make_engine

        await manager.start()
        # Scale up to 3 engines
        e1 = await manager.acquire()
        e2 = await manager.acquire()
        e3 = await manager.acquire()
        # Keep e1 busy (do not release)
        # Release e2 and e3 and force them to appear long-idle
        await manager.release(e2)
        await manager.release(e3)

        for eng in list(manager._all_engines):
            if eng.state == EngineState.IDLE:
                eng._idle_since = time.monotonic() - 2000

        busy_before = manager.get_status()["busy"]
        assert busy_before == 1

        await manager.run_health_checks()

        # The busy engine must still be tracked (busy engines are never drained from _all_engines)
        # Busy count should remain at 1
        assert manager.get_status()["busy"] == 1

        # Release the busy engine to clean up
        await manager.release(e1)
        await manager.stop()
