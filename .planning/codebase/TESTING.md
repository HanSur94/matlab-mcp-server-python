# Testing Patterns

**Analysis Date:** 2026-04-01

## Test Framework

**Runner:**
- `pytest` v7.0+ (specified in `pyproject.toml`)
- Configuration: `pyproject.toml` with `[tool.pytest.ini_options]`
- Async mode: `asyncio_mode = "auto"` — allows async test functions without decorators
- Test discovery: files matching `test_*.py` in `tests/` directory

**Assertion Library:**
- Standard `assert` statements (no custom matchers)
- Exception testing via `pytest.raises(ExceptionType, match="pattern")`

**Run Commands:**
```bash
pytest                        # Run all tests
pytest -v                     # Verbose output
pytest tests/test_session.py  # Run specific test file
pytest tests/test_session.py::TestSessionDataclass::test_session_has_session_id  # Run specific test
pytest -k "test_security"     # Run tests matching pattern
pytest --cov                  # With coverage (requires pytest-cov)
pytest -x                     # Stop on first failure
pytest -m "not matlab"        # Skip tests requiring live MATLAB
```

## Test File Organization

**Location:**
- `tests/` directory parallel to `src/` directory
- Test files co-located by module: `src/matlab_mcp/security/validator.py` has corresponding `tests/test_security.py`
- Shared utilities in `tests/conftest.py` (fixtures)
- Mocks in `tests/mocks/` subdirectory

**Naming:**
- Test files: `test_<module_name>.py` (e.g., `test_session.py`, `test_security.py`)
- Test classes: `Test<FunctionOrClassBeingTested>` (e.g., `TestSessionDataclass`, `TestCheckCodeBlockedFunctions`)
- Test methods: `test_<specific_scenario>` (e.g., `test_blocks_system_call`, `test_session_has_session_id`)

**File Count:** 33 test modules with 732 test functions

**Structure:**
```
tests/
├── conftest.py                          # Shared fixtures
├── mocks/
│   ├── __init__.py
│   └── matlab_engine_mock.py            # Mock MATLAB engine API
├── test_security.py                     # Security validator tests
├── test_session.py                      # Session manager tests
├── test_output.py                       # Formatter/plotly tests
├── test_file_read.py                    # File operation tests
├── test_monitoring_collector.py         # Metrics collector tests
├── test_tools_admin.py                  # Admin tool tests
├── test_tools_custom.py                 # Custom tool tests
└── ... (27 more test modules)
```

## Test Structure

**Suite Organization:**
- Tests grouped into classes by the component being tested
- Each class represents a "concern" or "behavior group"
- 185 test classes across the codebase

**Example from `tests/test_session.py`:**
```python
class TestSessionDataclass:
    """Tests for Session dataclass attributes and methods."""
    def test_session_has_session_id(self, tmp_path):
        s = Session(session_id="s1", temp_dir=str(tmp_path))
        assert s.session_id == "s1"

class TestCreateSession:
    """Tests for SessionManager.create_session()."""
    def test_creates_new_session(self, session_manager):
        s = session_manager.create_session()
        assert s.session_id is not None

class TestCheckCodeBlockedFunctions:
    """Tests for security validator blocking MATLAB functions."""
    def test_blocks_system_call(self, default_validator):
        with pytest.raises(BlockedFunctionError, match="system"):
            default_validator.check_code("result = system('ls');")
```

**Patterns:**
- Each test is a single, focused assertion
- Test names describe the behavior being verified: `test_blocks_system_call`, `test_truncation`, `test_path_traversal`
- Setup happens via fixtures or within the test method
- No shared mutable state between tests (each is independent)

## Fixtures

**Shared Fixtures (`tests/conftest.py`):**
```python
@pytest.fixture
def fixtures_dir() -> Path:
    """Path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def sample_config_path(tmp_path: Path) -> Path:
    """Create a minimal config file for testing."""
    config = tmp_path / "config.yaml"
    config.write_text("server:\n  name: test-server\n...")
    return config
```

**Module-Specific Fixtures:**
- Defined at the top of each test file using `@pytest.fixture`
- Example from `tests/test_security.py`:
```python
@pytest.fixture
def default_validator():
    """Validator using default SecurityConfig (blocking enabled)."""
    return SecurityValidator(SecurityConfig())

@pytest.fixture
def disabled_validator():
    """Validator with blocking disabled."""
    return SecurityValidator(SecurityConfig(blocked_functions_enabled=False))
```

- Example from `tests/test_session.py`:
```python
@pytest.fixture
def session_manager(tmp_path):
    """A SessionManager backed by a tmp directory with tight limits."""
    from matlab_mcp.config import AppConfig, ExecutionConfig, SessionsConfig
    cfg = AppConfig()
    cfg.sessions = SessionsConfig(max_sessions=5, session_timeout=3600)
    cfg.execution = ExecutionConfig(temp_dir=str(tmp_path / "temp"))
    return SessionManager(cfg)
```

**Parametrized Fixtures:**
- Used in `tests/test_tools_custom.py` with `@pytest.mark.parametrize`:
```python
@pytest.mark.parametrize(
    "key, expected",
    [
        ("str", str),
        ("string", str),
        ("int", int),
        ("integer", int),
    ],
)
def test_type_map_entries(self, key: str, expected: type) -> None:
    assert _TYPE_MAP[key] is expected
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Mocking Approaches:**

1. **Custom Mock Classes** (preferred for MATLAB engine):
   - `tests/mocks/matlab_engine_mock.py` provides comprehensive mock of `matlab.engine` API
   - Mock classes: `MockWorkspace`, `MockMatlabEngine`, `MockFuture`, `MatlabExecutionError`
   - Simulates MATLAB behaviors: `error('msg')`, `clear all`, `pause(N)`, variable assignment
   - Injected via `sys.modules` before production imports

2. **Unittest Mocks** (for specific test scenarios):
   - `MagicMock` for simple object replacement
   - `AsyncMock` for async functions
   - `patch` for replacing module-level imports

**Example from `tests/test_file_read.py`:**
```python
from unittest.mock import AsyncMock
import pytest

async def test_success(self, security, tmp_session_dir):
    """Reads a .m file and returns its text content."""
    p = Path(tmp_session_dir) / "test_script.m"
    p.write_text("x = magic(3);\ndisp(x);", encoding="utf-8")
    result = await read_script_impl(
        filename="test_script.m",
        session_temp_dir=tmp_session_dir,
        security=security,
        max_inline_text_length=50000,
    )
    assert result["status"] == "ok"
    assert "x = magic(3)" in result["content"]
```

**Example from `tests/test_monitoring_collector.py`:**
```python
from unittest.mock import MagicMock

def _make_mock_pool():
    pool = MagicMock()
    pool.get_status.return_value = {"total": 4, "available": 2, "busy": 2, "max": 10}
    return pool

def _make_mock_tracker():
    tracker = MagicMock()
    tracker.list_jobs.return_value = []
    return tracker
```

**What to Mock:**
- External system calls (file I/O, network, MATLAB engine)
- Large or slow operations (actual MATLAB computation)
- Stateful services (pools, trackers, collectors) when testing dependent logic

**What NOT to Mock:**
- Security validators (test actual validation logic)
- Config/dataclass initialization (test real object construction)
- Business logic (algorithm correctness requires actual execution)

## Async Testing

**Pattern:**
- Async test methods use `async def test_*`
- No manual `asyncio.run()` needed; pytest-asyncio handles execution
- Example from `tests/test_file_read.py`:
```python
async def test_success(self, security, tmp_session_dir):
    """Reads a .m file and returns its text content."""
    result = await read_script_impl(...)
    assert result["status"] == "ok"
```

- Fixtures can be async but are rarely used (most fixtures are synchronous)
- Parametrize works with async tests:
```python
@pytest.mark.asyncio
async def test_something(self):
    result = await some_async_function()
    assert result
```

## Error Testing

**Exceptions:**
- Test exception type and message using `pytest.raises`:
```python
def test_blocks_system_call(self, default_validator):
    with pytest.raises(BlockedFunctionError, match="system"):
        default_validator.check_code("result = system('ls');")
```

- Match pattern is a regex:
```python
with pytest.raises(RuntimeError, match="maximum number of sessions"):
    session_manager.create_session()  # When max reached
```

**Error Dicts:**
- Many operations return `{"status": "error", "message": "..."}` instead of raising
- Test by checking return dict:
```python
async def test_not_found(self, security, tmp_session_dir):
    result = await read_script_impl(
        filename="missing.m",
        session_temp_dir=tmp_session_dir,
        security=security,
        max_inline_text_length=50000,
    )
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()
```

## Coverage

**Requirement:** No explicit coverage threshold enforced (not configured in `pyproject.toml`)

**View Coverage:**
```bash
pytest --cov=src/matlab_mcp --cov-report=html  # Generate HTML report
pytest --cov=src/matlab_mcp --cov-report=term  # Terminal summary
```

**Current Status:** 732 test functions across 185 test classes covering:
- Security validation (43 tests)
- Session management (multiple test classes)
- Job execution and tracking (54+ tests)
- File operations (read/write/delete)
- Output formatting and plotly conversion
- Monitoring and metrics collection
- Custom tool loading and handlers
- MATLAB engine pool management (43 tests)

## Test Types

**Unit Tests:**
- Scope: Individual functions, methods, and classes in isolation
- Approach: Pass mock dependencies, verify behavior with specific inputs
- Example: Testing that `Session.idle_seconds` increases over time
- Coverage: Core business logic, security checks, formatting, calculations

**Integration Tests:**
- Scope: Multiple components working together (executor + pool, manager + config, etc.)
- Approach: Create real instances with real or partially-mocked dependencies
- Example: `test_integration_figures.py` (marked with `@pytest.mark.matlab` for CI skip)
- Coverage: End-to-end code execution paths, job lifecycle, session lifecycle

**E2E/MATLAB Tests:**
- Framework: Pytest with marker `@pytest.mark.matlab`
- Requirement: Live MATLAB installation
- Location: `tests/test_integration_figures.py`
- Run: `pytest -m matlab` (requires MATLAB; skipped in CI by default)
- Coverage: Real MATLAB code execution, figure rendering, output capture

## Test Markers

**Custom Markers (from `pyproject.toml`):**
```
markers = [
    "matlab: tests requiring a live MATLAB engine",
]
```

**Usage:**
```python
pytestmark = pytest.mark.matlab  # Mark entire module
# or
@pytest.mark.matlab
def test_something(): ...
```

**Running:**
```bash
pytest -m "not matlab"  # Skip MATLAB tests
pytest -m matlab        # Run only MATLAB tests
```

## Common Test Helper Functions

**Pattern:** Prefix helper functions with underscore to distinguish from tests

**Example from `tests/test_server.py`:**
```python
def _make_config(
    tmp_path: Path,
    *,
    transport: str = "stdio",
    monitoring_enabled: bool = False,
) -> AppConfig:
    """Build an AppConfig rooted in *tmp_path* for test isolation."""
    cfg = AppConfig(
        server=ServerConfig(
            transport=transport,
            log_file=str(tmp_path / "logs" / "server.log"),
            result_dir=str(tmp_path / "results"),
        ),
        execution=ExecutionConfig(temp_dir=str(tmp_path / "temp")),
        sessions=SessionsConfig(max_sessions=10, session_timeout=3600),
        monitoring=MonitoringConfig(
            enabled=monitoring_enabled,
            db_path=str(tmp_path / "monitoring" / "metrics.db"),
        ),
    )
    return cfg
```

**Time-Based Testing:**
- Tests for time-dependent behavior use `time.sleep()` for verification:
```python
def test_idle_seconds_increases_over_time(self, tmp_path):
    s = Session(session_id="s1", temp_dir=str(tmp_path))
    time.sleep(0.05)
    assert s.idle_seconds >= 0.04
```

---

*Testing analysis: 2026-04-01*
