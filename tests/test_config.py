"""Tests for the configuration system."""
from __future__ import annotations

from pathlib import Path

import pytest

from matlab_mcp.config import (
    AppConfig,
    ExecutionConfig,
    MonitoringConfig,
    OutputConfig,
    PoolConfig,
    SecurityConfig,
    ServerConfig,
    SessionsConfig,
    load_config,
)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestDefaultValues:
    def test_server_defaults(self):
        cfg = ServerConfig()
        assert cfg.name == "matlab-mcp-server"
        assert cfg.transport == "stdio"
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8765
        assert cfg.log_level == "info"
        assert cfg.drain_timeout_seconds == 300

    def test_server_host_env_override(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_SERVER_HOST", "0.0.0.0")
        cfg = load_config(None)
        assert cfg.server.host == "0.0.0.0"

    def test_pool_defaults(self):
        cfg = PoolConfig()
        assert cfg.min_engines == 2
        assert cfg.max_engines == 10
        assert cfg.scale_down_idle_timeout == 900
        assert cfg.engine_start_timeout == 120
        assert cfg.health_check_interval == 60
        assert cfg.proactive_warmup_threshold == 0.8
        assert cfg.queue_max_size == 50
        assert cfg.matlab_root is None

    def test_execution_defaults(self):
        cfg = ExecutionConfig()
        assert cfg.sync_timeout == 30
        assert cfg.max_execution_time == 86400
        assert cfg.workspace_isolation is True
        assert cfg.engine_affinity is False
        assert cfg.temp_cleanup_on_disconnect is True

    def test_output_defaults(self):
        cfg = OutputConfig()
        assert cfg.plotly_conversion is True
        assert cfg.static_image_format == "png"
        assert cfg.static_image_dpi == 150
        assert cfg.thumbnail_enabled is True
        assert cfg.thumbnail_max_width == 400
        assert cfg.large_result_threshold == 10000
        assert cfg.max_inline_text_length == 50000

    def test_security_defaults(self):
        cfg = SecurityConfig()
        assert cfg.blocked_functions_enabled is True
        assert "system" in cfg.blocked_functions
        assert cfg.max_upload_size_mb == 100
        assert cfg.require_proxy_auth is False

    def test_sessions_defaults(self):
        cfg = SessionsConfig()
        assert cfg.max_sessions == 50
        assert cfg.session_timeout == 3600
        assert cfg.job_retention_seconds == 86400

    def test_app_config_defaults(self):
        cfg = AppConfig()
        assert isinstance(cfg.server, ServerConfig)
        assert isinstance(cfg.pool, PoolConfig)
        assert isinstance(cfg.execution, ExecutionConfig)
        assert isinstance(cfg.output, OutputConfig)
        assert isinstance(cfg.security, SecurityConfig)
        assert isinstance(cfg.sessions, SessionsConfig)


# ---------------------------------------------------------------------------
# Loading from YAML
# ---------------------------------------------------------------------------


class TestLoadFromYaml:
    def test_load_sample_config(self, sample_config_path: Path):
        cfg = load_config(sample_config_path)
        assert cfg.server.name == "test-server"
        assert cfg.server.transport == "stdio"
        assert cfg.pool.min_engines == 1
        assert cfg.pool.max_engines == 2

    def test_missing_config_file_uses_defaults(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.yaml"
        cfg = load_config(missing)
        # Should use defaults without raising
        assert cfg.server.name == "matlab-mcp-server"
        assert cfg.pool.min_engines == 2

    def test_none_path_uses_defaults(self):
        cfg = load_config(None)
        assert cfg.server.name == "matlab-mcp-server"


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    def test_pool_max_engines_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("MATLAB_MCP_POOL_MAX_ENGINES", "15")
        cfg = load_config(None)
        assert cfg.pool.max_engines == 15

    def test_server_transport_override(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_SERVER_TRANSPORT", "sse")
        cfg = load_config(None)
        assert cfg.server.transport == "sse"

    def test_env_int_coercion(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_POOL_MIN_ENGINES", "3")
        cfg = load_config(None)
        assert cfg.pool.min_engines == 3
        assert isinstance(cfg.pool.min_engines, int)

    def test_env_bool_coercion(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_EXECUTION_ENGINE_AFFINITY", "true")
        cfg = load_config(None)
        assert cfg.execution.engine_affinity is True

    def test_env_override_does_not_persist(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_POOL_MAX_ENGINES", "99")
        cfg1 = load_config(None)
        assert cfg1.pool.max_engines == 99
        monkeypatch.delenv("MATLAB_MCP_POOL_MAX_ENGINES")
        cfg2 = load_config(None)
        assert cfg2.pool.max_engines == 10  # default


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPathResolution:
    def test_relative_result_dir_resolved(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("server:\n  result_dir: ./results\n")
        cfg = load_config(config_file)
        assert Path(cfg.server.result_dir).is_absolute()
        assert cfg.server.result_dir == str(tmp_path / "results")

    def test_relative_temp_dir_resolved(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("execution:\n  temp_dir: ./temp\n")
        cfg = load_config(config_file)
        assert Path(cfg.execution.temp_dir).is_absolute()

    def test_absolute_path_unchanged(self, tmp_path: Path):
        abs_dir = str(tmp_path / "absolute" / "path" / "results")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(f"server:\n  result_dir: '{abs_dir}'\n")
        cfg = load_config(config_file)
        assert cfg.server.result_dir == abs_dir


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


class TestValidation:
    def test_invalid_transport_rejected(self):
        with pytest.raises(Exception):  # pydantic ValidationError
            ServerConfig(transport="tcp")

    def test_min_engines_exceeds_max_rejected(self):
        with pytest.raises(ValueError, match="min_engines"):
            AppConfig(pool=PoolConfig(min_engines=5, max_engines=3))

    def test_equal_min_max_engines_allowed(self):
        cfg = AppConfig(pool=PoolConfig(min_engines=3, max_engines=3))
        assert cfg.pool.min_engines == 3
        assert cfg.pool.max_engines == 3

    def test_invalid_log_level_rejected(self):
        with pytest.raises(Exception):
            ServerConfig(log_level="verbose")

    def test_invalid_image_format_rejected(self):
        with pytest.raises(Exception):
            OutputConfig(static_image_format="bmp")


# ---------------------------------------------------------------------------
# Monitoring configuration
# ---------------------------------------------------------------------------


class TestMonitoringConfig:
    def test_monitoring_defaults(self):
        """MonitoringConfig has correct defaults."""
        cfg = MonitoringConfig()
        assert cfg.enabled is True
        assert cfg.sample_interval == 10
        assert cfg.retention_days == 7
        assert cfg.db_path == "./monitoring/metrics.db"
        assert cfg.dashboard_enabled is True
        assert cfg.http_port == 8766

    def test_monitoring_in_app_config(self):
        """AppConfig includes monitoring section with defaults."""
        config = load_config(None)
        assert hasattr(config, "monitoring")
        assert isinstance(config.monitoring, MonitoringConfig)
        assert config.monitoring.enabled is True
        assert config.monitoring.sample_interval == 10

    def test_monitoring_env_override(self, monkeypatch):
        """Environment variables override monitoring config."""
        monkeypatch.setenv("MATLAB_MCP_MONITORING_SAMPLE_INTERVAL", "5")
        monkeypatch.setenv("MATLAB_MCP_MONITORING_RETENTION_DAYS", "30")
        monkeypatch.setenv("MATLAB_MCP_MONITORING_ENABLED", "false")
        config = load_config(None)
        assert config.monitoring.sample_interval == 5
        assert config.monitoring.retention_days == 30
        assert config.monitoring.enabled is False

    def test_monitoring_db_path_resolved(self, tmp_path):
        """monitoring.db_path is resolved to absolute path."""
        cfg = MonitoringConfig()
        assert not Path(cfg.db_path).is_absolute()  # relative by default
        app = AppConfig(monitoring=cfg)
        app.resolve_paths(tmp_path)
        assert Path(app.monitoring.db_path).is_absolute()
        assert str(tmp_path) in app.monitoring.db_path
