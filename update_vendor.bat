@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
::  Refresh bundled vendor/ wheels for offline Windows installation.
::  Run this on a machine with internet access, then commit vendor/.
:: ============================================================================

echo.
echo  Updating vendor/ wheels for offline installation...
echo.

set "SCRIPT_DIR=%~dp0"
set "VENDOR_DIR=%SCRIPT_DIR%vendor"
set "REQ_FILE=%SCRIPT_DIR%requirements-lock.txt"

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

:: Download for Python 3.10, 3.11, 3.12 — Windows x64
for %%v in (310 311 312) do (
    echo  Downloading wheels for Python %%v win_amd64...
    pip download -r "%REQ_FILE%" --platform win_amd64 --python-version %%v --only-binary=:all: -d "%VENDOR_DIR%" --quiet 2>&1
)

echo.
echo  Done. Vendor directory:
dir /b "%VENDOR_DIR%\*.whl" | find /c ".whl"
echo  wheel files in %VENDOR_DIR%
echo.

pause
endlocal
