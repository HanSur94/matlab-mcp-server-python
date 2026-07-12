"""Tests for scripts/install_matlab_engine.py.

Every environment interaction (Windows registry, filesystem globs, pip) is
mocked. No live MATLAB installation and no real pip invocation are required —
this suite must pass on any host, including macOS/Linux CI with no MATLAB.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py (it is a collection of standalone tooling
# scripts, not a package). Shim the repo root onto sys.path so it resolves
# as an implicit namespace package regardless of how pytest was invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import install_matlab_engine as engine_script  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_matlab_env(monkeypatch):
    """Ensure MATLAB_RELEASE / MATLAB_MCP_VENDOR / MATLABROOT never leak in."""
    monkeypatch.delenv("MATLAB_RELEASE", raising=False)
    monkeypatch.delenv("MATLAB_MCP_VENDOR", raising=False)
    monkeypatch.delenv("MATLABROOT", raising=False)


# ---------------------------------------------------------------------------
# resolve_engine_spec: release -> matlabengine version map (whitelist gate)
# ---------------------------------------------------------------------------


class TestResolveEngineSpecReleaseTokens:
    """Every RELEASE_TO_ENGINE row must resolve to its matching pip pin."""

    @pytest.mark.parametrize(
        "token, expected",
        [
            ("R2022b", "matlabengine==9.13.*"),
            ("R2023a", "matlabengine==9.14.*"),
            ("R2023b", "matlabengine==9.15.*"),
            ("R2024a", "matlabengine==24.1.*"),
            ("R2024b", "matlabengine==24.2.*"),
            ("R2025a", "matlabengine==25.1.*"),
            ("R2025b", "matlabengine==25.2.*"),
            ("R2026a", "matlabengine==26.1.*"),
        ],
    )
    def test_r_token_resolves_to_expected_pin(self, token, expected):
        assert engine_script.resolve_engine_spec(token) == expected


class TestResolveEngineSpecNumericTokens:
    """Numeric registry-style tokens must resolve the same as their R-token."""

    @pytest.mark.parametrize(
        "token, expected",
        [
            ("24.2", "matlabengine==24.2.*"),
            ("9.13", "matlabengine==9.13.*"),
            ("25.1", "matlabengine==25.1.*"),
        ],
    )
    def test_numeric_token_resolves_to_expected_pin(self, token, expected):
        assert engine_script.resolve_engine_spec(token) == expected


class TestResolveEngineSpecRejectsUnknownTokens:
    """Unknown/garbage tokens must be rejected before any pip spec is built."""

    @pytest.mark.parametrize(
        "token",
        ["R2019a", "'; rm -rf", "99.99", "", "not-a-release", "R2022b; echo pwned"],
    )
    def test_unknown_token_raises_value_error(self, token):
        with pytest.raises(ValueError):
            engine_script.resolve_engine_spec(token)

    def test_unknown_token_never_reaches_pip_seam(self, monkeypatch):
        calls = []
        monkeypatch.setattr(engine_script, "_run_pip_install", lambda args: calls.append(args))
        with pytest.raises(ValueError):
            engine_script.install_engine(release="R2019a", matlab_root="/opt/matlab")
        assert calls == []


# ---------------------------------------------------------------------------
# detect_release: newest-wins discovery + MATLAB_RELEASE override
# ---------------------------------------------------------------------------


class TestDetectRelease:
    def test_newest_wins_when_multiple_releases_discovered(self, monkeypatch):
        monkeypatch.setattr(engine_script, "_discover_releases", lambda: ["R2023b", "R2025a"])
        assert engine_script.detect_release() == "R2025a"

    def test_newest_wins_regardless_of_discovery_order(self, monkeypatch):
        monkeypatch.setattr(
            engine_script, "_discover_releases", lambda: ["R2026a", "R2022b", "R2024a"]
        )
        assert engine_script.detect_release() == "R2026a"

    def test_env_override_forces_release_even_when_different_on_disk(self, monkeypatch):
        monkeypatch.setattr(engine_script, "_discover_releases", lambda: ["R2022b"])
        monkeypatch.setenv("MATLAB_RELEASE", "R2025b")
        assert engine_script.detect_release() == "R2025b"

    def test_no_releases_discovered_returns_none(self, monkeypatch):
        monkeypatch.setattr(engine_script, "_discover_releases", lambda: [])
        assert engine_script.detect_release() is None


# ---------------------------------------------------------------------------
# install_engine: online pip seam (whitelisted spec)
# ---------------------------------------------------------------------------


class TestInstallEngineOnline:
    def test_installs_resolved_pin_via_pip_seam(self, monkeypatch):
        calls = []
        monkeypatch.setattr(engine_script, "_run_pip_install", lambda args: calls.append(args))
        engine_script.install_engine(release="R2024b", matlab_root="/opt/matlab/R2024b")
        assert calls == [["matlabengine==24.2.*"]]

    def test_no_release_detected_raises_runtime_error(self, monkeypatch):
        calls = []
        monkeypatch.setattr(engine_script, "_discover_releases", lambda: [])
        monkeypatch.setattr(engine_script, "_run_pip_install", lambda args: calls.append(args))
        with pytest.raises(RuntimeError):
            engine_script.install_engine()
        assert calls == []


# ---------------------------------------------------------------------------
# install_engine: offline fallback (MATLAB_MCP_VENDOR set, or online failure)
# ---------------------------------------------------------------------------


class TestInstallEngineOffline:
    def test_vendor_env_forces_local_tree_install(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_VENDOR", "1")
        calls = []
        monkeypatch.setattr(engine_script, "_run_pip_install", lambda args: calls.append(args))
        engine_script.install_engine(release="R2024b", matlab_root="/opt/matlab/R2024b")
        assert calls == [["/opt/matlab/R2024b/extern/engines/python"]]
        assert all("matlabengine==" not in call[0] for call in calls)

    def test_online_pip_failure_falls_back_to_local_tree(self, monkeypatch):
        calls = []

        def fake_pip_install(args):
            calls.append(args)
            if args and str(args[0]).startswith("matlabengine=="):
                raise subprocess.CalledProcessError(returncode=1, cmd=args)

        monkeypatch.setattr(engine_script, "_run_pip_install", fake_pip_install)
        engine_script.install_engine(release="R2024b", matlab_root="/opt/matlab/R2024b")
        assert calls[0] == ["matlabengine==24.2.*"]
        assert calls[1] == ["/opt/matlab/R2024b/extern/engines/python"]

    def test_offline_without_matlab_root_raises(self, monkeypatch):
        monkeypatch.setenv("MATLAB_MCP_VENDOR", "1")
        calls = []
        monkeypatch.setattr(engine_script, "_run_pip_install", lambda args: calls.append(args))
        with pytest.raises(RuntimeError):
            engine_script.install_engine(release="R2024b", matlab_root=None)
        assert calls == []


# ---------------------------------------------------------------------------
# Cross-platform import safety (winreg must be lazily/guardedly imported)
# ---------------------------------------------------------------------------


class TestModuleImportSafety:
    def test_module_imports_without_winreg_on_this_platform(self):
        # Reaching this point means the top-level `import scripts.install_matlab_engine`
        # succeeded without raising on a non-Windows host — proof winreg is guarded.
        assert hasattr(engine_script, "detect_release")
        assert hasattr(engine_script, "resolve_engine_spec")
        assert hasattr(engine_script, "install_engine")
        assert hasattr(engine_script, "main")
        assert isinstance(engine_script.RELEASE_TO_ENGINE, dict)
