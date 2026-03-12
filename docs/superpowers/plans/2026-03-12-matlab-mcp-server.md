# MATLAB MCP Server Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python MCP server that exposes MATLAB engine capabilities (code execution, toolbox discovery, code checking, interactive Plotly plots) to any AI agent, with an elastic engine pool for multi-user concurrent access.

**Architecture:** Two-layer Python process — FastMCP server layer handles MCP protocol/tools/sessions, MATLAB Pool Manager handles elastic engine pool/job scheduling/toolbox discovery. Communication via in-process async queues. Single deployable process.

**Tech Stack:** Python 3.9+, FastMCP (MCP Python SDK), pydantic, pyyaml, Pillow, matlab.engine

**Spec:** `docs/superpowers/specs/2026-03-12-matlab-mcp-server-design.md`

---

## Chunk 1: Foundation — Project Scaffolding & Configuration

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `config.yaml`
- Create: `custom_tools.yaml`
- Create: `src/matlab_mcp/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "matlab-mcp-server"
version = "0.1.0"
description = "MCP server exposing MATLAB capabilities to AI agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.9"
dependencies = [
    "fastmcp>=2.0.0,<3.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "Pillow>=9.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
]

[project.scripts]
matlab-mcp = "matlab_mcp.server:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py39"
line-length = 100
```

- [ ] **Step 2: Create default config.yaml**

Use the exact config block from the spec (lines 398-473).

- [ ] **Step 3: Create custom_tools.yaml with example**

```yaml
# Custom MATLAB tool definitions
# Each tool becomes a first-class MCP tool with proper schema
tools: []
  # Example:
  # - name: run_simulation
  #   matlab_function: mylib.run_sim
  #   description: "Run custom physics simulation"
  #   parameters:
  #     - name: model_name
  #       type: string
  #       required: true
  #     - name: duration
  #       type: double
  #       default: 100.0
  #   returns: "Struct with fields: time, state, energy"
```

- [ ] **Step 4: Create package init and test conftest**

`src/matlab_mcp/__init__.py`:
```python
"""MATLAB MCP Server — Expose MATLAB capabilities to AI agents via MCP."""

__version__ = "0.1.0"
```

`tests/__init__.py`: empty file.

`tests/conftest.py`:
```python
"""Shared test fixtures for matlab-mcp-server."""

import pytest
from pathlib import Path

@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    """Create a minimal config.yaml for testing."""
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
```

- [ ] **Step 5: Create all package directories with __init__.py**

Create empty `__init__.py` in each subpackage:
- `src/matlab_mcp/pool/__init__.py`
- `src/matlab_mcp/jobs/__init__.py`
- `src/matlab_mcp/tools/__init__.py`
- `src/matlab_mcp/output/__init__.py`
- `src/matlab_mcp/session/__init__.py`
- `src/matlab_mcp/security/__init__.py`
- `tests/mocks/__init__.py`

- [ ] **Step 6: Install project in dev mode and verify**

Run: `cd matlab-mcp-server-python && pip install -e ".[dev]"`
Expected: successful install

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with pyproject.toml and package structure"
```

---

### Task 2: Configuration System

**Files:**
- Create: `src/matlab_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config loading**

`tests/test_config.py`:
```python
"""Tests for configuration loading, validation, and env overrides."""

import os
import platform
import pytest
from pathlib import Path

from matlab_mcp.config import (
    ServerConfig,
    PoolConfig,
    ExecutionConfig,
    WorkspaceConfig,
    ToolboxesConfig,
    SecurityConfig,
    CodeCheckerConfig,
    OutputConfig,
    SessionsConfig,
    AppConfig,
    load_config,
)


class TestDefaultConfig:
    """Config should have sensible defaults without any YAML file."""

    def test_default_server_config(self):
        cfg = ServerConfig()
        assert cfg.name == "matlab-mcp-server"
        assert cfg.transport == "stdio"
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8765
        assert cfg.log_level == "info"

    def test_default_pool_config(self):
        cfg = PoolConfig()
        assert cfg.min_engines == 2
        assert cfg.max_engines == 10
        assert cfg.scale_down_idle_timeout == 900
        assert cfg.engine_start_timeout == 120
        assert cfg.health_check_interval == 60
        assert cfg.proactive_warmup_threshold == 0.8
        assert cfg.queue_max_size == 50
        assert cfg.matlab_root is None

    def test_macos_max_engines_warning(self):
        """On macOS, max_engines > 4 should trigger a warning."""
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test")
        cfg = PoolConfig(max_engines=8)
        assert cfg.max_engines == 8  # still allowed, just warns

    def test_default_execution_config(self):
        cfg = ExecutionConfig()
        assert cfg.sync_timeout == 30
        assert cfg.max_execution_time == 86400
        assert cfg.workspace_isolation is True
        assert cfg.engine_affinity is False

    def test_default_security_config(self):
        cfg = SecurityConfig()
        assert cfg.blocked_functions_enabled is True
        assert "system" in cfg.blocked_functions
        assert cfg.max_upload_size_mb == 100

    def test_default_output_config(self):
        cfg = OutputConfig()
        assert cfg.plotly_conversion is True
        assert cfg.static_image_format == "png"
        assert cfg.thumbnail_enabled is True


class TestLoadConfig:
    """Config loads from YAML with env var overrides."""

    def test_load_from_yaml(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "server:\n"
            "  name: my-server\n"
            "  transport: sse\n"
            "  port: 9999\n"
            "pool:\n"
            "  min_engines: 4\n"
            "  max_engines: 20\n"
        )
        cfg = load_config(config_file)
        assert cfg.server.name == "my-server"
        assert cfg.server.transport == "sse"
        assert cfg.server.port == 9999
        assert cfg.pool.min_engines == 4
        assert cfg.pool.max_engines == 20

    def test_env_var_override(self, tmp_path: Path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("pool:\n  max_engines: 5\n")
        monkeypatch.setenv("MATLAB_MCP_POOL_MAX_ENGINES", "15")
        cfg = load_config(config_file)
        assert cfg.pool.max_engines == 15

    def test_relative_paths_resolved(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "server:\n"
            "  result_dir: ./results\n"
            "  log_file: ./logs/server.log\n"
            "execution:\n"
            "  temp_dir: ./temp\n"
        )
        cfg = load_config(config_file)
        assert cfg.server.result_dir.is_absolute()
        assert cfg.server.log_file.is_absolute()
        assert cfg.execution.temp_dir.is_absolute()

    def test_missing_config_uses_defaults(self):
        cfg = load_config(None)
        assert cfg.server.name == "matlab-mcp-server"
        assert cfg.pool.min_engines == 2

    def test_invalid_transport_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server:\n  transport: websocket\n")
        with pytest.raises(Exception):
            load_config(config_file)

    def test_min_engines_exceeds_max_rejected(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "pool:\n  min_engines: 10\n  max_engines: 5\n"
        )
        with pytest.raises(Exception):
            load_config(config_file)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'matlab_mcp.config'`

- [ ] **Step 3: Implement config.py**

`src/matlab_mcp/config.py`:
```python
"""Configuration loading, validation, and environment variable overrides."""

from __future__ import annotations

import logging
import os
import platform
import warnings
from pathlib import Path
from typing import Any, List, Literal, Optional

import yaml
from pydantic import BaseModel, field_validator, model_validator

logger = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    name: str = "matlab-mcp-server"
    transport: Literal["stdio", "sse"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_file: Path = Path("./logs/server.log")
    result_dir: Path = Path("./results")
    drain_timeout_seconds: int = 300


class PoolConfig(BaseModel):
    min_engines: int = 2
    max_engines: int = 10
    scale_down_idle_timeout: int = 900
    engine_start_timeout: int = 120
    health_check_interval: int = 60
    proactive_warmup_threshold: float = 0.8
    queue_max_size: int = 50
    matlab_root: Optional[Path] = None

    @model_validator(mode="after")
    def warn_macos_engines(self) -> "PoolConfig":
        if platform.system() == "Darwin" and self.max_engines > 4:
            warnings.warn(
                f"max_engines={self.max_engines} on macOS may cause instability. "
                "Recommended max is 4.",
                stacklevel=2,
            )
        return self


class ExecutionConfig(BaseModel):
    sync_timeout: int = 30
    max_execution_time: int = 86400
    workspace_isolation: bool = True
    engine_affinity: bool = False
    temp_dir: Path = Path("./temp")
    temp_cleanup_on_disconnect: bool = True


class WorkspaceConfig(BaseModel):
    default_paths: List[str] = []
    startup_commands: List[str] = ["format long"]


class ToolboxesConfig(BaseModel):
    mode: Literal["whitelist", "blacklist", "all"] = "whitelist"
    list: List[str] = []


class CustomToolsConfig(BaseModel):
    config_file: Path = Path("./custom_tools.yaml")


class SecurityConfig(BaseModel):
    blocked_functions_enabled: bool = True
    blocked_functions: List[str] = ["system", "unix", "dos", "!"]
    max_upload_size_mb: int = 100
    require_proxy_auth: bool = False


class CodeCheckerConfig(BaseModel):
    enabled: bool = True
    auto_check_before_execute: bool = False
    severity_levels: List[str] = ["error", "warning"]


class OutputConfig(BaseModel):
    plotly_conversion: bool = True
    static_image_format: Literal["png", "jpg", "svg"] = "png"
    static_image_dpi: int = 150
    thumbnail_enabled: bool = True
    thumbnail_max_width: int = 400
    large_result_threshold: int = 10000
    max_inline_text_length: int = 50000


class SessionsConfig(BaseModel):
    max_sessions: int = 50
    session_timeout: int = 3600
    job_retention_seconds: int = 86400


class AppConfig(BaseModel):
    server: ServerConfig = ServerConfig()
    pool: PoolConfig = PoolConfig()
    execution: ExecutionConfig = ExecutionConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    toolboxes: ToolboxesConfig = ToolboxesConfig()
    custom_tools: CustomToolsConfig = CustomToolsConfig()
    security: SecurityConfig = SecurityConfig()
    code_checker: CodeCheckerConfig = CodeCheckerConfig()
    output: OutputConfig = OutputConfig()
    sessions: SessionsConfig = SessionsConfig()

    @model_validator(mode="after")
    def validate_pool_bounds(self) -> "AppConfig":
        if self.pool.min_engines > self.pool.max_engines:
            raise ValueError(
                f"min_engines ({self.pool.min_engines}) cannot exceed "
                f"max_engines ({self.pool.max_engines})"
            )
        return self


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Override config values from MATLAB_MCP_* environment variables."""
    prefix = "MATLAB_MCP_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("_")
        d = data
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        # Try to parse as int/float/bool
        final_key = parts[-1]
        if value.lower() in ("true", "false"):
            d[final_key] = value.lower() == "true"
        else:
            try:
                d[final_key] = int(value)
            except ValueError:
                try:
                    d[final_key] = float(value)
                except ValueError:
                    d[final_key] = value
    return data


def _resolve_paths(cfg: AppConfig, base_dir: Path) -> AppConfig:
    """Resolve relative paths to absolute, relative to config file directory."""
    def resolve(p: Path) -> Path:
        if not p.is_absolute():
            return (base_dir / p).resolve()
        return p

    cfg.server.log_file = resolve(cfg.server.log_file)
    cfg.server.result_dir = resolve(cfg.server.result_dir)
    cfg.execution.temp_dir = resolve(cfg.execution.temp_dir)
    cfg.custom_tools.config_file = resolve(cfg.custom_tools.config_file)
    return cfg


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """Load config from YAML file with env var overrides."""
    data: dict[str, Any] = {}
    base_dir = Path.cwd()

    if config_path is not None:
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            base_dir = config_path.parent.resolve()

    data = _apply_env_overrides(data)
    cfg = AppConfig(**data)
    cfg = _resolve_paths(cfg, base_dir)
    return cfg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/config.py tests/test_config.py
git commit -m "feat: configuration system with YAML loading, pydantic validation, env overrides"
```

---

### Task 3: MATLAB Engine Mock

**Files:**
- Create: `tests/mocks/matlab_engine_mock.py`
- Create: `tests/test_engine_mock.py`

- [ ] **Step 1: Write failing tests for the mock**

`tests/test_engine_mock.py`:
```python
"""Tests for the MATLAB engine mock used in CI without MATLAB."""

import pytest
from tests.mocks.matlab_engine_mock import MockMatlabEngine, start_matlab


class TestMockEngine:
    def test_start_returns_engine(self):
        engine = start_matlab()
        assert isinstance(engine, MockMatlabEngine)

    def test_eval_simple(self):
        engine = start_matlab()
        engine.eval("x = 42;", nargout=0)

    def test_eval_returns_output(self):
        engine = start_matlab()
        result = engine.eval("disp('hello')", nargout=0)
        # Mock captures output
        assert engine.last_output is not None

    def test_workspace_access(self):
        engine = start_matlab()
        engine.workspace["x"] = 42.0
        assert engine.workspace["x"] == 42.0

    def test_eval_background(self):
        engine = start_matlab()
        future = engine.eval("pause(0.1)", nargout=0, background=True)
        result = future.result(timeout=5.0)

    def test_eval_error(self):
        engine = start_matlab()
        with pytest.raises(Exception):
            engine.eval("error('test error')", nargout=0)

    def test_quit(self):
        engine = start_matlab()
        engine.quit()
        assert not engine.is_alive

    def test_health_check(self):
        engine = start_matlab()
        engine.eval("1", nargout=0)

    def test_clear_workspace(self):
        engine = start_matlab()
        engine.workspace["x"] = 1
        engine.eval("clear all", nargout=0)
        assert len(engine.workspace) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_engine_mock.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the mock**

`tests/mocks/matlab_engine_mock.py`:
```python
"""Mock matlab.engine for testing without a MATLAB installation.

Simulates the core matlab.engine Python API surface used by the server:
- start_matlab() → MockMatlabEngine
- engine.eval(code, nargout=0, background=False)
- engine.workspace (dict-like)
- engine.quit()
- Async futures via background=True
"""

from __future__ import annotations

import re
import threading
import time
from concurrent.futures import Future
from typing import Any, Dict, Optional


class MatlabExecutionError(Exception):
    """Raised when MATLAB code execution fails."""
    pass


class MockWorkspace:
    """Dict-like workspace mirroring MATLAB engine workspace behavior."""

    def __init__(self) -> None:
        self._vars: Dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self._vars[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._vars[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._vars

    def __len__(self) -> int:
        return len(self._vars)

    def keys(self) -> list:
        return list(self._vars.keys())

    def clear(self) -> None:
        self._vars.clear()


class MockFuture:
    """Simulates matlab.engine FutureResult."""

    def __init__(self, fn, args, kwargs):
        self._future: Future = Future()
        self._cancelled = False

        def run():
            try:
                result = fn(*args, **kwargs)
                self._future.set_result(result)
            except Exception as e:
                self._future.set_exception(e)

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._future.result(timeout=timeout)

    def cancel(self) -> bool:
        self._cancelled = True
        return self._future.cancel()

    def done(self) -> bool:
        return self._future.done()


class MockMatlabEngine:
    """Mock MATLAB engine for testing."""

    def __init__(self) -> None:
        self.workspace = MockWorkspace()
        self.is_alive: bool = True
        self.last_output: Optional[str] = None
        self._path: list[str] = []

    def eval(self, code: str, nargout: int = 0, background: bool = False) -> Any:
        if not self.is_alive:
            raise MatlabExecutionError("Engine is not running")

        if background:
            return MockFuture(self._execute, (code, nargout), {})
        return self._execute(code, nargout)

    def _execute(self, code: str, nargout: int) -> Any:
        """Simulate MATLAB code execution."""
        # Simulate error()
        error_match = re.search(r"error\(['\"](.+?)['\"]\)", code)
        if error_match:
            raise MatlabExecutionError(error_match.group(1))

        # Simulate clear all
        if "clear all" in code or "clear" == code.strip():
            self.workspace.clear()
            self.last_output = ""
            return None

        # Simulate disp()
        disp_match = re.search(r"disp\(['\"](.+?)['\"]\)", code)
        if disp_match:
            self.last_output = disp_match.group(1)
            return self.last_output if nargout > 0 else None

        # Simulate pause()
        pause_match = re.search(r"pause\(([\d.]+)\)", code)
        if pause_match:
            time.sleep(float(pause_match.group(1)))
            self.last_output = ""
            return None

        # Simulate simple assignment: x = <number>
        assign_match = re.search(r"(\w+)\s*=\s*([\d.]+)", code)
        if assign_match:
            var_name = assign_match.group(1)
            value = float(assign_match.group(2))
            self.workspace[var_name] = value
            self.last_output = f"{var_name} = {value}"
            return value if nargout > 0 else None

        # Default: just record execution
        self.last_output = ""
        return None

    def quit(self) -> None:
        self.is_alive = False
        self.workspace.clear()

    def addpath(self, path: str) -> None:
        if path not in self._path:
            self._path.append(path)

    def restoredefaultpath(self) -> None:
        self._path.clear()


def start_matlab() -> MockMatlabEngine:
    """Mimic matlab.engine.start_matlab()."""
    return MockMatlabEngine()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_engine_mock.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/mocks/matlab_engine_mock.py tests/test_engine_mock.py
git commit -m "feat: MATLAB engine mock for CI testing without MATLAB"
```

---

## Chunk 2: Engine Pool & Security

### Task 4: Engine Wrapper

**Files:**
- Create: `src/matlab_mcp/pool/engine.py`
- Create: `tests/test_pool.py`

- [ ] **Step 1: Write failing tests for engine wrapper**

`tests/test_pool.py`:
```python
"""Tests for MATLAB engine pool components."""

import pytest
from unittest.mock import patch

from matlab_mcp.config import PoolConfig, WorkspaceConfig, ExecutionConfig
from matlab_mcp.pool.engine import MatlabEngineWrapper, EngineState


@pytest.fixture
def mock_engine_module():
    """Patch matlab.engine with our mock."""
    from tests.mocks import matlab_engine_mock
    with patch("matlab_mcp.pool.engine.matlab_engine", matlab_engine_mock):
        yield matlab_engine_mock


class TestEngineWrapper:
    def test_start_engine(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(),
        )
        wrapper.start()
        assert wrapper.state == EngineState.IDLE
        assert wrapper.is_alive

    def test_stop_engine(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(),
        )
        wrapper.start()
        wrapper.stop()
        assert wrapper.state == EngineState.STOPPED
        assert not wrapper.is_alive

    def test_health_check_alive(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(),
        )
        wrapper.start()
        assert wrapper.health_check() is True

    def test_execute_sync(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(),
        )
        wrapper.start()
        result = wrapper.execute("x = 42;")
        assert result is not None

    def test_reset_workspace(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(default_paths=["/test/path"]),
        )
        wrapper.start()
        wrapper.execute("x = 42;")
        wrapper.reset_workspace()
        assert len(wrapper._engine.workspace) == 0

    def test_engine_state_transitions(self, mock_engine_module):
        wrapper = MatlabEngineWrapper(
            engine_id="eng-1",
            pool_config=PoolConfig(min_engines=1, max_engines=1),
            workspace_config=WorkspaceConfig(),
        )
        assert wrapper.state == EngineState.STOPPED
        wrapper.start()
        assert wrapper.state == EngineState.IDLE
        wrapper.mark_busy()
        assert wrapper.state == EngineState.BUSY
        wrapper.mark_idle()
        assert wrapper.state == EngineState.IDLE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pool.py -v`
Expected: FAIL

- [ ] **Step 3: Implement engine wrapper**

`src/matlab_mcp/pool/engine.py`:
```python
"""Single MATLAB engine wrapper — start, stop, health check, reset, execute."""

from __future__ import annotations

import enum
import logging
import time
from typing import Any, Optional

from matlab_mcp.config import PoolConfig, WorkspaceConfig

logger = logging.getLogger(__name__)

# Lazy import — allows mock injection in tests
matlab_engine: Any = None


def _get_matlab_engine():
    global matlab_engine
    if matlab_engine is None:
        import matlab.engine as _me
        matlab_engine = _me
    return matlab_engine


class EngineState(enum.Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    IDLE = "idle"
    BUSY = "busy"


class MatlabEngineWrapper:
    """Wraps a single MATLAB engine instance with lifecycle management."""

    def __init__(
        self,
        engine_id: str,
        pool_config: PoolConfig,
        workspace_config: WorkspaceConfig,
    ) -> None:
        self.engine_id = engine_id
        self._pool_config = pool_config
        self._workspace_config = workspace_config
        self._engine: Any = None
        self.state = EngineState.STOPPED
        self._started_at: Optional[float] = None
        self._last_used: Optional[float] = None

    @property
    def is_alive(self) -> bool:
        return self._engine is not None and self.state not in (
            EngineState.STOPPED,
        )

    def start(self) -> None:
        """Start the MATLAB engine."""
        self.state = EngineState.STARTING
        me = _get_matlab_engine()
        try:
            self._engine = me.start_matlab()
            # Apply default paths
            for path in self._workspace_config.default_paths:
                self._engine.addpath(path)
            # Run startup commands
            for cmd in self._workspace_config.startup_commands:
                self._engine.eval(cmd, nargout=0)
            self.state = EngineState.IDLE
            self._started_at = time.time()
            self._last_used = time.time()
            logger.info("Engine %s started", self.engine_id)
        except Exception:
            self.state = EngineState.STOPPED
            logger.exception("Failed to start engine %s", self.engine_id)
            raise

    def stop(self) -> None:
        """Stop the MATLAB engine."""
        if self._engine is not None:
            try:
                self._engine.quit()
            except Exception:
                logger.warning("Error stopping engine %s", self.engine_id)
            self._engine = None
        self.state = EngineState.STOPPED
        logger.info("Engine %s stopped", self.engine_id)

    def health_check(self) -> bool:
        """Ping the engine to check it's alive."""
        if self._engine is None:
            return False
        try:
            self._engine.eval("1", nargout=0)
            return True
        except Exception:
            logger.warning("Engine %s failed health check", self.engine_id)
            return False

    def execute(self, code: str, nargout: int = 0, background: bool = False) -> Any:
        """Execute MATLAB code on this engine."""
        if self._engine is None:
            raise RuntimeError(f"Engine {self.engine_id} is not running")
        self._last_used = time.time()
        return self._engine.eval(code, nargout=nargout, background=background)

    def reset_workspace(self) -> None:
        """Clear workspace and restore default state."""
        if self._engine is None:
            return
        self._engine.eval("clear all; clear global; clear functions;", nargout=0)
        try:
            self._engine.eval("fclose all;", nargout=0)
        except Exception:
            pass
        self._engine.restoredefaultpath()
        for path in self._workspace_config.default_paths:
            self._engine.addpath(path)
        for cmd in self._workspace_config.startup_commands:
            self._engine.eval(cmd, nargout=0)

    def mark_busy(self) -> None:
        self.state = EngineState.BUSY
        self._last_used = time.time()

    def mark_idle(self) -> None:
        self.state = EngineState.IDLE
        self._last_used = time.time()

    @property
    def idle_seconds(self) -> float:
        if self._last_used is None:
            return 0.0
        return time.time() - self._last_used
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pool.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/pool/engine.py tests/test_pool.py
git commit -m "feat: MATLAB engine wrapper with lifecycle, health check, workspace reset"
```

---

### Task 5: Pool Manager

**Files:**
- Create: `src/matlab_mcp/pool/manager.py`
- Modify: `tests/test_pool.py` (add pool manager tests)

- [ ] **Step 1: Write failing tests for pool manager**

Append to `tests/test_pool.py`:
```python
import asyncio
from matlab_mcp.pool.manager import EnginePoolManager
from matlab_mcp.config import AppConfig


@pytest.fixture
def app_config():
    return AppConfig(
        pool=PoolConfig(min_engines=2, max_engines=4),
        workspace=WorkspaceConfig(),
        execution=ExecutionConfig(),
    )


class TestPoolManager:
    async def test_start_pool(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        assert pool.total_engines == app_config.pool.min_engines
        assert pool.available_engines == app_config.pool.min_engines
        await pool.stop()

    async def test_acquire_release_engine(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        engine = await pool.acquire()
        assert engine is not None
        assert engine.state == EngineState.BUSY
        assert pool.available_engines == app_config.pool.min_engines - 1
        await pool.release(engine)
        assert engine.state == EngineState.IDLE
        assert pool.available_engines == app_config.pool.min_engines
        await pool.stop()

    async def test_scale_up_on_demand(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        # Acquire all min_engines
        engines = []
        for _ in range(app_config.pool.min_engines):
            engines.append(await pool.acquire())
        # Next acquire should trigger scale-up
        extra = await pool.acquire()
        assert pool.total_engines == app_config.pool.min_engines + 1
        for e in engines:
            await pool.release(e)
        await pool.release(extra)
        await pool.stop()

    async def test_max_engines_ceiling(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        engines = []
        for _ in range(app_config.pool.max_engines):
            engines.append(await pool.acquire())
        assert pool.total_engines == app_config.pool.max_engines
        # Next acquire with no timeout should raise or queue
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(pool.acquire(), timeout=0.5)
        for e in engines:
            await pool.release(e)
        await pool.stop()

    async def test_pool_status(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        status = pool.get_status()
        assert status["total"] == app_config.pool.min_engines
        assert status["available"] == app_config.pool.min_engines
        assert status["busy"] == 0
        await pool.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pool.py::TestPoolManager -v`
Expected: FAIL

- [ ] **Step 3: Implement pool manager**

`src/matlab_mcp/pool/manager.py`:
```python
"""Elastic MATLAB engine pool manager."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from matlab_mcp.config import AppConfig
from matlab_mcp.pool.engine import EngineState, MatlabEngineWrapper

logger = logging.getLogger(__name__)


class EnginePoolManager:
    """Manages an elastic pool of MATLAB engines."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._engines: Dict[str, MatlabEngineWrapper] = {}
        self._available: asyncio.Queue[MatlabEngineWrapper] = asyncio.Queue()
        self._engine_counter = 0
        self._lock = asyncio.Lock()
        self._health_task: Optional[asyncio.Task] = None
        self._scale_down_task: Optional[asyncio.Task] = None

    @property
    def total_engines(self) -> int:
        return len(self._engines)

    @property
    def available_engines(self) -> int:
        return self._available.qsize()

    @property
    def busy_engines(self) -> int:
        return sum(
            1 for e in self._engines.values() if e.state == EngineState.BUSY
        )

    async def start(self) -> None:
        """Start the pool with min_engines."""
        loop = asyncio.get_running_loop()
        tasks = []
        for _ in range(self._config.pool.min_engines):
            tasks.append(loop.run_in_executor(None, self._create_engine))
        engines = await asyncio.gather(*tasks, return_exceptions=True)
        started = 0
        for engine in engines:
            if isinstance(engine, MatlabEngineWrapper):
                self._engines[engine.engine_id] = engine
                await self._available.put(engine)
                started += 1
            else:
                logger.error("Failed to start engine: %s", engine)
        if started < self._config.pool.min_engines:
            raise RuntimeError(
                f"Only {started}/{self._config.pool.min_engines} engines started"
            )
        logger.info("Pool started with %d engines", started)

    def _create_engine(self) -> MatlabEngineWrapper:
        """Create and start a new engine (runs in thread)."""
        self._engine_counter += 1
        eid = f"eng-{self._engine_counter}"
        wrapper = MatlabEngineWrapper(
            engine_id=eid,
            pool_config=self._config.pool,
            workspace_config=self._config.workspace,
        )
        wrapper.start()
        return wrapper

    async def acquire(self) -> MatlabEngineWrapper:
        """Acquire an engine from the pool. Scales up if needed."""
        # Try to get an available engine immediately
        try:
            engine = self._available.get_nowait()
            engine.mark_busy()
            if self._config.execution.workspace_isolation:
                await asyncio.get_running_loop().run_in_executor(
                    None, engine.reset_workspace
                )
            return engine
        except asyncio.QueueEmpty:
            pass

        # Scale up if possible
        async with self._lock:
            if self.total_engines < self._config.pool.max_engines:
                loop = asyncio.get_running_loop()
                engine = await loop.run_in_executor(None, self._create_engine)
                self._engines[engine.engine_id] = engine
                engine.mark_busy()
                if self._config.execution.workspace_isolation:
                    await loop.run_in_executor(None, engine.reset_workspace)
                return engine

        # Pool at max — wait for an engine to become available
        engine = await self._available.get()
        engine.mark_busy()
        if self._config.execution.workspace_isolation:
            await asyncio.get_running_loop().run_in_executor(
                None, engine.reset_workspace
            )
        return engine

    async def release(self, engine: MatlabEngineWrapper) -> None:
        """Return an engine to the pool."""
        engine.mark_idle()
        await self._available.put(engine)

    async def stop(self) -> None:
        """Stop all engines and shut down the pool."""
        for engine in self._engines.values():
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, engine.stop
                )
            except Exception:
                logger.warning("Error stopping engine %s", engine.engine_id)
        self._engines.clear()
        # Drain the queue
        while not self._available.empty():
            try:
                self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("Pool stopped")

    async def run_health_checks(self) -> None:
        """Check all idle engines, replace dead ones."""
        loop = asyncio.get_running_loop()
        for engine in list(self._engines.values()):
            if engine.state != EngineState.IDLE:
                continue
            alive = await loop.run_in_executor(None, engine.health_check)
            if not alive:
                logger.warning("Engine %s failed health check, replacing", engine.engine_id)
                self._engines.pop(engine.engine_id, None)
                if self.total_engines < self._config.pool.min_engines:
                    try:
                        new_engine = await loop.run_in_executor(None, self._create_engine)
                        self._engines[new_engine.engine_id] = new_engine
                        await self._available.put(new_engine)
                    except Exception:
                        logger.error("Failed to replace engine %s", engine.engine_id)

        # Scale down idle engines beyond min
        idle_engines = [
            e for e in self._engines.values()
            if e.state == EngineState.IDLE
            and e.idle_seconds > self._config.pool.scale_down_idle_timeout
        ]
        for engine in idle_engines:
            if self.total_engines <= self._config.pool.min_engines:
                break
            logger.info("Scaling down idle engine %s", engine.engine_id)
            self._engines.pop(engine.engine_id, None)
            await loop.run_in_executor(None, engine.stop)

    def get_status(self) -> Dict[str, Any]:
        """Return pool status summary."""
        return {
            "total": self.total_engines,
            "available": self.available_engines,
            "busy": self.busy_engines,
            "max": self._config.pool.max_engines,
            "queued_requests": 0,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pool.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/pool/manager.py tests/test_pool.py
git commit -m "feat: elastic engine pool manager with scale-up, acquire/release"
```

---

### Task 6: Security Validator

**Files:**
- Create: `src/matlab_mcp/security/validator.py`
- Create: `tests/test_security.py`

- [ ] **Step 1: Write failing tests**

`tests/test_security.py`:
```python
"""Tests for security validation — function blocklist and filename sanitization."""

import pytest
from matlab_mcp.config import SecurityConfig
from matlab_mcp.security.validator import SecurityValidator, BlockedFunctionError


@pytest.fixture
def validator():
    return SecurityValidator(SecurityConfig())


class TestFunctionBlocklist:
    def test_blocks_system_call(self, validator):
        with pytest.raises(BlockedFunctionError, match="system"):
            validator.check_code("system('ls')")

    def test_blocks_unix_call(self, validator):
        with pytest.raises(BlockedFunctionError):
            validator.check_code("unix('rm -rf /')")

    def test_blocks_dos_call(self, validator):
        with pytest.raises(BlockedFunctionError):
            validator.check_code("dos('dir')")

    def test_blocks_shell_escape(self, validator):
        with pytest.raises(BlockedFunctionError):
            validator.check_code("!ls -la")

    def test_allows_normal_code(self, validator):
        validator.check_code("x = fft(signal);")

    def test_allows_system_in_string(self, validator):
        # "system" inside a string literal should not trigger
        validator.check_code("disp('the system is running')")

    def test_disabled_blocklist(self):
        cfg = SecurityConfig(blocked_functions_enabled=False)
        v = SecurityValidator(cfg)
        v.check_code("system('ls')")  # should not raise


class TestFilenameSanitization:
    def test_valid_filename(self, validator):
        assert validator.sanitize_filename("data.csv") == "data.csv"

    def test_valid_filename_with_dashes(self, validator):
        assert validator.sanitize_filename("my-file_v2.mat") == "my-file_v2.mat"

    def test_rejects_path_traversal(self, validator):
        with pytest.raises(ValueError, match="Invalid filename"):
            validator.sanitize_filename("../../etc/passwd")

    def test_rejects_slash(self, validator):
        with pytest.raises(ValueError, match="Invalid filename"):
            validator.sanitize_filename("path/to/file.csv")

    def test_rejects_backslash(self, validator):
        with pytest.raises(ValueError, match="Invalid filename"):
            validator.sanitize_filename("path\\file.csv")

    def test_rejects_empty(self, validator):
        with pytest.raises(ValueError, match="Invalid filename"):
            validator.sanitize_filename("")

    def test_rejects_special_chars(self, validator):
        with pytest.raises(ValueError):
            validator.sanitize_filename("file;rm.csv")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_security.py -v`
Expected: FAIL

- [ ] **Step 3: Implement security validator**

`src/matlab_mcp/security/validator.py`:
```python
"""Security validation — function blocklist and filename sanitization."""

from __future__ import annotations

import re
from matlab_mcp.config import SecurityConfig


class BlockedFunctionError(Exception):
    """Raised when code contains a blocked MATLAB function call."""

    def __init__(self, function_name: str, code_snippet: str = ""):
        self.function_name = function_name
        super().__init__(
            f"Blocked function '{function_name}' detected in code. "
            "This function is not allowed for security reasons."
        )


# Regex to match MATLAB string/char literals so we can exclude them
_STRING_PATTERN = re.compile(r"'[^']*'|\"[^\"]*\"")


class SecurityValidator:
    """Validates MATLAB code and filenames for security."""

    def __init__(self, config: SecurityConfig) -> None:
        self._config = config

    def check_code(self, code: str) -> None:
        """Check code for blocked function calls. Raises BlockedFunctionError."""
        if not self._config.blocked_functions_enabled:
            return

        # Remove string literals to avoid false positives
        cleaned = _STRING_PATTERN.sub("", code)

        for func in self._config.blocked_functions:
            if func == "!":
                # Shell escape: line starting with !
                if re.search(r"(?m)^\s*!", cleaned):
                    raise BlockedFunctionError("!", code[:50])
            else:
                # Match function call pattern: func_name(
                if re.search(rf"\b{re.escape(func)}\s*\(", cleaned):
                    raise BlockedFunctionError(func, code[:50])

    def sanitize_filename(self, filename: str) -> str:
        """Validate and sanitize a filename. Raises ValueError if invalid."""
        if not filename:
            raise ValueError("Invalid filename: empty string")

        # Only allow alphanumeric, dash, underscore, dot
        if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
            raise ValueError(f"Invalid filename: '{filename}'. Only alphanumeric, '-', '_', '.' allowed.")

        # Reject path traversal
        if ".." in filename:
            raise ValueError(f"Invalid filename: '{filename}'. Path traversal not allowed.")

        return filename
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_security.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/security/validator.py tests/test_security.py
git commit -m "feat: security validator with function blocklist and filename sanitization"
```

---

## Chunk 3: Jobs & Sessions

### Task 7: Job Models & Tracker

**Files:**
- Create: `src/matlab_mcp/jobs/models.py`
- Create: `src/matlab_mcp/jobs/tracker.py`
- Create: `tests/test_jobs.py`

- [ ] **Step 1: Write failing tests**

`tests/test_jobs.py`:
```python
"""Tests for job models, tracker, and executor."""

import time
import pytest
from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.config import SessionsConfig


class TestJobModel:
    def test_create_job(self):
        job = Job(session_id="s-1", code="x = 1;")
        assert job.status == JobStatus.PENDING
        assert job.job_id.startswith("j-")
        assert job.session_id == "s-1"
        assert job.code == "x = 1;"

    def test_job_transitions(self):
        job = Job(session_id="s-1", code="x = 1;")
        job.mark_running("eng-1")
        assert job.status == JobStatus.RUNNING
        assert job.engine_id == "eng-1"
        job.mark_completed({"text": "x = 1"})
        assert job.status == JobStatus.COMPLETED
        assert job.result == {"text": "x = 1"}

    def test_job_failure(self):
        job = Job(session_id="s-1", code="error('bad')")
        job.mark_running("eng-1")
        job.mark_failed("MatlabExecutionError", "bad")
        assert job.status == JobStatus.FAILED
        assert job.error["type"] == "MatlabExecutionError"

    def test_job_cancel_from_pending(self):
        job = Job(session_id="s-1", code="x = 1;")
        job.mark_cancelled()
        assert job.status == JobStatus.CANCELLED

    def test_job_cancel_from_running(self):
        job = Job(session_id="s-1", code="x = 1;")
        job.mark_running("eng-1")
        job.mark_cancelled()
        assert job.status == JobStatus.CANCELLED


class TestJobTracker:
    def test_create_and_get_job(self):
        tracker = JobTracker(SessionsConfig())
        job = tracker.create_job("s-1", "x = 1;")
        retrieved = tracker.get_job(job.job_id)
        assert retrieved is job

    def test_list_session_jobs(self):
        tracker = JobTracker(SessionsConfig())
        tracker.create_job("s-1", "x = 1;")
        tracker.create_job("s-1", "y = 2;")
        tracker.create_job("s-2", "z = 3;")
        jobs = tracker.list_jobs("s-1")
        assert len(jobs) == 2

    def test_get_unknown_job_returns_none(self):
        tracker = JobTracker(SessionsConfig())
        assert tracker.get_job("j-nonexistent") is None

    def test_prune_old_jobs(self):
        cfg = SessionsConfig(job_retention_seconds=0)
        tracker = JobTracker(cfg)
        job = tracker.create_job("s-1", "x = 1;")
        job.mark_running("eng-1")
        job.mark_completed({"text": "done"})
        # Force created_at to the past
        job.completed_at = time.time() - 1
        tracker.prune()
        assert tracker.get_job(job.job_id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement job models**

`src/matlab_mcp/jobs/models.py`:
```python
"""Job data model — status, result, progress, lifecycle."""

from __future__ import annotations

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class JobStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    session_id: str
    code: str
    job_id: str = field(default_factory=lambda: f"j-{uuid.uuid4().hex[:12]}")
    status: JobStatus = JobStatus.PENDING
    engine_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    future: Any = None  # matlab.engine future for async jobs

    @property
    def elapsed_seconds(self) -> float:
        start = self.started_at or self.created_at
        end = self.completed_at or time.time()
        return round(end - start, 2)

    def mark_running(self, engine_id: str) -> None:
        self.status = JobStatus.RUNNING
        self.engine_id = engine_id
        self.started_at = time.time()

    def mark_completed(self, result: Dict[str, Any]) -> None:
        self.status = JobStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()

    def mark_failed(self, error_type: str, message: str, matlab_id: str = "", stack_trace: str = "") -> None:
        self.status = JobStatus.FAILED
        self.error = {
            "type": error_type,
            "message": message,
            "matlab_id": matlab_id,
            "stack_trace": stack_trace,
        }
        self.completed_at = time.time()

    def mark_cancelled(self) -> None:
        self.status = JobStatus.CANCELLED
        self.completed_at = time.time()
```

- [ ] **Step 4: Implement job tracker**

`src/matlab_mcp/jobs/tracker.py`:
```python
"""Job store — create, retrieve, list, prune jobs."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from matlab_mcp.config import SessionsConfig
from matlab_mcp.jobs.models import Job, JobStatus

logger = logging.getLogger(__name__)


class JobTracker:
    """In-memory job store with session scoping and pruning."""

    def __init__(self, config: SessionsConfig) -> None:
        self._config = config
        self._jobs: Dict[str, Job] = {}

    def create_job(self, session_id: str, code: str) -> Job:
        job = Job(session_id=session_id, code=code)
        self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self, session_id: str) -> List[Job]:
        return [j for j in self._jobs.values() if j.session_id == session_id]

    def prune(self) -> int:
        """Remove completed/failed jobs older than retention period. Returns count removed."""
        cutoff = time.time() - self._config.job_retention_seconds
        terminal = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
        to_remove = [
            jid
            for jid, job in self._jobs.items()
            if job.status in terminal
            and job.completed_at is not None
            and job.completed_at < cutoff
        ]
        for jid in to_remove:
            del self._jobs[jid]
        if to_remove:
            logger.info("Pruned %d old jobs", len(to_remove))
        return len(to_remove)

    def has_active_jobs(self, session_id: str) -> bool:
        active = {JobStatus.PENDING, JobStatus.RUNNING}
        return any(
            j.session_id == session_id and j.status in active
            for j in self._jobs.values()
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_jobs.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/matlab_mcp/jobs/models.py src/matlab_mcp/jobs/tracker.py tests/test_jobs.py
git commit -m "feat: job models and tracker with lifecycle, session scoping, pruning"
```

---

### Task 8: Job Executor

**Files:**
- Create: `src/matlab_mcp/jobs/executor.py`
- Modify: `tests/test_jobs.py` (add executor tests)

- [ ] **Step 1: Write failing tests for executor**

Append to `tests/test_jobs.py`:
```python
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.pool.manager import EnginePoolManager
from matlab_mcp.config import AppConfig, PoolConfig, ExecutionConfig, WorkspaceConfig, SessionsConfig


@pytest.fixture
def mock_engine_module():
    from tests.mocks import matlab_engine_mock
    with patch("matlab_mcp.pool.engine.matlab_engine", matlab_engine_mock):
        yield


@pytest.fixture
def app_config():
    return AppConfig(
        pool=PoolConfig(min_engines=1, max_engines=2),
        execution=ExecutionConfig(sync_timeout=2),
        workspace=WorkspaceConfig(),
        sessions=SessionsConfig(),
    )


class TestJobExecutor:
    async def test_sync_execution(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        tracker = JobTracker(app_config.sessions)
        executor = JobExecutor(pool, tracker, app_config)
        result = await executor.execute("s-1", "x = 42;")
        assert result["status"] == "completed"
        await pool.stop()

    async def test_async_promotion(self, mock_engine_module, app_config):
        """Job exceeding sync_timeout gets promoted to async."""
        app_config.execution.sync_timeout = 0  # instant promotion
        pool = EnginePoolManager(app_config)
        await pool.start()
        tracker = JobTracker(app_config.sessions)
        executor = JobExecutor(pool, tracker, app_config)
        result = await executor.execute("s-1", "pause(0.5)")
        assert result["status"] == "async"
        assert "job_id" in result
        await pool.stop()

    async def test_execution_error(self, mock_engine_module, app_config):
        pool = EnginePoolManager(app_config)
        await pool.start()
        tracker = JobTracker(app_config.sessions)
        executor = JobExecutor(pool, tracker, app_config)
        result = await executor.execute("s-1", "error('test fail')")
        assert result["status"] == "failed"
        assert "error" in result
        await pool.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_jobs.py::TestJobExecutor -v`
Expected: FAIL

- [ ] **Step 3: Implement executor**

`src/matlab_mcp/jobs/executor.py`:
```python
"""Job executor — sync/async execution with timeout promotion."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from matlab_mcp.config import AppConfig
from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.pool.engine import MatlabEngineWrapper
from matlab_mcp.pool.manager import EnginePoolManager

logger = logging.getLogger(__name__)


class JobExecutor:
    """Executes MATLAB code with hybrid sync/async promotion."""

    def __init__(
        self,
        pool: EnginePoolManager,
        tracker: JobTracker,
        config: AppConfig,
    ) -> None:
        self._pool = pool
        self._tracker = tracker
        self._config = config

    def _inject_job_context(self, engine: MatlabEngineWrapper, job: Job, temp_dir: Path) -> None:
        """Inject __mcp_job_id__ and set MCP_TEMP_DIR before user code runs."""
        engine.execute(f"__mcp_job_id__ = '{job.job_id}';", nargout=0)
        os.environ["MCP_TEMP_DIR"] = str(temp_dir)

    async def execute(
        self, session_id: str, code: str, temp_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute code. Returns result inline if fast, or job_id if promoted to async."""
        job = self._tracker.create_job(session_id, code)
        engine = await self._pool.acquire()
        job.mark_running(engine.engine_id)

        if temp_dir is None:
            temp_dir = self._config.execution.temp_dir

        try:
            # Inject job context into MATLAB workspace
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: self._inject_job_context(engine, job, temp_dir)
            )

            # Start background execution
            future = await loop.run_in_executor(
                None, lambda: engine.execute(code, nargout=0, background=True)
            )
            job.future = future

            # Wait for sync_timeout
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: future.result(timeout=self._config.execution.sync_timeout)),
                    timeout=self._config.execution.sync_timeout + 1,
                )
                # Completed within timeout — return inline
                output = self._build_result(engine, result, job, temp_dir)
                job.mark_completed(output)
                await self._pool.release(engine)
                return {
                    "status": "completed",
                    "job_id": job.job_id,
                    "output": output,
                    "execution_time_seconds": job.elapsed_seconds,
                }
            except (asyncio.TimeoutError, Exception) as e:
                if isinstance(e, asyncio.TimeoutError) or (
                    hasattr(e, '__class__') and 'Timeout' in type(e).__name__
                ):
                    # Promote to async
                    logger.info("Job %s promoted to async", job.job_id)
                    asyncio.create_task(
                        self._wait_for_completion(job, engine, future, temp_dir)
                    )
                    return {
                        "status": "async",
                        "job_id": job.job_id,
                        "message": f"Job promoted to async after {self._config.execution.sync_timeout}s. "
                                   "Use get_job_status to check progress.",
                    }
                else:
                    raise
        except Exception as e:
            error_type = type(e).__name__
            job.mark_failed(error_type, str(e))
            await self._pool.release(engine)
            return {
                "status": "failed",
                "job_id": job.job_id,
                "error": job.error,
                "execution_time_seconds": job.elapsed_seconds,
            }

    async def _wait_for_completion(
        self,
        job: Job,
        engine: MatlabEngineWrapper,
        future: Any,
        temp_dir: Path,
    ) -> None:
        """Background task: wait for async job to complete."""
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, lambda: future.result(timeout=self._config.execution.max_execution_time)
            )
            output = self._build_result(engine, result, job, temp_dir)
            job.mark_completed(output)
        except Exception as e:
            job.mark_failed(type(e).__name__, str(e))
        finally:
            await self._pool.release(engine)

    def _build_result(
        self, engine: MatlabEngineWrapper, raw_result: Any, job: Job, temp_dir: Path,
    ) -> Dict[str, Any]:
        """Build structured result dict from engine execution output."""
        text = ""
        if hasattr(engine, '_engine') and hasattr(engine._engine, 'last_output'):
            text = engine._engine.last_output or ""

        figures = []
        # Attempt Plotly figure conversion if configured
        if self._config.output.plotly_conversion:
            try:
                result_dir = self._config.server.result_dir / job.job_id
                result_dir.mkdir(parents=True, exist_ok=True)
                plotly_path = result_dir / "figure_1.json"
                png_path = result_dir / f"figure_1.{self._config.output.static_image_format}"
                # Call mcp_fig2plotly.m to convert open figures
                engine.execute(
                    f"try; mcp_fig2plotly(gcf, '{plotly_path}'); "
                    f"saveas(gcf, '{png_path}'); close(gcf); "
                    f"catch; end;",
                    nargout=0,
                )
                from matlab_mcp.output.plotly_convert import load_plotly_json
                from matlab_mcp.output.thumbnail import generate_thumbnail
                plotly_json = load_plotly_json(plotly_path)
                thumbnail = None
                if png_path.exists():
                    thumbnail = generate_thumbnail(png_path, self._config.output.thumbnail_max_width)
                if plotly_json or png_path.exists():
                    figures.append({
                        "plotly_json": plotly_json,
                        "thumbnail_base64": thumbnail,
                        "file_path": str(png_path) if png_path.exists() else None,
                        "conversion_error": None if plotly_json else "Plotly conversion failed",
                    })
            except Exception:
                pass  # No open figures or conversion failed — that's fine

        return {
            "text": text,
            "variables": {},
            "figures": figures,
            "files": [],
            "warnings": [],
            "errors": [],
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jobs.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/jobs/executor.py tests/test_jobs.py
git commit -m "feat: job executor with sync/async hybrid execution and timeout promotion"
```

---

### Task 9: Session Manager

**Files:**
- Create: `src/matlab_mcp/session/manager.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write failing tests**

`tests/test_session.py`:
```python
"""Tests for session manager."""

import pytest
from pathlib import Path
from matlab_mcp.session.manager import SessionManager, Session
from matlab_mcp.config import AppConfig, SessionsConfig, ExecutionConfig


@pytest.fixture
def session_manager(tmp_path):
    cfg = AppConfig(
        execution=ExecutionConfig(temp_dir=tmp_path / "temp"),
        sessions=SessionsConfig(max_sessions=5, session_timeout=3600),
    )
    return SessionManager(cfg)


class TestSessionManager:
    def test_create_session(self, session_manager):
        session = session_manager.create_session()
        assert session.session_id is not None
        assert session.temp_dir.exists()

    def test_get_session(self, session_manager):
        session = session_manager.create_session()
        retrieved = session_manager.get_session(session.session_id)
        assert retrieved is session

    def test_max_sessions_enforced(self, session_manager):
        for _ in range(5):
            session_manager.create_session()
        with pytest.raises(RuntimeError, match="max sessions"):
            session_manager.create_session()

    def test_destroy_session_cleans_temp(self, session_manager):
        session = session_manager.create_session()
        temp_dir = session.temp_dir
        # Create a file in the temp dir
        (temp_dir / "test.txt").write_text("hello")
        session_manager.destroy_session(session.session_id)
        assert not temp_dir.exists()
        assert session_manager.get_session(session.session_id) is None

    def test_session_touch_updates_last_active(self, session_manager):
        session = session_manager.create_session()
        first_active = session.last_active
        import time
        time.sleep(0.01)
        session.touch()
        assert session.last_active > first_active

    def test_get_or_create_default_session(self, session_manager):
        """For stdio mode, get the default session."""
        session = session_manager.get_or_create_default()
        session2 = session_manager.get_or_create_default()
        assert session is session2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL

- [ ] **Step 3: Implement session manager**

`src/matlab_mcp/session/manager.py`:
```python
"""Session lifecycle — creation, temp dirs, cleanup."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from matlab_mcp.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class Session:
    session_id: str
    temp_dir: Path
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_active = time.time()

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active


class SessionManager:
    """Manages user sessions with temp directories and cleanup."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._sessions: Dict[str, Session] = {}
        self._default_session_id: Optional[str] = None
        self._base_temp_dir = config.execution.temp_dir

    def create_session(self) -> Session:
        if len(self._sessions) >= self._config.sessions.max_sessions:
            raise RuntimeError(
                f"Cannot create session: max sessions ({self._config.sessions.max_sessions}) reached"
            )
        sid = f"s-{uuid.uuid4().hex[:12]}"
        temp_dir = self._base_temp_dir / sid
        temp_dir.mkdir(parents=True, exist_ok=True)
        session = Session(session_id=sid, temp_dir=temp_dir)
        self._sessions[sid] = session
        logger.info("Session %s created", sid)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def get_or_create_default(self) -> Session:
        """Get or create the default session (for stdio single-user mode)."""
        if self._default_session_id and self._default_session_id in self._sessions:
            return self._sessions[self._default_session_id]
        session = self.create_session()
        self._default_session_id = session.session_id
        return session

    def destroy_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        if session.temp_dir.exists():
            shutil.rmtree(session.temp_dir, ignore_errors=True)
        logger.info("Session %s destroyed", session_id)

    def cleanup_expired(self, has_active_jobs_fn=None) -> int:
        """Remove sessions that have been idle beyond session_timeout.
        Skips sessions with active jobs if has_active_jobs_fn is provided."""
        timeout = self._config.sessions.session_timeout
        expired = [
            sid
            for sid, s in self._sessions.items()
            if s.idle_seconds > timeout
        ]
        removed = 0
        for sid in expired:
            if has_active_jobs_fn and has_active_jobs_fn(sid):
                continue
            self.destroy_session(sid)
            removed += 1
        return removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/session/manager.py tests/test_session.py
git commit -m "feat: session manager with temp directories, cleanup, default session"
```

---

## Chunk 4: MCP Tools

### Task 10: Core MCP Tools (execute_code, check_code, get_workspace)

**Files:**
- Create: `src/matlab_mcp/tools/core.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write failing tests**

`tests/test_tools.py`:
```python
"""Tests for MCP tool implementations."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from matlab_mcp.config import AppConfig, PoolConfig, WorkspaceConfig, ExecutionConfig, SessionsConfig, SecurityConfig
from matlab_mcp.pool.manager import EnginePoolManager
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.session.manager import SessionManager
from matlab_mcp.security.validator import SecurityValidator


@pytest.fixture
def mock_engine_module():
    from tests.mocks import matlab_engine_mock
    with patch("matlab_mcp.pool.engine.matlab_engine", matlab_engine_mock):
        yield


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(
        pool=PoolConfig(min_engines=1, max_engines=2),
        execution=ExecutionConfig(sync_timeout=5, temp_dir=tmp_path / "temp"),
        workspace=WorkspaceConfig(),
        sessions=SessionsConfig(),
        security=SecurityConfig(),
    )


@pytest.fixture
async def server_deps(mock_engine_module, app_config):
    """Set up all server dependencies."""
    pool = EnginePoolManager(app_config)
    await pool.start()
    tracker = JobTracker(app_config.sessions)
    executor = JobExecutor(pool, tracker, app_config)
    session_mgr = SessionManager(app_config)
    security = SecurityValidator(app_config.security)
    yield {
        "pool": pool,
        "tracker": tracker,
        "executor": executor,
        "session_mgr": session_mgr,
        "security": security,
        "config": app_config,
    }
    await pool.stop()


class TestExecuteCodeTool:
    async def test_execute_simple_code(self, server_deps):
        from matlab_mcp.tools.core import execute_code_impl
        session = server_deps["session_mgr"].create_session()
        result = await execute_code_impl(
            code="x = 42;",
            session_id=session.session_id,
            executor=server_deps["executor"],
            security=server_deps["security"],
        )
        assert result["status"] in ("completed", "async")

    async def test_execute_blocked_code(self, server_deps):
        from matlab_mcp.tools.core import execute_code_impl
        session = server_deps["session_mgr"].create_session()
        result = await execute_code_impl(
            code="system('ls')",
            session_id=session.session_id,
            executor=server_deps["executor"],
            security=server_deps["security"],
        )
        assert result["status"] == "failed"
        assert "blocked" in result["error"]["message"].lower() or "Blocked" in result["error"]["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL

- [ ] **Step 3: Implement core tools**

`src/matlab_mcp/tools/core.py`:
```python
"""Core MCP tools — execute_code, check_code, get_workspace."""

from __future__ import annotations

import logging
from typing import Any, Dict

from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.security.validator import BlockedFunctionError, SecurityValidator

logger = logging.getLogger(__name__)


async def execute_code_impl(
    code: str,
    session_id: str,
    executor: JobExecutor,
    security: SecurityValidator,
) -> Dict[str, Any]:
    """Execute MATLAB code with security check and sync/async handling."""
    try:
        security.check_code(code)
    except BlockedFunctionError as e:
        return {
            "status": "failed",
            "error": {
                "type": "ValidationError",
                "message": str(e),
                "matlab_id": "",
                "stack_trace": "",
            },
            "execution_time_seconds": 0.0,
        }

    return await executor.execute(session_id, code)


async def check_code_impl(
    code: str,
    session_id: str,
    executor: JobExecutor,
    temp_dir: Any,
) -> Dict[str, Any]:
    """Run MATLAB checkcode/mlint on a code string using mcp_checkcode.m helper."""
    import json
    import uuid
    from pathlib import Path

    temp_dir = Path(temp_dir)
    temp_file = temp_dir / f"_mcp_check_{uuid.uuid4().hex[:8]}.m"

    try:
        temp_file.write_text(code)
        # Use the mcp_checkcode.m helper which returns structured JSON
        check_cmd = f"result_json = mcp_checkcode('{temp_file}'); disp(result_json)"
        result = await executor.execute(session_id, check_cmd)
        # Parse the JSON output from mcp_checkcode.m
        text = result.get("output", {}).get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"issues": [], "summary": {"errors": 0, "warnings": 0}, "raw": text}
    finally:
        temp_file.unlink(missing_ok=True)


async def get_workspace_impl(
    session_id: str,
    executor: JobExecutor,
) -> Dict[str, Any]:
    """Get variables in the current MATLAB workspace."""
    code = "whos"
    return await executor.execute(session_id, code)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tools.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/tools/core.py tests/test_tools.py
git commit -m "feat: core MCP tools — execute_code, check_code, get_workspace"
```

---

### Task 11: Job & Discovery & File & Admin & Custom Tools

**Files:**
- Create: `src/matlab_mcp/tools/jobs.py`
- Create: `src/matlab_mcp/tools/discovery.py`
- Create: `src/matlab_mcp/tools/files.py`
- Create: `src/matlab_mcp/tools/admin.py`
- Create: `src/matlab_mcp/tools/custom.py`

- [ ] **Step 1: Implement job tools**

`src/matlab_mcp/tools/jobs.py`:
```python
"""MCP tools for async job management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from matlab_mcp.jobs.models import Job, JobStatus
from matlab_mcp.jobs.tracker import JobTracker


def get_job_status_impl(job_id: str, tracker: JobTracker, temp_dir: Path) -> Dict[str, Any]:
    """Get status of an async job, including progress if available."""
    job = tracker.get_job(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}

    result: Dict[str, Any] = {
        "job_id": job.job_id,
        "status": job.status.value,
        "elapsed_seconds": job.elapsed_seconds,
    }

    if job.status == JobStatus.RUNNING:
        result["engine_id"] = job.engine_id
        # Check for progress file
        progress_file = temp_dir / f"{job.job_id}.progress"
        if progress_file.exists():
            try:
                progress = json.loads(progress_file.read_text())
                result["progress"] = progress
            except (json.JSONDecodeError, OSError):
                pass
    elif job.status == JobStatus.COMPLETED:
        result["message"] = "Job completed. Use get_job_result to retrieve output."
    elif job.status == JobStatus.PENDING:
        result["message"] = "Job is queued."

    return result


def get_job_result_impl(job_id: str, tracker: JobTracker) -> Dict[str, Any]:
    """Retrieve full result of a completed job."""
    job = tracker.get_job(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}
    if job.status == JobStatus.COMPLETED:
        return {
            "status": "completed",
            "job_id": job.job_id,
            "output": job.result,
            "execution_time_seconds": job.elapsed_seconds,
        }
    elif job.status == JobStatus.FAILED:
        return {
            "status": "failed",
            "job_id": job.job_id,
            "error": job.error,
            "execution_time_seconds": job.elapsed_seconds,
        }
    else:
        return {
            "job_id": job.job_id,
            "status": job.status.value,
            "message": "Job is not yet complete.",
        }


def cancel_job_impl(job_id: str, tracker: JobTracker) -> Dict[str, Any]:
    """Cancel a pending or running job."""
    job = tracker.get_job(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return {"error": f"Job {job_id} is already in terminal state: {job.status.value}"}
    if job.future is not None:
        try:
            job.future.cancel()
        except Exception:
            pass
    job.mark_cancelled()
    return {"job_id": job.job_id, "status": "cancelled"}


def list_jobs_impl(session_id: str, tracker: JobTracker) -> List[Dict[str, Any]]:
    """List all jobs for a session."""
    jobs = tracker.list_jobs(session_id)
    return [
        {
            "job_id": j.job_id,
            "status": j.status.value,
            "code": j.code[:100],
            "elapsed_seconds": j.elapsed_seconds,
        }
        for j in jobs
    ]
```

- [ ] **Step 2: Implement discovery tools**

`src/matlab_mcp/tools/discovery.py`:
```python
"""MCP tools for MATLAB toolbox and function discovery."""

from __future__ import annotations

from typing import Any, Dict, List

from matlab_mcp.config import ToolboxesConfig
from matlab_mcp.jobs.executor import JobExecutor


async def list_toolboxes_impl(
    session_id: str,
    executor: JobExecutor,
    toolbox_config: ToolboxesConfig,
) -> Dict[str, Any]:
    """List installed and exposed toolboxes."""
    result = await executor.execute(session_id, "ver")
    # Filter based on whitelist/blacklist config
    return {
        "toolboxes": result.get("output", {}).get("text", ""),
        "mode": toolbox_config.mode,
        "configured_list": toolbox_config.list,
    }


async def list_functions_impl(
    toolbox_name: str,
    session_id: str,
    executor: JobExecutor,
) -> Dict[str, Any]:
    """List functions in a specific toolbox."""
    code = f"help {toolbox_name}"
    return await executor.execute(session_id, code)


async def get_help_impl(
    function_name: str,
    session_id: str,
    executor: JobExecutor,
) -> Dict[str, Any]:
    """Get MATLAB help text for a function."""
    code = f"help {function_name}"
    return await executor.execute(session_id, code)
```

- [ ] **Step 3: Implement file tools**

`src/matlab_mcp/tools/files.py`:
```python
"""MCP tools for file management within session temp directories."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List

from matlab_mcp.security.validator import SecurityValidator


def upload_data_impl(
    filename: str,
    content_base64: str,
    session_temp_dir: Path,
    security: SecurityValidator,
    max_size_mb: int,
) -> Dict[str, Any]:
    """Upload a file to the session temp directory."""
    safe_name = security.sanitize_filename(filename)
    data = base64.b64decode(content_base64)

    if len(data) > max_size_mb * 1024 * 1024:
        return {"error": f"File exceeds max upload size of {max_size_mb}MB"}

    filepath = session_temp_dir / safe_name
    filepath.write_bytes(data)
    return {
        "path": str(filepath),
        "size_bytes": len(data),
        "filename": safe_name,
    }


def delete_file_impl(
    filename: str,
    session_temp_dir: Path,
    security: SecurityValidator,
) -> Dict[str, Any]:
    """Delete a file from the session temp directory."""
    safe_name = security.sanitize_filename(filename)
    filepath = session_temp_dir / safe_name
    if not filepath.exists():
        return {"error": f"File '{safe_name}' not found"}
    filepath.unlink()
    return {"deleted": safe_name}


def list_files_impl(session_temp_dir: Path) -> List[Dict[str, Any]]:
    """List files in the session temp directory."""
    if not session_temp_dir.exists():
        return []
    return [
        {
            "name": f.name,
            "size_bytes": f.stat().st_size,
            "path": str(f),
        }
        for f in session_temp_dir.iterdir()
        if f.is_file()
    ]
```

- [ ] **Step 4: Implement admin and custom tools**

`src/matlab_mcp/tools/admin.py`:
```python
"""MCP admin tools — pool status."""

from __future__ import annotations

from typing import Any, Dict

from matlab_mcp.pool.manager import EnginePoolManager


def get_pool_status_impl(pool: EnginePoolManager) -> Dict[str, Any]:
    """Return engine pool status."""
    return pool.get_status()
```

`src/matlab_mcp/tools/custom.py`:
```python
"""Custom tool loader — reads custom_tools.yaml and registers MCP tools."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CustomToolParam(BaseModel):
    name: str
    type: str  # string, double, int, logical
    required: bool = False
    default: Any = None


class CustomToolDef(BaseModel):
    name: str
    matlab_function: str
    description: str
    parameters: List[CustomToolParam] = []
    returns: str = ""


def load_custom_tools(config_path: Path) -> List[CustomToolDef]:
    """Load custom tool definitions from YAML."""
    if not config_path.exists():
        logger.info("No custom tools file at %s", config_path)
        return []

    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    tools_data = data.get("tools", [])
    if not tools_data:
        return []

    tools = [CustomToolDef(**t) for t in tools_data]
    logger.info("Loaded %d custom tools from %s", len(tools), config_path)
    return tools


def make_custom_tool_handler(tool_def: CustomToolDef, server_state: Any):
    """Create a typed async handler for a custom tool (avoids **kwargs which FastMCP rejects)."""
    import inspect
    from fastmcp.server.context import Context

    # Build parameter list dynamically
    params = [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Context)]
    for p in tool_def.parameters:
        annotation = {"string": str, "double": float, "int": int, "logical": bool}.get(p.type, str)
        default = p.default if not p.required else inspect.Parameter.empty
        params.append(
            inspect.Parameter(p.name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation, default=default)
        )

    async def handler(*args, **kwargs):
        from matlab_mcp.tools import core
        ctx = kwargs.get("ctx") or args[0]
        session_id = server_state._get_session_id(ctx)
        # Build MATLAB function call from named args (skip ctx)
        call_args = []
        for p in tool_def.parameters:
            val = kwargs.get(p.name, p.default)
            call_args.append(f"'{val}'" if isinstance(val, str) else str(val))
        code = f"result = {tool_def.matlab_function}({', '.join(call_args)}); disp(result)"
        return await core.execute_code_impl(
            code=code,
            session_id=session_id,
            executor=server_state.executor,
            security=server_state.security,
        )

    # Set the signature so FastMCP can introspect it
    handler.__signature__ = inspect.Signature(params)
    handler.__name__ = tool_def.name
    handler.__doc__ = tool_def.description
    return handler
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/matlab_mcp/tools/
git commit -m "feat: MCP tools — jobs, discovery, files, admin, custom tool loader"
```

---

## Chunk 5: Output, MATLAB Helpers & Server Integration

### Task 12: Output Formatter & Thumbnail

**Files:**
- Create: `src/matlab_mcp/output/formatter.py`
- Create: `src/matlab_mcp/output/thumbnail.py`
- Create: `src/matlab_mcp/output/plotly_convert.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests for output**

`tests/test_output.py`:
```python
"""Tests for output formatting and thumbnail generation."""

import pytest
from pathlib import Path
from matlab_mcp.output.formatter import ResultFormatter
from matlab_mcp.config import OutputConfig


@pytest.fixture
def formatter():
    return ResultFormatter(OutputConfig())


class TestResultFormatter:
    def test_format_text_inline(self, formatter):
        result = formatter.format_text("hello world")
        assert result["text"] == "hello world"
        assert result["truncated"] is False

    def test_format_text_truncated(self, formatter, tmp_path):
        long_text = "x" * 60000
        result = formatter.format_text(long_text, save_dir=tmp_path)
        assert result["truncated"] is True
        assert result["file_path"] is not None

    def test_format_variables(self, formatter):
        vars_dict = {"x": 42.0, "y": "hello"}
        result = formatter.format_variables(vars_dict)
        assert "x" in result
        assert result["x"]["value"] == 42.0

    def test_build_success_response(self, formatter):
        resp = formatter.build_success_response(
            job_id="j-123",
            text="ans = 42",
            variables={"ans": 42.0},
            figures=[],
            files=[],
            warnings=[],
            execution_time=1.5,
        )
        assert resp["status"] == "completed"
        assert resp["job_id"] == "j-123"
        assert resp["output"]["text"] == "ans = 42"

    def test_build_error_response(self, formatter):
        resp = formatter.build_error_response(
            job_id="j-123",
            error_type="MatlabExecutionError",
            message="Undefined function",
            execution_time=0.1,
        )
        assert resp["status"] == "failed"
        assert resp["error"]["type"] == "MatlabExecutionError"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_output.py -v`
Expected: FAIL

- [ ] **Step 3: Implement formatter**

`src/matlab_mcp/output/formatter.py`:
```python
"""Result formatting — builds structured MCP responses."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from matlab_mcp.config import OutputConfig


class ResultFormatter:
    """Formats MATLAB execution results for MCP responses."""

    def __init__(self, config: OutputConfig) -> None:
        self._config = config

    def format_text(self, text: str, save_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Format text output, saving to file if too long."""
        if len(text) <= self._config.max_inline_text_length:
            return {"text": text, "truncated": False, "file_path": None}

        file_path = None
        if save_dir:
            file_path = save_dir / "output.txt"
            file_path.write_text(text)

        return {
            "text": text[: self._config.max_inline_text_length] + "\n... (truncated)",
            "truncated": True,
            "file_path": str(file_path) if file_path else None,
        }

    def format_variables(self, variables: Dict[str, Any]) -> Dict[str, Any]:
        """Format workspace variables into structured info."""
        result = {}
        for name, value in variables.items():
            var_info: Dict[str, Any] = {"value": value}
            if isinstance(value, (int, float)):
                var_info["type"] = "double"
                var_info["size"] = [1, 1]
            elif isinstance(value, str):
                var_info["type"] = "char"
                var_info["size"] = [1, len(value)]
            else:
                var_info["type"] = type(value).__name__
            result[name] = var_info
        return result

    def build_success_response(
        self,
        job_id: str,
        text: str,
        variables: Dict[str, Any],
        figures: List[Dict[str, Any]],
        files: List[Dict[str, Any]],
        warnings: List[str],
        execution_time: float,
        save_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        text_result = self.format_text(text, save_dir)
        return {
            "status": "completed",
            "job_id": job_id,
            "output": {
                "text": text_result["text"],
                "variables": self.format_variables(variables),
                "figures": figures,
                "files": files,
                "warnings": warnings,
                "errors": [],
            },
            "execution_time_seconds": execution_time,
        }

    def build_error_response(
        self,
        job_id: str,
        error_type: str,
        message: str,
        execution_time: float,
        matlab_id: str = "",
        stack_trace: str = "",
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "job_id": job_id,
            "error": {
                "type": error_type,
                "message": message,
                "matlab_id": matlab_id,
                "stack_trace": stack_trace,
            },
            "execution_time_seconds": execution_time,
        }
```

`src/matlab_mcp/output/thumbnail.py`:
```python
"""Thumbnail generation for MATLAB figures."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Optional


def generate_thumbnail(
    image_path: Path, max_width: int = 400
) -> Optional[str]:
    """Generate a base64-encoded thumbnail from an image file.
    Returns base64 string or None if Pillow is not available or image fails."""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            ratio = max_width / img.width
            if ratio < 1:
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None
```

`src/matlab_mcp/output/plotly_convert.py`:
```python
"""Python-side Plotly JSON handling — receives converted data from MATLAB helper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_plotly_json(json_path: Path) -> Optional[Dict[str, Any]]:
    """Load Plotly JSON generated by mcp_fig2plotly.m."""
    if not json_path.exists():
        return None
    try:
        with open(json_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_output.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/output/ tests/test_output.py
git commit -m "feat: output formatter, thumbnail generator, Plotly JSON loader"
```

---

### Task 13: MATLAB Helper Files

**Files:**
- Create: `src/matlab_mcp/matlab_helpers/mcp_fig2plotly.m`
- Create: `src/matlab_mcp/matlab_helpers/mcp_checkcode.m`
- Create: `src/matlab_mcp/matlab_helpers/mcp_progress.m`

- [ ] **Step 1: Create mcp_progress.m**

`src/matlab_mcp/matlab_helpers/mcp_progress.m`:
```matlab
function mcp_progress(job_id, percentage, message)
%MCP_PROGRESS Report job progress to the MCP server.
%   mcp_progress(job_id, percentage) reports progress percentage (0-100).
%   mcp_progress(job_id, percentage, message) includes a status message.
%
%   Example:
%     mcp_progress(__mcp_job_id__, 50, 'Iteration 500/1000')

    if nargin < 3
        message = '';
    end

    % Validate inputs
    percentage = max(0, min(100, percentage));

    % Build JSON
    progress = struct();
    progress.percentage = percentage;
    progress.message = message;
    progress.timestamp = datestr(now, 'yyyy-mm-ddTHH:MM:SS');

    json_str = jsonencode(progress);

    % Write to progress file (overwrite)
    temp_dir = getenv('MCP_TEMP_DIR');
    if isempty(temp_dir)
        warning('MCP_PROGRESS:NoTempDir', 'MCP_TEMP_DIR not set');
        return;
    end

    filepath = fullfile(temp_dir, [job_id '.progress']);
    fid = fopen(filepath, 'w');
    if fid == -1
        warning('MCP_PROGRESS:WriteError', 'Cannot write progress file');
        return;
    end
    fprintf(fid, '%s', json_str);
    fclose(fid);
end
```

- [ ] **Step 2: Create mcp_checkcode.m**

`src/matlab_mcp/matlab_helpers/mcp_checkcode.m`:
```matlab
function results = mcp_checkcode(file_path)
%MCP_CHECKCODE Run checkcode and return structured results as JSON.
%   results = mcp_checkcode(file_path) runs MATLAB's checkcode on the
%   specified .m file and returns a JSON string with structured results.

    info = checkcode(file_path, '-struct');

    issues = {};
    for i = 1:length(info)
        issue = struct();
        issue.line = info(i).line;
        issue.column = info(i).column(1);
        issue.message = info(i).message;
        issue.id = info(i).id;
        % All checkcode messages are warnings by definition
        issue.severity = 'warning';
        issues{end+1} = issue;
    end

    result = struct();
    result.issues = issues;
    result.summary = struct('errors', 0, 'warnings', 0);
    for i = 1:length(issues)
        if strcmp(issues{i}.severity, 'error')
            result.summary.errors = result.summary.errors + 1;
        else
            result.summary.warnings = result.summary.warnings + 1;
        end
    end

    results = jsonencode(result);
end
```

- [ ] **Step 3: Create mcp_fig2plotly.m**

`src/matlab_mcp/matlab_helpers/mcp_fig2plotly.m`:
```matlab
function plotly_json = mcp_fig2plotly(fig_handle, output_path)
%MCP_FIG2PLOTLY Convert a MATLAB figure to Plotly JSON format.
%   plotly_json = mcp_fig2plotly(fig_handle) converts the figure and
%   returns the Plotly JSON as a string.
%   mcp_fig2plotly(fig_handle, output_path) also saves to file.
%
%   Supported: line, scatter, bar, histogram, surface, contour, image.
%   Falls back gracefully for unsupported plot types.

    if nargin < 1 || isempty(fig_handle)
        fig_handle = gcf;
    end

    plotly_data = struct();
    plotly_data.data = {};
    plotly_data.layout = struct();

    % Get all axes in the figure
    all_axes = findobj(fig_handle, 'Type', 'axes');

    for ax_idx = 1:length(all_axes)
        ax = all_axes(ax_idx);

        % Get all children (plot objects)
        children = get(ax, 'Children');

        for ch_idx = 1:length(children)
            child = children(ch_idx);
            trace = convert_object(child);
            if ~isempty(trace)
                plotly_data.data{end+1} = trace;
            end
        end

        % Extract layout from first axes
        if ax_idx == 1
            plotly_data.layout.title = struct('text', get(get(ax, 'Title'), 'String'));
            plotly_data.layout.xaxis = struct('title', struct('text', get(get(ax, 'XLabel'), 'String')));
            plotly_data.layout.yaxis = struct('title', struct('text', get(get(ax, 'YLabel'), 'String')));
        end
    end

    plotly_json = jsonencode(plotly_data);

    if nargin >= 2 && ~isempty(output_path)
        fid = fopen(output_path, 'w');
        fprintf(fid, '%s', plotly_json);
        fclose(fid);
    end
end

function trace = convert_object(obj)
    trace = [];
    obj_type = get(obj, 'Type');

    switch obj_type
        case 'line'
            trace = struct();
            trace.type = 'scatter';
            trace.mode = 'lines';
            trace.x = get(obj, 'XData');
            trace.y = get(obj, 'YData');
            if ~isempty(get(obj, 'ZData'))
                trace.z = get(obj, 'ZData');
                trace.type = 'scatter3d';
            end
            trace.name = get(obj, 'DisplayName');

        case 'bar'
            trace = struct();
            trace.type = 'bar';
            trace.x = get(obj, 'XData');
            trace.y = get(obj, 'YData');
            trace.name = get(obj, 'DisplayName');

        case 'scatter'
            trace = struct();
            trace.type = 'scatter';
            trace.mode = 'markers';
            trace.x = get(obj, 'XData');
            trace.y = get(obj, 'YData');
            trace.name = get(obj, 'DisplayName');

        case 'surface'
            trace = struct();
            trace.type = 'surface';
            trace.x = get(obj, 'XData');
            trace.y = get(obj, 'YData');
            trace.z = get(obj, 'ZData');

        case 'image'
            trace = struct();
            trace.type = 'heatmap';
            trace.z = get(obj, 'CData');

        case 'histogram'
            trace = struct();
            trace.type = 'histogram';
            trace.x = get(obj, 'Data');

        otherwise
            % Unsupported type — skip
            trace = [];
    end
end
```

- [ ] **Step 4: Commit**

```bash
git add src/matlab_mcp/matlab_helpers/
git commit -m "feat: MATLAB helper files — mcp_progress, mcp_checkcode, mcp_fig2plotly"
```

---

### Task 14: MCP Server Entry Point

**Files:**
- Create: `src/matlab_mcp/server.py`

This is the main integration point that ties everything together with FastMCP.

- [ ] **Step 1: Implement server.py**

`src/matlab_mcp/server.py`:
```python
"""MCP server entry point — tool registration, startup, shutdown."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastmcp import FastMCP
from fastmcp.server.context import Context

from matlab_mcp.config import AppConfig, load_config
from matlab_mcp.jobs.executor import JobExecutor
from matlab_mcp.jobs.tracker import JobTracker
from matlab_mcp.output.formatter import ResultFormatter
from matlab_mcp.pool.manager import EnginePoolManager
from matlab_mcp.security.validator import SecurityValidator
from matlab_mcp.session.manager import SessionManager
from matlab_mcp.jobs.models import JobStatus
from matlab_mcp.tools import core, discovery, files, jobs, admin
from matlab_mcp.tools.custom import load_custom_tools

logger = logging.getLogger(__name__)


def _setup_logging(config: AppConfig) -> None:
    """Configure logging based on config."""
    level = getattr(logging, config.server.log_level.upper(), logging.INFO)
    log_file = config.server.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file)),
        ],
    )


class MatlabMCPServer:
    """Main server class tying all components together."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.pool = EnginePoolManager(config)
        self.tracker = JobTracker(config.sessions)
        self.executor = JobExecutor(self.pool, self.tracker, config)
        self.sessions = SessionManager(config)
        self.security = SecurityValidator(config.security)
        self.formatter = ResultFormatter(config.output)

    def _get_session_id(self, ctx: Context) -> str:
        """Get session ID from context, or use default for stdio."""
        if self.config.server.transport == "stdio":
            return self.sessions.get_or_create_default().session_id
        # For SSE, use the MCP session ID
        sid = ctx.session_id or "default"
        session = self.sessions.get_session(sid)
        if session is None:
            session = self.sessions.create_session()
        session.touch()
        return session.session_id

    def _get_temp_dir(self, session_id: str) -> Path:
        session = self.sessions.get_session(session_id)
        if session:
            return session.temp_dir
        return self.config.execution.temp_dir


def create_server(config: AppConfig) -> FastMCP:
    """Create and configure the FastMCP server with all tools."""

    server_state = MatlabMCPServer(config)

    @asynccontextmanager
    async def lifespan(mcp: FastMCP):
        """Server lifecycle — start pool, background tasks, drain on shutdown."""
        logger.info("Starting MATLAB MCP Server...")

        # Warn if SSE without proxy auth acknowledgement
        if config.server.transport == "sse" and not config.security.require_proxy_auth:
            logger.warning(
                "SSE transport active without require_proxy_auth=true. "
                "Ensure a reverse proxy with auth is in front of this server."
            )

        # Create directories
        config.server.result_dir.mkdir(parents=True, exist_ok=True)
        config.execution.temp_dir.mkdir(parents=True, exist_ok=True)

        # Add MATLAB helpers to path
        helpers_dir = Path(__file__).parent / "matlab_helpers"
        if helpers_dir.exists():
            # Will be added to each engine's path via workspace config
            config.workspace.default_paths.append(str(helpers_dir))

        # Start engine pool
        await server_state.pool.start()
        logger.info("Engine pool started")

        # Start background maintenance tasks
        async def health_check_loop():
            while True:
                await asyncio.sleep(config.pool.health_check_interval)
                await server_state.pool.run_health_checks()

        async def cleanup_loop():
            while True:
                await asyncio.sleep(60)  # check every minute
                server_state.sessions.cleanup_expired(
                    server_state.tracker.has_active_jobs
                )
                server_state.tracker.prune()

        bg_tasks = [
            asyncio.create_task(health_check_loop()),
            asyncio.create_task(cleanup_loop()),
        ]

        yield {"server": server_state}

        # Cancel background tasks
        for task in bg_tasks:
            task.cancel()

        # Graceful drain: wait for running jobs up to drain_timeout
        logger.info("Draining running jobs (timeout=%ds)...", config.server.drain_timeout_seconds)
        drain_start = asyncio.get_running_loop().time()
        while True:
            active = [
                j for j in server_state.tracker._jobs.values()
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            ]
            if not active:
                break
            elapsed = asyncio.get_running_loop().time() - drain_start
            if elapsed >= config.server.drain_timeout_seconds:
                logger.warning("Drain timeout reached, %d jobs still active", len(active))
                for j in active:
                    j.mark_cancelled()
                break
            await asyncio.sleep(1)

        await server_state.pool.stop()
        logger.info("Server stopped")

    mcp = FastMCP(name=config.server.name, lifespan=lifespan)

    # ── Core tools ───────────────────────────────────────────────

    @mcp.tool(
        name="execute_code",
        description="Execute MATLAB code. Fast commands return inline; long-running jobs auto-promote to async.",
    )
    async def execute_code(code: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        return await core.execute_code_impl(
            code=code,
            session_id=session_id,
            executor=server_state.executor,
            security=server_state.security,
        )

    @mcp.tool(
        name="check_code",
        description="Run MATLAB's checkcode/mlint on a code string. Returns warnings and errors.",
    )
    async def check_code(code: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(session_id)
        return await core.check_code_impl(code, session_id, server_state.executor, temp_dir)

    @mcp.tool(
        name="get_workspace",
        description="Show current variables in the MATLAB workspace for this session.",
    )
    async def get_workspace(ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        return await core.get_workspace_impl(session_id, server_state.executor)

    # ── Job tools ────────────────────────────────────────────────

    @mcp.tool(
        name="get_job_status",
        description="Check status and progress of an async MATLAB job.",
    )
    async def get_job_status(job_id: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(session_id)
        return jobs.get_job_status_impl(job_id, server_state.tracker, temp_dir)

    @mcp.tool(
        name="get_job_result",
        description="Retrieve the full result of a completed async job.",
    )
    async def get_job_result(job_id: str, ctx: Context) -> dict:
        return jobs.get_job_result_impl(job_id, server_state.tracker)

    @mcp.tool(
        name="cancel_job",
        description="Cancel a pending or running async job.",
    )
    async def cancel_job(job_id: str, ctx: Context) -> dict:
        return jobs.cancel_job_impl(job_id, server_state.tracker)

    @mcp.tool(
        name="list_jobs",
        description="List all MATLAB jobs for the current session.",
    )
    async def list_jobs(ctx: Context) -> list:
        session_id = server_state._get_session_id(ctx)
        return jobs.list_jobs_impl(session_id, server_state.tracker)

    # ── Discovery tools ──────────────────────────────────────────

    @mcp.tool(
        name="list_toolboxes",
        description="List installed and exposed MATLAB toolboxes.",
    )
    async def list_toolboxes(ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        return await discovery.list_toolboxes_impl(
            session_id, server_state.executor, config.toolboxes
        )

    @mcp.tool(
        name="list_functions",
        description="List functions available in a specific MATLAB toolbox.",
    )
    async def list_functions(toolbox_name: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        return await discovery.list_functions_impl(toolbox_name, session_id, server_state.executor)

    @mcp.tool(
        name="get_help",
        description="Get MATLAB help text for any function.",
    )
    async def get_help(function_name: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        return await discovery.get_help_impl(function_name, session_id, server_state.executor)

    # ── File tools ───────────────────────────────────────────────

    @mcp.tool(
        name="upload_data",
        description="Upload a file (CSV, MAT, etc.) to the session temp directory. Content must be base64 encoded.",
    )
    async def upload_data(filename: str, content_base64: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(session_id)
        return files.upload_data_impl(
            filename, content_base64, temp_dir,
            server_state.security, config.security.max_upload_size_mb,
        )

    @mcp.tool(
        name="delete_file",
        description="Delete a file from the session temp directory.",
    )
    async def delete_file(filename: str, ctx: Context) -> dict:
        session_id = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(session_id)
        return files.delete_file_impl(filename, temp_dir, server_state.security)

    @mcp.tool(
        name="list_files",
        description="List files in the session temp directory.",
    )
    async def list_files(ctx: Context) -> list:
        session_id = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(session_id)
        return files.list_files_impl(temp_dir)

    # ── Admin tools ──────────────────────────────────────────────

    @mcp.tool(
        name="get_pool_status",
        description="Show MATLAB engine pool status (available, busy, queued).",
    )
    async def get_pool_status(ctx: Context) -> dict:
        return admin.get_pool_status_impl(server_state.pool)

    # ── Custom tools ─────────────────────────────────────────────

    custom_tools = load_custom_tools(config.custom_tools.config_file)
    for tool_def in custom_tools:
        # Build a typed function dynamically (FastMCP rejects **kwargs)
        from matlab_mcp.tools.custom import make_custom_tool_handler
        handler = make_custom_tool_handler(tool_def, server_state)
        mcp.tool(
            name=tool_def.name,
            description=tool_def.description,
        )(handler)

    return mcp


def main() -> None:
    """CLI entry point."""
    config_path = Path("config.yaml")
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    config = load_config(config_path if config_path.exists() else None)
    _setup_logging(config)

    mcp = create_server(config)

    if config.server.transport == "sse":
        mcp.run(transport="sse", host=config.server.host, port=config.server.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all tests to ensure nothing is broken**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 3: Commit**

```bash
git add src/matlab_mcp/server.py
git commit -m "feat: MCP server entry point with all tools registered and lifespan management"
```

---

### Task 15: GitHub Repo & README

**Files:**
- Create: `README.md`
- Create: `LICENSE`
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
.env
*.log
logs/
temp/
results/
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
htmlcov/
```

- [ ] **Step 2: Create LICENSE (MIT)**

Standard MIT license with year 2026 and copyright holder HanSur94.

- [ ] **Step 3: Create README.md**

```markdown
# MATLAB MCP Server (Python)

A Python-based [MCP](https://modelcontextprotocol.io/) server that exposes MATLAB capabilities to any AI agent. Run MATLAB code, discover toolboxes, check code quality, and get interactive Plotly plots — all through the Model Context Protocol.

## Features

- **Execute MATLAB code** — sync for fast commands, auto-async for long-running jobs
- **Elastic engine pool** — scales from min to max engines based on demand
- **Toolbox discovery** — list installed toolboxes, browse functions, read help
- **Code checker** — run `checkcode`/`mlint` on code before execution
- **Interactive plots** — figures converted to Plotly JSON for web rendering
- **Multi-user support** — SSE transport with session isolation
- **Fully configurable** — single YAML config, env var overrides
- **Cross-platform** — Windows and macOS, MATLAB 2020b+

## Quick Start

### Prerequisites

- Python 3.9+
- MATLAB 2020b or newer (with MATLAB Engine API for Python installed)

### Install

```bash
pip install -e ".[dev]"
```

### Configure

Edit `config.yaml` or use environment variables:

```bash
export MATLAB_MCP_POOL_MIN_ENGINES=2
export MATLAB_MCP_POOL_MAX_ENGINES=8
```

### Run

```bash
# stdio transport (single user)
matlab-mcp

# SSE transport (multi-user)
matlab-mcp config.yaml  # with transport: sse in config
```

### Add to Claude Desktop

```json
{
  "mcpServers": {
    "matlab": {
      "command": "matlab-mcp",
      "args": []
    }
  }
}
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `execute_code` | Run MATLAB code (auto sync/async) |
| `get_job_status` | Check async job progress |
| `get_job_result` | Get completed job result |
| `cancel_job` | Cancel pending/running job |
| `list_jobs` | List session jobs |
| `check_code` | Run checkcode/mlint |
| `list_toolboxes` | List MATLAB toolboxes |
| `list_functions` | List toolbox functions |
| `get_help` | Get function help text |
| `get_workspace` | Show workspace variables |
| `upload_data` | Upload files to session |
| `delete_file` | Delete session file |
| `list_files` | List session files |
| `get_pool_status` | Engine pool status |

## Custom Tools

Define custom MATLAB functions as first-class MCP tools in `custom_tools.yaml`:

```yaml
tools:
  - name: run_simulation
    matlab_function: mylib.run_sim
    description: "Run physics simulation"
    parameters:
      - name: model_name
        type: string
        required: true
```

## License

MIT
```

- [ ] **Step 4: Create GitHub repo and push**

```bash
gh repo create HanSur94/matlab-mcp-server-python --public --source=. --push
```

- [ ] **Step 5: Verify repo exists**

Run: `gh repo view HanSur94/matlab-mcp-server-python`
Expected: repo info displayed

---
