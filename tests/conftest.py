"""Shared test fixtures for matlab-mcp-server."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from matlab_mcp.config import AppConfig, ExecutionConfig, PoolConfig, WorkspaceConfig
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    config = tmp_path / "config.yaml"
    config.write_text(
        "server:\n"
        "  name: test-server\n"
        "  transport: stdio\n"
        "pool:\n"
        "  min_engines: 1\n"
        "  max_engines: 2\n"
    )
    return config


def make_mock_pool():
    """Create a minimal mock engine pool using the MockMatlabEngine.

    Returns (MockPool, wrapper, mock_engine_inner) — same shape as the
    local _make_mock_pool helpers that previously lived in individual test
    files.
    """
    from tests.mocks.matlab_engine_mock import MockMatlabEngine

    mock_engine_inner = MockMatlabEngine()
    pool_cfg = PoolConfig(min_engines=1, max_engines=2)
    workspace_cfg = WorkspaceConfig()
    wrapper = MatlabEngineWrapper("engine-0", pool_cfg, workspace_cfg)
    wrapper._engine = mock_engine_inner
    wrapper._state = EngineState.IDLE

    class MockPool:
        async def acquire(self):
            wrapper.mark_busy()
            return wrapper

        async def release(self, engine):
            engine.mark_idle()

    return MockPool(), wrapper, mock_engine_inner


@pytest.fixture
def mock_pool():
    """Shared mock MATLAB engine pool for tests that don't need real engines."""
    pool, wrapper, inner = make_mock_pool()
    return pool, wrapper, inner
