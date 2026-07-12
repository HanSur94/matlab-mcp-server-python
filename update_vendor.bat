@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
::  Refresh bundled vendor/ wheels for offline Windows installation.
::  Run this on a machine with internet access, then commit vendor/.
::
::  Produces: (1) the win_amd64 wheel closure for the pinned dependency set
::  (requirements-lock.txt) across Python 3.10/3.11/3.12, (2) the project's
::  own wheel (matlab-mcp-python), and (3) the matlabengine sdist (source
::  only -- MathWorks' build step must run on a machine with a matching
::  MATLAB install; see scripts/install_matlab_engine.py). NOTE:
::  requirements-lock.txt is deprecated in favor of pixi.lock; this script
::  is the one remaining consumer.
:: ============================================================================

echo.
echo  Updating vendor/ wheels for offline installation...
echo.

set "SCRIPT_DIR=%~dp0"
set "VENDOR_DIR=%SCRIPT_DIR%vendor"
set "REQ_FILE=%SCRIPT_DIR%requirements-lock.txt"

:: matlabengine release to vendor as source (sdist-only on PyPI; the build
:: step reads the Windows registry, so it can only be installed where a
:: matching MATLAB lives -- see scripts/install_matlab_engine.py). Bump this
:: to track the Dockerfile/docs default MATLAB release.
set "MATLABENGINE_VER=25.1.*"

if not exist "%REQ_FILE%" (
    echo  [ERROR] requirements-lock.txt not found.
    pause
    exit /b 1
)

:: Clean old wheels
if exist "%VENDOR_DIR%" (
    echo  Removing old wheels...
    rd /s /q "%VENDOR_DIR%"
)
mkdir "%VENDOR_DIR%"

:: Download the pinned dependency closure for Python 3.10, 3.11, 3.12 -- Windows x64
for %%v in (310 311 312) do (
    echo  Downloading wheels for Python %%v win_amd64...
    pip download -r "%REQ_FILE%" --platform win_amd64 --python-version %%v --only-binary=:all: -d "%VENDOR_DIR%" --quiet 2>&1
)

:: Build the project's own wheel (not in requirements-lock.txt; pip download
:: only fetches third-party deps, so the project must be wheel-built separately)
echo  Building project wheel...
pip wheel "%SCRIPT_DIR%." -w "%VENDOR_DIR%" --no-deps --quiet 2>&1

:: Fetch the matlabengine sdist (source only -- offline engine fallback).
:: --no-binary is required: matlabengine ships no wheels on PyPI, so
:: --only-binary (used above for the regular closure) would silently skip it.
echo  Fetching matlabengine %MATLABENGINE_VER% sdist...
pip download "matlabengine==%MATLABENGINE_VER%" --no-deps --no-binary :all: -d "%VENDOR_DIR%" --quiet 2>&1

:: Dedup: cryptography ships a single stable-ABI (abi3) wheel per release that
:: covers every supported CPython (3.10+), so downloading it once per
:: Python version above can leave redundant same-package/different-tag
:: wheels around after a lock bump. Keep only the newest tag, drop the rest.
echo  Deduping redundant cryptography wheels...
set "KEEP_FIRST=1"
for /f "delims=" %%f in ('dir /b /o-n "%VENDOR_DIR%\cryptography-*.whl" 2^>nul') do (
    if defined KEEP_FIRST (
        set "KEEP_FIRST="
    ) else (
        echo   Removing redundant %%f
        del "%VENDOR_DIR%\%%f"
    )
)

echo.
echo  Done. Vendor directory:
dir /b "%VENDOR_DIR%\*.whl" | find /c ".whl"
echo  wheel files in %VENDOR_DIR%
echo.

pause
endlocal
