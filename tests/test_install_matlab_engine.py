"""Tests for scripts/install_matlab_engine.py.

Every environment interaction (Windows registry, filesystem globs, pip) is
mocked. No live MATLAB installation and no real pip invocation are required —
this suite must pass on any host, including macOS/Linux CI with no MATLAB.
"""
from __future__ import annotations

import glob
import os
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
# Filesystem glob discovery: real glob against a temp install tree.
#
# Regression guard for the R20?? -> R20* pattern fix. The old "R20??" glob
# could not match the 6-character release dirs MATLAB actually creates
# (R2022b, R2024a, ...): fnmatch("R2022b", "R20??") is False. These tests run
# the REAL discovery code (glob.glob + _extract_release_token +
# _discover_releases_glob + detect_release) over an on-disk tree, patching
# only _glob_patterns to point at the temp dir. Reverting to "R20??" makes
# glob.glob return nothing and fails them.
# ---------------------------------------------------------------------------


class TestDiscoverReleasesGlob:
    """Real filesystem-glob discovery, tied to the source's own glob string.

    These drive the REAL ``_glob_patterns()`` (never mocking it), so the
    wildcard under test is the one in the source. Reverting to the broken
    ``R20??`` makes ``glob.glob`` match nothing and fails these tests.
    """

    def test_windows_localappdata_glob_finds_six_char_releases(
        self, tmp_path, monkeypatch
    ):
        # The Windows LOCALAPPDATA pattern is built from the source's own R20*
        # string, so pointing LOCALAPPDATA at a temp tree exercises the real
        # pattern end to end.
        monkeypatch.setattr(engine_script.sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        install_root = tmp_path / "Programs" / "MATLAB"
        (install_root / "R2024b").mkdir(parents=True)
        (install_root / "R2022b").mkdir(parents=True)
        assert sorted(engine_script._discover_releases_glob()) == ["R2022b", "R2024b"]

    def test_windows_localappdata_detect_release_newest_wins(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(engine_script.sys, "platform", "win32")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        install_root = tmp_path / "Programs" / "MATLAB"
        for release in ("R2022b", "R2024b", "R2023a"):
            (install_root / release).mkdir(parents=True)
        # winreg is absent on this host, so registry discovery returns [] and
        # detection runs entirely over the real glob result — newest must win.
        assert engine_script.detect_release() == "R2024b"

    def test_posix_glob_pattern_components_match_six_char_releases(
        self, tmp_path, monkeypatch
    ):
        # The POSIX patterns are hardcoded absolute paths with no env seam, so
        # take their real wildcard component (e.g. "R20*", "MATLAB_R20*.app")
        # straight from the source and prove it matches a concrete 6-char
        # release dir/bundle on disk.
        monkeypatch.setattr(engine_script.sys, "platform", "linux")
        patterns = engine_script._glob_patterns()
        assert patterns, "expected POSIX glob patterns"
        for pattern in patterns:
            component = os.path.basename(pattern)
            assert "R20*" in component, f"broken wildcard in {component!r}"
            concrete = component.replace("R20*", "R2024b")
            base = tmp_path / component.replace("*", "_star")
            base.mkdir()
            (base / concrete).mkdir()
            matches = glob.glob(str(base / component))
            assert matches, f"real pattern component {component!r} matched nothing"
            assert engine_script._extract_release_token(matches[0]) == "R2024b"


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


# ---------------------------------------------------------------------------
# main(): whitelist pre-check skipped when offline is forced; clean error on
# a double (online+offline) failure instead of a raw traceback.
# ---------------------------------------------------------------------------


class TestMainOfflineForced:
    def test_offline_forced_skips_whitelist_precheck_for_unwhitelisted_release(
        self, monkeypatch, capsys
    ):
        # An unwhitelisted release (R2019a) fails resolve_engine_spec, but the
        # forced-offline path never consults the whitelist — main() must not
        # reject it at the pre-check and must install from the local tree.
        monkeypatch.setattr(engine_script, "detect_release", lambda: "R2019a")
        monkeypatch.setenv("MATLAB_MCP_VENDOR", "1")
        monkeypatch.setenv("MATLABROOT", "/opt/matlab/R2019a")
        calls = []
        monkeypatch.setattr(
            engine_script, "_run_pip_install", lambda args: calls.append(args)
        )
        assert engine_script.main() == 0
        assert calls == [["/opt/matlab/R2019a/extern/engines/python"]]
        assert "ERROR" not in capsys.readouterr().out


class TestMainDoubleFailure:
    def test_online_then_offline_failure_prints_clean_error(self, monkeypatch, capsys):
        # Online install fails, the offline fallback also fails with a
        # CalledProcessError. main() must catch it and print a clean ERROR
        # line (return 1), not leak a raw traceback.
        monkeypatch.setattr(engine_script, "detect_release", lambda: "R2024b")
        monkeypatch.setenv("MATLABROOT", "/opt/matlab/R2024b")

        def always_fail(args):
            raise subprocess.CalledProcessError(returncode=1, cmd=args)

        monkeypatch.setattr(engine_script, "_run_pip_install", always_fail)
        assert engine_script.main() == 1
        assert "ERROR:" in capsys.readouterr().out
