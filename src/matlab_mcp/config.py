"""Configuration system for MATLAB MCP Server.

Loads YAML config, applies environment variable overrides (MATLAB_MCP_* prefix),
and validates settings with Pydantic models.
"""
from __future__ import annotations

import logging
import os
import platform
import warnings
from pathlib import Path
from typing import List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


class ServerConfig(BaseModel):
    name: str = "matlab-mcp-server"
    transport: Literal["stdio", "sse"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_file: str = "./logs/server.log"
    result_dir: str = "./results"
    drain_timeout_seconds: int = 300


class PoolConfig(BaseModel):
    min_engines: int = 2
    max_engines: int = 10
    scale_down_idle_timeout: int = 900
    engine_start_timeout: int = 120
    health_check_interval: int = 60
    proactive_warmup_threshold: float = 0.8
    queue_max_size: int = 50
    matlab_root: Optional[str] = None


class ExecutionConfig(BaseModel):
    sync_timeout: int = 30
    max_execution_time: int = 86400
    workspace_isolation: bool = True
    engine_affinity: bool = False
    temp_dir: str = "./temp"
    temp_cleanup_on_disconnect: bool = True


class WorkspaceConfig(BaseModel):
    default_paths: List[str] = Field(default_factory=list)
    startup_commands: List[str] = Field(default_factory=lambda: ["format long"])


class ToolboxesConfig(BaseModel):
    mode: Literal["whitelist", "blacklist", "all"] = "whitelist"
    list: List[str] = Field(default_factory=list)


class CustomToolsConfig(BaseModel):
    config_file: str = "./custom_tools.yaml"


class SecurityConfig(BaseModel):
    blocked_functions_enabled: bool = True
    blocked_functions: List[str] = Field(
        default_factory=lambda: [
            "system", "unix", "dos", "!",
            "eval", "feval", "evalc", "evalin", "assignin",
            "perl", "python",
        ]
    )
    max_upload_size_mb: int = 100
    require_proxy_auth: bool = False


class CodeCheckerConfig(BaseModel):
    enabled: bool = True
    auto_check_before_execute: bool = False
    severity_levels: List[str] = Field(default_factory=lambda: ["error", "warning"])


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


class MonitoringConfig(BaseModel):
    enabled: bool = True
    sample_interval: int = 10
    retention_days: int = 7
    db_path: str = "./monitoring/metrics.db"
    dashboard_enabled: bool = True
    http_port: int = 8766


class AppConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    pool: PoolConfig = Field(default_factory=PoolConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    toolboxes: ToolboxesConfig = Field(default_factory=ToolboxesConfig)
    custom_tools: CustomToolsConfig = Field(default_factory=CustomToolsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    code_checker: CodeCheckerConfig = Field(default_factory=CodeCheckerConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    # Internal: stored after resolution so validators can use it
    _config_dir: Optional[Path] = None

    @model_validator(mode="after")
    def validate_pool(self) -> "AppConfig":
        if self.pool.min_engines > self.pool.max_engines:
            raise ValueError(
                f"pool.min_engines ({self.pool.min_engines}) must not exceed "
                f"pool.max_engines ({self.pool.max_engines})"
            )
        if platform.system() == "Darwin" and self.pool.max_engines > 4:
            warnings.warn(
                f"pool.max_engines is {self.pool.max_engines} on macOS. "
                "Running more than 4 matlab.engine instances in a single Python process "
                "on macOS has known stability issues. Consider setting max_engines <= 4.",
                stacklevel=2,
            )
        return self

    def resolve_paths(self, base_dir: Path) -> None:
        """Resolve all relative paths to absolute paths relative to base_dir."""

        def _resolve(p: str) -> str:
            path = Path(p)
            if not path.is_absolute():
                return str((base_dir / path).resolve())
            return p

        self.server.result_dir = _resolve(self.server.result_dir)
        self.server.log_file = _resolve(self.server.log_file)
        self.execution.temp_dir = _resolve(self.execution.temp_dir)
        self.custom_tools.config_file = _resolve(self.custom_tools.config_file)
        self.monitoring.db_path = _resolve(self.monitoring.db_path)


def _apply_env_overrides(data: dict) -> dict:
    """Apply MATLAB_MCP_* environment variable overrides.

    Convention: MATLAB_MCP_SECTION_KEY maps to data[section][key].
    E.g. MATLAB_MCP_POOL_MAX_ENGINES=20 → data["pool"]["max_engines"] = 20.
    """
    prefix = "MATLAB_MCP_"
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        remainder = env_key[len(prefix):]  # e.g. "POOL_MAX_ENGINES"
        parts = remainder.lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, key = parts  # e.g. ("pool", "max_engines")
        if section not in data:
            data[section] = {}

        # Attempt type coercion: int → float → bool → str
        coerced: object = env_val
        try:
            coerced = int(env_val)
        except ValueError:
            try:
                coerced = float(env_val)
            except ValueError:
                if env_val.lower() in ("true", "false"):
                    coerced = env_val.lower() == "true"

        data[section][key] = coerced
    return data


def load_config(path: Optional[Path] = None) -> AppConfig:
    """Load application config from a YAML file with env var overrides.

    If *path* is None or the file does not exist, default values are used.
    """
    data: dict = {}
    config_dir = Path.cwd()

    if path is not None:
        path = Path(path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            data = loaded
            config_dir = path.parent
        else:
            logger.warning("Config file not found: %s — using defaults", path)

    data = _apply_env_overrides(data)
    config = AppConfig.model_validate(data)
    config.resolve_paths(config_dir)
    return config
