"""Shared test fixtures for matlab-mcp-server."""
import pytest
from pathlib import Path

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
