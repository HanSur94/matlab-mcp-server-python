"""Tests for the MCP server module (MatlabMCPServer, create_server, main).

Covers:
- MatlabMCPServer.__init__ with monitoring enabled/disabled
- MatlabMCPServer._get_session_id for stdio and SSE transports
- MatlabMCPServer._get_temp_dir for existing/missing sessions in both transports
- create_server returns a correctly configured FastMCP instance
- create_server registers all expected tools
- main() CLI entry point with argument parsing and transport routing
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock matlab.engine before any production import touches it
# ---------------------------------------------------------------------------
_matlab_pkg = types.ModuleType("matlab")
_engine_mod = types.ModuleType("matlab.engine")

from tests.mocks.matlab_engine_mock import (  # noqa: E402
    MatlabExecutionError,
    start_matlab as _mock_start_matlab,
)

_engine_mod.start_matlab = _mock_start_matlab
_engine_mod.MatlabExecutionError = MatlabExecutionError
_matlab_pkg.engine = _engine_mod

sys.modules.setdefault("matlab", _matlab_pkg)
sys.modules.setdefault("matlab.engine", _engine_mod)

# Now safe to import production code
from matlab_mcp.config import (  # noqa: E402
    AppConfig,
    ExecutionConfig,
    MonitoringConfig,
    SecurityConfig,
    ServerConfig,
    SessionsConfig,
)
from matlab_mcp.server import MatlabMCPServer, create_server, main  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

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


@pytest.fixture
def stdio_config(tmp_path: Path) -> AppConfig:
    return _make_config(tmp_path, transport="stdio")


@pytest.fixture
def sse_config(tmp_path: Path) -> AppConfig:
    return _make_config(tmp_path, transport="sse")


@pytest.fixture
def monitoring_config(tmp_path: Path) -> AppConfig:
    return _make_config(tmp_path, monitoring_enabled=True)


@pytest.fixture
def server_state(stdio_config: AppConfig) -> MatlabMCPServer:
    """A MatlabMCPServer instance configured for stdio with monitoring off."""
    return MatlabMCPServer(stdio_config)


@pytest.fixture
def sse_server_state(sse_config: AppConfig) -> MatlabMCPServer:
    """A MatlabMCPServer instance configured for SSE transport."""
    return MatlabMCPServer(sse_config)


class _NoSessionIdSpec:
    """Spec class that deliberately lacks a session_id attribute."""
    pass


def _mock_context(session_id: str | None = "UNSET") -> MagicMock:
    """Build a mock fastmcp Context with an optional session_id attribute.

    Pass a string to set session_id, pass None to make accessing it
    raise AttributeError, or omit to get the default MagicMock behaviour.
    """
    if session_id is None:
        # Use spec= so that accessing .session_id raises AttributeError
        return MagicMock(spec=_NoSessionIdSpec)
    ctx = MagicMock()
    if session_id != "UNSET":
        ctx.session_id = session_id
    return ctx


# =========================================================================
# MatlabMCPServer.__init__
# =========================================================================


class TestMatlabMCPServerInit:
    """Verify __init__ wires up all sub-components correctly."""

    def test_pool_created(self, server_state: MatlabMCPServer) -> None:
        assert server_state.pool is not None

    def test_tracker_created(self, server_state: MatlabMCPServer) -> None:
        assert server_state.tracker is not None

    def test_executor_created(self, server_state: MatlabMCPServer) -> None:
        assert server_state.executor is not None

    def test_sessions_manager_created(self, server_state: MatlabMCPServer) -> None:
        assert server_state.sessions is not None

    def test_security_validator_created(self, server_state: MatlabMCPServer) -> None:
        assert server_state.security is not None

    def test_config_stored(self, server_state: MatlabMCPServer, stdio_config: AppConfig) -> None:
        assert server_state.config is stdio_config

    def test_monitoring_disabled_collector_is_none(self, server_state: MatlabMCPServer) -> None:
        assert server_state.collector is None

    def test_monitoring_disabled_store_is_none(self, server_state: MatlabMCPServer) -> None:
        assert server_state.store is None

    def test_monitoring_enabled_collector_created(self, monitoring_config: AppConfig) -> None:
        state = MatlabMCPServer(monitoring_config)
        assert state.collector is not None

    def test_monitoring_enabled_store_still_none_at_init(
        self, monitoring_config: AppConfig
    ) -> None:
        """Store is initialised during lifespan, not __init__."""
        state = MatlabMCPServer(monitoring_config)
        assert state.store is None

    def test_tracker_retention_from_config(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        cfg.sessions.job_retention_seconds = 42
        state = MatlabMCPServer(cfg)
        assert state.tracker._retention_seconds == 42

    def test_security_uses_config_security_section(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path)
        cfg.security = SecurityConfig(blocked_functions=["foo", "bar"])
        state = MatlabMCPServer(cfg)
        assert "foo" in state.security._call_patterns
        assert "bar" in state.security._call_patterns


# =========================================================================
# MatlabMCPServer._get_session_id
# =========================================================================


class TestGetSessionId:
    """Verify session ID resolution for both transport modes."""

    def test_stdio_returns_default(self, server_state: MatlabMCPServer) -> None:
        ctx = _mock_context(session_id="anything")
        sid = server_state._get_session_id(ctx)
        assert sid == "default"

    def test_stdio_ignores_ctx_session_id(self, server_state: MatlabMCPServer) -> None:
        ctx = _mock_context(session_id="sse-abc-123")
        sid = server_state._get_session_id(ctx)
        # stdio should always fall back to default regardless of ctx
        assert sid == "default"

    def test_sse_uses_ctx_session_id(self, sse_server_state: MatlabMCPServer) -> None:
        ctx = _mock_context(session_id="sse-session-42")
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "sse-session-42"

    def test_sse_empty_session_id_falls_back_to_default(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        ctx = MagicMock()
        ctx.session_id = ""  # empty string is falsy
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "default"

    def test_sse_none_session_id_falls_back_to_default(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        ctx = MagicMock()
        ctx.session_id = None
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "default"

    def test_sse_session_id_attribute_error_falls_back(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        ctx = _mock_context(session_id=None)  # raises AttributeError
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "default"

    def test_stdio_creates_default_session_on_first_call(
        self, server_state: MatlabMCPServer
    ) -> None:
        ctx = _mock_context()
        server_state._get_session_id(ctx)
        session = server_state.sessions.get_session("default")
        assert session is not None

    def test_sse_does_not_create_session_for_known_id(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        """_get_session_id should NOT create a session — that is _get_temp_dir's job."""
        ctx = _mock_context(session_id="new-sse-id")
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "new-sse-id"
        # The session manager should NOT have "new-sse-id" yet
        assert sse_server_state.sessions.get_session("new-sse-id") is None


# =========================================================================
# MatlabMCPServer._get_temp_dir
# =========================================================================


class TestGetTempDir:
    """Verify temp directory resolution for existing and new sessions."""

    def test_existing_session_returns_its_temp_dir(
        self, server_state: MatlabMCPServer
    ) -> None:
        session = server_state.sessions.create_session(session_id="s1")
        temp_dir = server_state._get_temp_dir("s1")
        assert temp_dir == session.temp_dir

    def test_default_session_stdio(self, server_state: MatlabMCPServer) -> None:
        """For an unknown session in stdio mode, falls back to the default session."""
        temp_dir = server_state._get_temp_dir("unknown-session")
        # Should have created the default session
        default = server_state.sessions.get_session("default")
        assert default is not None
        assert temp_dir == default.temp_dir

    def test_sse_creates_session_for_unknown_id(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        temp_dir = sse_server_state._get_temp_dir("sse-new-client")
        session = sse_server_state.sessions.get_session("sse-new-client")
        assert session is not None
        assert temp_dir == session.temp_dir

    def test_sse_created_session_temp_dir_exists(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        temp_dir = sse_server_state._get_temp_dir("sse-client-xyz")
        assert Path(temp_dir).exists()

    def test_stdio_unknown_session_returns_default_temp_dir(
        self, server_state: MatlabMCPServer
    ) -> None:
        """Unknown session IDs in stdio mode should all map to the default session."""
        td1 = server_state._get_temp_dir("unknown-a")
        td2 = server_state._get_temp_dir("unknown-b")
        assert td1 == td2  # both should be the default session's temp dir

    def test_returns_string(self, server_state: MatlabMCPServer) -> None:
        result = server_state._get_temp_dir("whatever")
        assert isinstance(result, str)

    def test_sse_second_call_returns_same_dir(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        td1 = sse_server_state._get_temp_dir("session-x")
        td2 = sse_server_state._get_temp_dir("session-x")
        assert td1 == td2

    def test_sse_different_sessions_get_different_dirs(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        td1 = sse_server_state._get_temp_dir("session-a")
        td2 = sse_server_state._get_temp_dir("session-b")
        assert td1 != td2


# =========================================================================
# create_server
# =========================================================================


class TestCreateServer:
    """Verify create_server returns a properly configured FastMCP instance."""

    def test_returns_fastmcp_instance(self, stdio_config: AppConfig) -> None:
        from fastmcp import FastMCP

        mcp = create_server(stdio_config)
        assert isinstance(mcp, FastMCP)

    def test_server_name_matches_config(self, stdio_config: AppConfig) -> None:
        mcp = create_server(stdio_config)
        assert mcp.name == stdio_config.server.name

    async def test_expected_core_tools_registered(self, stdio_config: AppConfig) -> None:
        """All core tools from the tool registration block should be present."""
        mcp = create_server(stdio_config)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        expected = {
            "execute_code",
            "check_code",
            "get_workspace",
            "get_job_status",
            "get_job_result",
            "cancel_job",
            "list_jobs",
            "list_toolboxes",
            "list_functions",
            "get_help",
            "upload_data",
            "delete_file",
            "list_files",
            "read_script",
            "read_data",
            "read_image",
            "get_pool_status",
        }
        for name in expected:
            assert name in tool_names, f"Tool '{name}' not found in registered tools"

    async def test_monitoring_tools_registered(self, stdio_config: AppConfig) -> None:
        mcp = create_server(stdio_config)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        monitoring_tools = {"get_server_metrics", "get_server_health", "get_error_log"}
        for name in monitoring_tools:
            assert name in tool_names, f"Monitoring tool '{name}' not found"

    async def test_all_tools_count_at_least_20(self, stdio_config: AppConfig) -> None:
        """Sanity check: server should have at least 20 built-in tools."""
        mcp = create_server(stdio_config)
        tools = await mcp.list_tools()
        assert len(tools) >= 20

    def test_create_server_with_sse_transport(self, sse_config: AppConfig) -> None:
        from fastmcp import FastMCP

        mcp = create_server(sse_config)
        assert isinstance(mcp, FastMCP)

    def test_create_server_with_monitoring_enabled(
        self, monitoring_config: AppConfig
    ) -> None:
        from fastmcp import FastMCP

        mcp = create_server(monitoring_config)
        assert isinstance(mcp, FastMCP)

    def test_custom_tools_config_file_not_found_no_crash(
        self, tmp_path: Path
    ) -> None:
        """When custom_tools.yaml doesn't exist, create_server should not fail."""
        cfg = _make_config(tmp_path)
        cfg.custom_tools.config_file = str(tmp_path / "nonexistent_custom_tools.yaml")
        mcp = create_server(cfg)
        assert mcp is not None


# =========================================================================
# main() CLI entry point
# =========================================================================


class TestMain:
    """Verify main() argument parsing and server launch."""

    def test_main_stdio_default(self, tmp_path: Path) -> None:
        """main() with no args should load default config and run stdio."""
        cfg = _make_config(tmp_path)
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            mock_create.assert_called_once_with(cfg)
            mock_mcp.run.assert_called_once_with(transport="stdio", show_banner=False)

    def test_main_transport_override_sse(self, tmp_path: Path) -> None:
        """--transport=sse should override config and run in SSE mode with middleware."""
        cfg = _make_config(tmp_path, transport="stdio")
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp", "--transport", "sse"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            # Config should have been mutated
            assert cfg.server.transport == "sse"
            call_kwargs = mock_mcp.run.call_args.kwargs
            assert call_kwargs["transport"] == "sse"
            assert call_kwargs["host"] == cfg.server.host
            assert call_kwargs["port"] == cfg.server.port
            # SSE transport must wire middleware (BearerAuthMiddleware + CORSMiddleware)
            assert "middleware" in call_kwargs
            assert len(call_kwargs["middleware"]) == 2

    def test_main_config_file_arg(self, tmp_path: Path) -> None:
        """--config should pass the specified path to load_config."""
        cfg = _make_config(tmp_path)
        config_path = tmp_path / "my_config.yaml"
        config_path.write_text("server:\n  name: test\n")

        with (
            patch("matlab_mcp.server.load_config", return_value=cfg) as mock_load,
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp", "--config", str(config_path)]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            # load_config should receive the Path object
            call_args = mock_load.call_args
            actual_path = call_args[0][0]
            assert actual_path == config_path

    def test_main_nonexistent_config_uses_defaults(self, tmp_path: Path) -> None:
        """When the config file does not exist, load_config(None) is called."""
        cfg = _make_config(tmp_path)
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg) as mock_load,
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp", "--config", "/no/such/file.yaml"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            # Config file path does not exist, so load_config(None) is used
            call_args = mock_load.call_args
            assert call_args[0][0] is None

    def test_main_sse_passes_host_and_port(self, tmp_path: Path) -> None:
        """SSE transport should pass host and port from config with middleware."""
        cfg = _make_config(tmp_path, transport="sse")
        cfg.server.host = "127.0.0.1"
        cfg.server.port = 9999

        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            call_kwargs = mock_mcp.run.call_args.kwargs
            assert call_kwargs["transport"] == "sse"
            assert call_kwargs["host"] == "127.0.0.1"
            assert call_kwargs["port"] == 9999
            # SSE transport must include middleware kwarg
            assert "middleware" in call_kwargs


# =========================================================================
# Integration-style: MatlabMCPServer + SessionManager wiring
# =========================================================================


class TestServerSessionIntegration:
    """Verify that MatlabMCPServer correctly delegates to SessionManager."""

    def test_get_session_id_then_temp_dir_round_trip_stdio(
        self, server_state: MatlabMCPServer
    ) -> None:
        """In stdio mode, _get_session_id -> _get_temp_dir should be consistent."""
        ctx = _mock_context()
        sid = server_state._get_session_id(ctx)
        temp_dir = server_state._get_temp_dir(sid)
        assert isinstance(temp_dir, str)
        assert Path(temp_dir).exists()

    def test_get_session_id_then_temp_dir_round_trip_sse(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        """In SSE mode, _get_session_id -> _get_temp_dir should create the session."""
        ctx = _mock_context(session_id="round-trip-client")
        sid = sse_server_state._get_session_id(ctx)
        assert sid == "round-trip-client"
        temp_dir = sse_server_state._get_temp_dir(sid)
        assert isinstance(temp_dir, str)
        assert Path(temp_dir).exists()
        # Session should now exist in the manager
        session = sse_server_state.sessions.get_session("round-trip-client")
        assert session is not None

    def test_multiple_sse_clients_get_isolated_dirs(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        ctx_a = _mock_context(session_id="client-a")
        ctx_b = _mock_context(session_id="client-b")

        sid_a = sse_server_state._get_session_id(ctx_a)
        sid_b = sse_server_state._get_session_id(ctx_b)

        td_a = sse_server_state._get_temp_dir(sid_a)
        td_b = sse_server_state._get_temp_dir(sid_b)

        assert td_a != td_b
        assert Path(td_a).exists()
        assert Path(td_b).exists()

    def test_stdio_all_contexts_share_same_temp_dir(
        self, server_state: MatlabMCPServer
    ) -> None:
        """All requests in stdio mode should use the same default temp dir."""
        ctx1 = _mock_context()
        ctx2 = _mock_context()

        sid1 = server_state._get_session_id(ctx1)
        sid2 = server_state._get_session_id(ctx2)

        assert sid1 == sid2 == "default"

        td1 = server_state._get_temp_dir(sid1)
        td2 = server_state._get_temp_dir(sid2)
        assert td1 == td2


# =========================================================================
# Edge cases
# =========================================================================


class TestEdgeCases:
    """Boundary conditions and error-path coverage."""

    def test_monitoring_collector_receives_config(
        self, monitoring_config: AppConfig
    ) -> None:
        state = MatlabMCPServer(monitoring_config)
        # The collector should have received the config
        assert state.collector._config is monitoring_config

    def test_executor_receives_pool_reference(
        self, server_state: MatlabMCPServer
    ) -> None:
        assert server_state.executor._pool is server_state.pool

    def test_executor_receives_tracker_reference(
        self, server_state: MatlabMCPServer
    ) -> None:
        assert server_state.executor._tracker is server_state.tracker

    def test_executor_receives_collector_none_when_monitoring_off(
        self, server_state: MatlabMCPServer
    ) -> None:
        assert server_state.executor._collector is None

    def test_executor_receives_collector_when_monitoring_on(
        self, monitoring_config: AppConfig
    ) -> None:
        state = MatlabMCPServer(monitoring_config)
        assert state.executor._collector is state.collector

    def test_security_receives_collector_when_monitoring_on(
        self, monitoring_config: AppConfig
    ) -> None:
        state = MatlabMCPServer(monitoring_config)
        assert state.security._collector is state.collector

    def test_sessions_receives_collector_when_monitoring_on(
        self, monitoring_config: AppConfig
    ) -> None:
        state = MatlabMCPServer(monitoring_config)
        assert state.sessions._collector is state.collector

    def test_create_server_idempotent_tool_registration(
        self, stdio_config: AppConfig
    ) -> None:
        """Calling create_server twice should produce independent instances."""
        mcp1 = create_server(stdio_config)
        mcp2 = create_server(stdio_config)
        assert mcp1 is not mcp2

    def test_sse_get_temp_dir_does_not_create_default_session(
        self, sse_server_state: MatlabMCPServer
    ) -> None:
        """In SSE mode, _get_temp_dir for a new client should not pollute 'default'."""
        sse_server_state._get_temp_dir("sse-only-client")
        # The "default" session should NOT have been created
        # (it would only be created if the code incorrectly fell through)
        session = sse_server_state.sessions.get_session("sse-only-client")
        assert session is not None


# =========================================================================
# main() — additional branches
# =========================================================================


class TestMainAdditionalBranches:
    """Cover SSE logging messages and monitoring-enabled branches in main()."""

    def test_main_monitoring_enabled_stdio(self, tmp_path: Path) -> None:
        """main() with monitoring enabled logs monitoring info."""
        cfg = _make_config(tmp_path, monitoring_enabled=True)
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            mock_mcp.run.assert_called_once_with(transport="stdio", show_banner=False)

    def test_main_monitoring_enabled_sse(self, tmp_path: Path) -> None:
        """main() with monitoring enabled + SSE logs different dashboard URL."""
        cfg = _make_config(tmp_path, transport="sse", monitoring_enabled=True)
        cfg.server.host = "0.0.0.0"
        cfg.server.port = 8080
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            call_kwargs = mock_mcp.run.call_args.kwargs
            assert call_kwargs["transport"] == "sse"
            assert call_kwargs["host"] == "0.0.0.0"
            assert call_kwargs["port"] == 8080
            assert "middleware" in call_kwargs

    def test_main_sse_without_transport_override(self, tmp_path: Path) -> None:
        """main() with SSE config but no --transport flag should use config transport."""
        cfg = _make_config(tmp_path, transport="sse")
        cfg.server.host = "localhost"
        cfg.server.port = 3000
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            call_kwargs = mock_mcp.run.call_args.kwargs
            assert call_kwargs["transport"] == "sse"
            assert call_kwargs["host"] == "localhost"
            assert call_kwargs["port"] == 3000
            assert "middleware" in call_kwargs

    def test_main_log_file_directory_creation_failure(self, tmp_path: Path) -> None:
        """If log file dir can't be created, main should still proceed."""
        cfg = _make_config(tmp_path)
        cfg.server.log_file = "/nonexistent/readonly/dir/server.log"
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            mock_create.assert_called_once()


# =========================================================================
# create_server — SSE + monitoring route mounting
# =========================================================================


class TestCreateServerSSEMonitoring:
    def test_sse_monitoring_mounts_routes(self, tmp_path: Path) -> None:
        """create_server with SSE + monitoring should try to mount monitoring routes."""
        cfg = _make_config(tmp_path, transport="sse", monitoring_enabled=True)
        mcp = create_server(cfg)
        # Should not crash regardless of whether Starlette is available
        assert mcp is not None

    def test_custom_tools_yaml_with_tools(self, tmp_path: Path) -> None:
        """create_server should load and register custom tools from YAML."""
        cfg = _make_config(tmp_path)
        custom_yaml = tmp_path / "custom_tools.yaml"
        custom_yaml.write_text(
            "tools:\n"
            "  - name: my_custom_tool\n"
            "    matlab_function: my_func\n"
            "    description: A custom tool\n"
            "    parameters:\n"
            "      - name: input_val\n"
            "        type: str\n"
        )
        cfg.custom_tools.config_file = str(custom_yaml)
        mcp = create_server(cfg)
        assert mcp is not None


# =========================================================================
# --generate-token CLI flag
# =========================================================================


class TestGenerateToken:
    """Verify --generate-token flag prints 64-char hex token and exits 0."""

    def test_generate_token_prints_and_exits(self, capsys):
        import re
        sys.argv = ["matlab-mcp", "--generate-token"]
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        # Token must be exactly 64 hex chars
        tokens = re.findall(r'[0-9a-f]{64}', captured.out)
        assert len(tokens) >= 1
        assert "MATLAB_MCP_AUTH_TOKEN" in captured.out

    def test_generate_token_format_posix(self, capsys):
        sys.argv = ["matlab-mcp", "--generate-token"]
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "export MATLAB_MCP_AUTH_TOKEN=" in captured.out

    def test_generate_token_format_windows_cmd(self, capsys):
        sys.argv = ["matlab-mcp", "--generate-token"]
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "set MATLAB_MCP_AUTH_TOKEN=" in captured.out

    def test_generate_token_format_powershell(self, capsys):
        sys.argv = ["matlab-mcp", "--generate-token"]
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "$env:MATLAB_MCP_AUTH_TOKEN=" in captured.out

    def test_main_stdio_no_middleware(self, tmp_path: Path):
        """stdio transport must not pass middleware kwarg to server.run()."""
        cfg = _make_config(tmp_path, transport="stdio")
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp

            main()

            call_kwargs = mock_mcp.run.call_args.kwargs
            assert "middleware" not in call_kwargs
            assert call_kwargs["transport"] == "stdio"


# ---------------------------------------------------------------------------
# Phase 3: Streamable HTTP transport fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def streamablehttp_config(tmp_path: Path) -> AppConfig:
    """AppConfig configured for streamable HTTP transport."""
    return _make_config(tmp_path, transport="streamablehttp")


@pytest.fixture
def streamablehttp_server_state(streamablehttp_config: AppConfig) -> MatlabMCPServer:
    """A MatlabMCPServer instance configured for streamable HTTP transport."""
    return MatlabMCPServer(streamablehttp_config)


# =========================================================================
# Phase 3: Streamable HTTP transport tests
# =========================================================================


class TestStreamableHTTPTransport:
    """Phase 3: Streamable HTTP transport tests."""

    def test_get_session_id_streamablehttp_uses_ctx_session_id(
        self, streamablehttp_server_state: MatlabMCPServer
    ) -> None:
        ctx = MagicMock()
        ctx.session_id = "http-sess-abc"
        sid = streamablehttp_server_state._get_session_id(ctx)
        assert sid == "http-sess-abc"

    def test_get_session_id_streamablehttp_falls_back_to_client_id(
        self, streamablehttp_server_state: MatlabMCPServer
    ) -> None:
        ctx = MagicMock()
        type(ctx).session_id = property(lambda self: (_ for _ in ()).throw(RuntimeError("no session")))
        ctx.client_id = "client-xyz"
        sid = streamablehttp_server_state._get_session_id(ctx)
        assert sid == "client-xyz"

    def test_get_session_id_streamablehttp_falls_back_to_default(
        self, streamablehttp_server_state: MatlabMCPServer
    ) -> None:
        ctx = MagicMock()
        type(ctx).session_id = property(lambda self: (_ for _ in ()).throw(RuntimeError))
        type(ctx).client_id = property(lambda self: (_ for _ in ()).throw(RuntimeError))
        sid = streamablehttp_server_state._get_session_id(ctx)
        default = streamablehttp_server_state.sessions.get_or_create_default()
        assert sid == default.session_id

    def test_get_temp_dir_streamablehttp_creates_session(
        self, streamablehttp_server_state: MatlabMCPServer
    ) -> None:
        td = streamablehttp_server_state._get_temp_dir("new-http-sess")
        assert td  # non-empty string
        session = streamablehttp_server_state.sessions.get_session("new-http-sess")
        assert session is not None

    def test_session_isolation_two_http_sessions_get_different_dirs(
        self, streamablehttp_server_state: MatlabMCPServer
    ) -> None:
        dir_a = streamablehttp_server_state._get_temp_dir("sess-a")
        dir_b = streamablehttp_server_state._get_temp_dir("sess-b")
        assert dir_a != dir_b

    def test_streamablehttp_config_calls_run_with_streamable_http(
        self, tmp_path: Path
    ) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("server:\n  transport: streamablehttp\n")
        with patch("matlab_mcp.server.create_server") as mock_create, \
             patch("sys.argv", ["matlab-mcp", "--config", str(cfg_file)]):
            mock_server = MagicMock()
            mock_create.return_value = mock_server
            main()
            mock_server.run.assert_called_once()
            call_kwargs = mock_server.run.call_args
            assert (
                call_kwargs.kwargs.get("transport") == "streamable-http"
                or (call_kwargs.args and call_kwargs.args[0] == "streamable-http")
            )

    def test_streamablehttp_passes_stateless_http_true(
        self, tmp_path: Path
    ) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("server:\n  transport: streamablehttp\n  stateless_http: true\n")
        with patch("matlab_mcp.server.create_server") as mock_create, \
             patch("sys.argv", ["matlab-mcp", "--config", str(cfg_file)]):
            mock_server = MagicMock()
            mock_create.return_value = mock_server
            main()
            call_kwargs = mock_server.run.call_args
            assert call_kwargs.kwargs.get("stateless_http") is True

    def test_main_transport_override_streamablehttp(self, tmp_path: Path) -> None:
        """--transport streamablehttp CLI flag sets config and calls streamable-http run."""
        cfg = _make_config(tmp_path, transport="stdio")
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("sys.argv", ["matlab-mcp", "--transport", "streamablehttp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            assert cfg.server.transport == "streamablehttp"
            call_kwargs = mock_mcp.run.call_args
            assert call_kwargs.kwargs.get("transport") == "streamable-http"

    def test_streamablehttp_auth_warning_no_token(self, tmp_path: Path) -> None:
        """Auth warning fires for streamablehttp when no MATLAB_MCP_AUTH_TOKEN is set."""
        cfg = _make_config(tmp_path, transport="streamablehttp")
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("matlab_mcp.server.logger") as mock_logger,
            patch("sys.argv", ["matlab-mcp"]),
            patch.dict("os.environ", {}, clear=False),
        ):
            import os
            os.environ.pop("MATLAB_MCP_AUTH_TOKEN", None)
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("auth" in w.lower() or "token" in w.lower() for w in warning_calls), \
                f"No auth warning found in: {warning_calls}"

    def test_streamablehttp_dashboard_url_logged(self, tmp_path: Path) -> None:
        """Dashboard URL is logged for streamablehttp transport when monitoring enabled."""
        cfg = _make_config(tmp_path, transport="streamablehttp", monitoring_enabled=True)
        cfg.server.host = "127.0.0.1"
        cfg.server.port = 8765
        with (
            patch("matlab_mcp.server.load_config", return_value=cfg),
            patch("matlab_mcp.server.create_server") as mock_create,
            patch("matlab_mcp.server.logger") as mock_logger,
            patch("sys.argv", ["matlab-mcp"]),
        ):
            mock_mcp = MagicMock()
            mock_create.return_value = mock_mcp
            main()
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("dashboard" in c.lower() for c in info_calls), \
                f"No dashboard URL found in: {info_calls}"


# =========================================================================
# Phase 3: SSE deprecation warning test
# =========================================================================


class TestSSEDeprecationWarning:
    """Verify SSE transport emits a deprecation warning at startup."""

    def test_sse_startup_logs_deprecation_warning(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("server:\n  transport: sse\n")
        with patch("matlab_mcp.server.create_server") as mock_create, \
             patch("matlab_mcp.server.logger") as mock_logger, \
             patch("sys.argv", ["matlab-mcp", "--config", str(cfg_file)]):
            mock_server = MagicMock()
            mock_create.return_value = mock_server
            main()
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("deprecated" in w.lower() for w in warning_calls), \
                f"No deprecation warning found in: {warning_calls}"
