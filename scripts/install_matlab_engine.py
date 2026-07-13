"""Detect the installed MATLAB release and install the matching ``matlabengine``.

Single source of truth for MATLAB engine acquisition (D-01). ``matlabengine`` is
published on PyPI as an sdist only, and its build step reads the local MATLAB
installation and *raises* if no matching MATLAB is present. That means it must
never be a static project dependency (it would break ``pip install`` /
``pixi install`` / CI on any machine without that exact MATLAB release
installed). This script is the only place that installs it.

Flow:

1. Detect the installed MATLAB release (newest wins), via the Windows registry
   (non-admin readable) or, as a fallback / on POSIX, filesystem globs of the
   standard install locations. ``MATLAB_RELEASE`` overrides detection.
2. Map the release to the matching ``matlabengine==<major>.<minor>.*`` PyPI
   pin and pip-install it into the active environment.
3. Offline fallback (air-gapped installs, or PyPI unreachable): install from
   the local ``<MATLABROOT>/extern/engines/python`` tree instead. Forced by
   setting ``MATLAB_MCP_VENDOR``, or triggered automatically if the online
   pip install fails.

Called by both the pixi ``install-engine`` task and ``install.bat``.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Release -> matlabengine version map (verified, see 08-RESEARCH.md #1)
# ---------------------------------------------------------------------------
#
# Both the human-readable "R20XXx" release token and its numeric MathWorks
# registry-style equivalent (e.g. "24.2") map to the same matlabengine
# <major>.<minor> pin. This is a WHITELIST — resolve_engine_spec() rejects
# any token not present here, which is the injection guard required by the
# D-01 threat model (T-08-01-INJ): an unvalidated MATLAB_RELEASE env var or
# tampered registry value must never be interpolated into a pip spec.
RELEASE_TO_ENGINE: dict[str, str] = {
    "R2022b": "9.13",
    "9.13": "9.13",
    "R2023a": "9.14",
    "9.14": "9.14",
    "R2023b": "9.15",
    "9.15": "9.15",
    "R2024a": "24.1",
    "24.1": "24.1",
    "R2024b": "24.2",
    "24.2": "24.2",
    "R2025a": "25.1",
    "25.1": "25.1",
    "R2025b": "25.2",
    "25.2": "25.2",
    "R2026a": "26.1",
    "26.1": "26.1",
}

# Newest-wins ordering: canonical release order, oldest to newest. Both the
# "R20XXx" token and its numeric equivalent share a rank so detect_release()
# can compare mixed tokens discovered from different sources (registry vs.
# filesystem glob).
_RELEASE_RANK: dict[str, int] = {
    "R2022b": 0,
    "9.13": 0,
    "R2023a": 1,
    "9.14": 1,
    "R2023b": 2,
    "9.15": 2,
    "R2024a": 3,
    "24.1": 3,
    "R2024b": 4,
    "24.2": 4,
    "R2025a": 5,
    "25.1": 5,
    "R2025b": 6,
    "25.2": 6,
    "R2026a": 7,
    "26.1": 7,
}

_R_TOKEN_RE = re.compile(r"R20\d\d[ab]")


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _extract_release_token(path: str) -> Optional[str]:
    """Extract an "R20XXx" release token from an install path.

    Parameters
    ----------
    path : str
        A filesystem path or directory name, e.g.
        ``"C:\\Program Files\\MATLAB\\R2025a"`` or
        ``"/Applications/MATLAB_R2025a.app"``.

    Returns
    -------
    str or None
        The release token (e.g. ``"R2025a"``), or ``None`` if not found.
    """
    match = _R_TOKEN_RE.search(path)
    return match.group(0) if match else None


def _discover_releases_registry() -> list[str]:
    """Discover MATLAB releases from the Windows registry.

    Reads the non-admin-readable ``SOFTWARE\\MathWorks\\MATLAB`` subkeys
    under both ``HKEY_LOCAL_MACHINE`` and ``HKEY_CURRENT_USER``. Returns an
    empty list on any non-Windows platform (the ``winreg`` import is guarded
    so this module always imports cleanly on macOS/Linux).

    Returns
    -------
    list[str]
        Numeric registry-style release tokens found (e.g. ``["24.2"]``).
    """
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:  # pragma: no cover - defensive, win32-only import
        return []

    releases: list[str] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\MathWorks\MATLAB") as key:
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    releases.append(subkey_name)
                    index += 1
        except OSError:
            continue
    return releases


def _glob_patterns() -> list[str]:
    """Return platform-specific filesystem glob patterns for MATLAB installs."""
    if sys.platform == "win32":
        patterns = [r"C:\Program Files\MATLAB\R20*"]
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            patterns.append(os.path.join(local_appdata, "Programs", "MATLAB", "R20*"))
        return patterns
    return [
        "/usr/local/MATLAB/R20*",
        "/Applications/MATLAB_R20*.app",
    ]


def _discover_releases_glob() -> list[str]:
    """Discover MATLAB releases by globbing standard install locations.

    Returns
    -------
    list[str]
        "R20XXx" release tokens found on disk.
    """
    releases: list[str] = []
    for pattern in _glob_patterns():
        for path in glob.glob(pattern):
            token = _extract_release_token(path)
            if token:
                releases.append(token)
    return releases


def _discover_releases() -> list[str]:
    """Discover all MATLAB releases installed on this machine.

    Combines Windows registry results (if any) with filesystem glob results.
    Order is undefined; callers should pick the newest via ``_RELEASE_RANK``.

    Returns
    -------
    list[str]
        All discovered release tokens (mixed "R20XXx" and numeric forms).
    """
    return _discover_releases_registry() + _discover_releases_glob()


def _newest_release(tokens: list[str]) -> Optional[str]:
    """Return the newest known release token from a list, or ``None``.

    Unrecognized tokens (not present in ``_RELEASE_RANK``) are ignored rather
    than raising, since detection may pick up unrelated directories; the
    whitelist check happens later, in ``resolve_engine_spec``.
    """
    ranked = [(token, _RELEASE_RANK[token]) for token in tokens if token in _RELEASE_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda pair: pair[1])[0]


def detect_release() -> Optional[str]:
    """Detect the MATLAB release to install an engine for.

    Honors the ``MATLAB_RELEASE`` environment variable as an override — if
    set, it is returned as-is (still subject to the whitelist check in
    ``resolve_engine_spec`` before it can reach a pip spec). Otherwise,
    detects installed releases via the registry and filesystem globs and
    returns the newest.

    Returns
    -------
    str or None
        The detected (or overridden) release token, or ``None`` if nothing
        was found.
    """
    override = os.environ.get("MATLAB_RELEASE")
    if override:
        return override
    return _newest_release(_discover_releases())


# ---------------------------------------------------------------------------
# Whitelist gate: release token -> matlabengine pip spec
# ---------------------------------------------------------------------------


def resolve_engine_spec(token: str) -> str:
    """Validate a release token against the whitelist and build its pip spec.

    This is the security gate for the environment -> pip spec trust boundary
    (D-01 threat T-08-01-INJ): an unvalidated ``MATLAB_RELEASE`` env var,
    registry value, or directory name must never be interpolated into a pip
    install command. Only tokens present in ``RELEASE_TO_ENGINE`` are
    accepted.

    Parameters
    ----------
    token : str
        A MATLAB release token (e.g. ``"R2024b"``) or numeric registry-style
        token (e.g. ``"24.2"``).

    Returns
    -------
    str
        The pip install spec, e.g. ``"matlabengine==24.2.*"``.

    Raises
    ------
    ValueError
        If ``token`` is not a known, whitelisted release.
    """
    version = RELEASE_TO_ENGINE.get(token)
    if version is None:
        raise ValueError(
            f"Unknown/unsupported MATLAB release token: {token!r}. "
            f"Supported releases: {sorted(RELEASE_TO_ENGINE)}"
        )
    return f"matlabengine=={version}.*"


# ---------------------------------------------------------------------------
# Install (online pip seam + offline fallback)
# ---------------------------------------------------------------------------


def _run_pip_install(args: list[str]) -> subprocess.CompletedProcess:
    """Run ``pip install`` with the given extra args.

    This is the single injectable seam for pip invocation, so tests can
    patch it and assert on the exact argv without ever calling real pip.

    Parameters
    ----------
    args : list[str]
        Extra arguments appended to ``pip install`` (e.g. a version spec or
        a local path).

    Returns
    -------
    subprocess.CompletedProcess
        The completed pip subprocess.
    """
    cmd = [sys.executable, "-m", "pip", "install", *args]
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, check=True)


def _is_offline_forced() -> bool:
    """Return True if the offline (vendored/local-tree) install is forced."""
    return bool(os.environ.get("MATLAB_MCP_VENDOR"))


def _install_offline(matlab_root: str) -> None:
    """Install matlabengine from the local MATLAB installation tree.

    Parameters
    ----------
    matlab_root : str
        Root of the local MATLAB installation (e.g. ``MATLABROOT``).
    """
    target = os.path.join(matlab_root, "extern", "engines", "python")
    logger.info("Installing matlabengine from local tree: %s", target)
    _run_pip_install([target])


def install_engine(
    release: Optional[str] = None,
    matlab_root: Optional[str] = None,
) -> None:
    """Resolve and install the matching ``matlabengine`` for this machine.

    Installs the whitelisted PyPI ``matlabengine==<major>.<minor>.*`` spec by
    default. Falls back to the local ``<matlab_root>/extern/engines/python``
    tree (offline / air-gapped install) when ``MATLAB_MCP_VENDOR`` is set, or
    automatically if the online pip install fails (e.g. PyPI unreachable).

    Parameters
    ----------
    release : str, optional
        Release token to install for. Defaults to ``detect_release()``.
    matlab_root : str, optional
        Root of the local MATLAB installation, used only for the offline
        fallback path. Defaults to the ``MATLABROOT`` environment variable.

    Raises
    ------
    ValueError
        If the resolved release token is not whitelisted.
    RuntimeError
        If no MATLAB release could be detected, or the offline fallback path
        is required but no ``matlab_root`` is available.
    """
    resolved_release = release or detect_release()
    if resolved_release is None:
        raise RuntimeError(
            "No MATLAB installation detected. Set MATLAB_RELEASE to override "
            "detection, or pass matlab_root to point at a local installation."
        )

    root = matlab_root or os.environ.get("MATLABROOT")

    if _is_offline_forced():
        if not root:
            raise RuntimeError(
                "MATLAB_MCP_VENDOR is set but no MATLABROOT is available for "
                "the offline install."
            )
        _install_offline(root)
        return

    spec = resolve_engine_spec(resolved_release)
    try:
        _run_pip_install([spec])
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.warning(
            "Online install of %s failed (%s); falling back to offline install.",
            spec,
            exc,
        )
        if not root:
            raise RuntimeError(
                f"Online install of {spec} failed and no MATLABROOT is "
                "available for the offline fallback."
            ) from exc
        _install_offline(root)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Detect, resolve, and install the MATLAB engine for this machine.

    Returns
    -------
    int
        Process exit code (0 on success, 1 on failure).
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    release = detect_release()
    if release is None:
        print(
            "ERROR: No MATLAB installation detected. Set MATLAB_RELEASE to "
            "override detection."
        )
        return 1

    try:
        spec = resolve_engine_spec(release)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Detected MATLAB release: {release} -> {spec}")

    try:
        install_engine(release=release)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    print("matlabengine installed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
