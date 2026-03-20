@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
::  MATLAB MCP Server - One-Click Windows Installer  (no admin rights needed)
::  https://github.com/HanSur94/matlab-mcp-server-python
:: ============================================================================

title MATLAB MCP Server Installer

echo.
echo  ============================================================
echo   MATLAB MCP Server - Windows Installer v1.3.0
echo   (no administrator rights required)
echo  ============================================================
echo.

:: ----------------------------------------------------------------------------
:: 1. Determine install directory (must be user-writable)
:: ----------------------------------------------------------------------------
set "INSTALL_DIR=%~dp0"

:: Quick writability test — try to create and delete a temp file
set "_PROBE=%INSTALL_DIR%_install_probe.tmp"
echo probe > "%_PROBE%" 2>nul
if not exist "%_PROBE%" (
    echo  [INFO] Script directory is not writable: %INSTALL_DIR%
    echo         Falling back to %%LOCALAPPDATA%%\matlab-mcp ...
    set "INSTALL_DIR=%LOCALAPPDATA%\matlab-mcp\"
    if not exist "!INSTALL_DIR!" mkdir "!INSTALL_DIR!"
) else (
    del "%_PROBE%" >nul 2>&1
)

:: ----------------------------------------------------------------------------
:: 2. Check Python
:: ----------------------------------------------------------------------------
echo  [1/6] Checking Python installation...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is not installed or not in PATH.
    echo.
    echo  Please install Python 3.10+ from https://www.python.org/downloads/
    echo  IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYTHON_VERSION=%%v
echo  Found Python %PYTHON_VERSION%

:: Check minimum version (3.10)
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% lss 3 (
    echo  [ERROR] Python 3.10+ is required. Found %PYTHON_VERSION%.
    pause
    exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 10 (
    echo  [ERROR] Python 3.10+ is required. Found %PYTHON_VERSION%.
    pause
    exit /b 1
)
echo  [OK] Python version is compatible.
echo.

:: ----------------------------------------------------------------------------
:: 3. Detect MATLAB
:: ----------------------------------------------------------------------------
echo  [2/6] Detecting MATLAB installation...

set "MATLAB_FOUND="
set "MATLAB_ROOT="
set "MATLAB_VER="
set "HAS_ENGINE_API="

:: MATLAB R2022b is the minimum version with Python 3.10 support.
:: Compatibility: R2022b (3.8-3.10), R2023a (3.8-3.10), R2023b (3.9-3.11),
::                R2024a (3.9-3.11), R2024b (3.10-3.12), R2025a (3.10-3.12)
set "MATLAB_MIN_VER=R2022b"

:: Search common MATLAB install locations (all readable without admin)
:: Picks the latest installed version (reverse-sorted by name)
for %%d in (
    "C:\Program Files\MATLAB"
    "C:\Program Files (x86)\MATLAB"
    "%USERPROFILE%\MATLAB"
    "D:\Program Files\MATLAB"
    "D:\MATLAB"
    "E:\Program Files\MATLAB"
    "E:\MATLAB"
) do (
    if exist "%%~d" (
        for /f "delims=" %%r in ('dir /b /ad /o-n "%%~d\R*" 2^>nul') do (
            if not defined MATLAB_FOUND (
                set "MATLAB_ROOT=%%~d\%%r"
                set "MATLAB_VER=%%r"
                set "MATLAB_FOUND=1"
            )
        )
    )
)

:: Check if the detected version is too old for Python 3.10+
if defined MATLAB_FOUND (
    set "_VER_OK="
    :: Extract year from version string (e.g., R2022b -> 2022)
    set "_MVER=!MATLAB_VER!"
    set "_MYEAR=!_MVER:~1,4!"
    set "_MSUF=!_MVER:~5,1!"
    :: R2022b+ required: year>2022, or year==2022 and suffix>=b
    if !_MYEAR! gtr 2022 set "_VER_OK=1"
    if !_MYEAR! equ 2022 if /i "!_MSUF!" geq "b" set "_VER_OK=1"
    if not defined _VER_OK (
        echo  [WARNING] Found !MATLAB_VER! but it does NOT support Python 3.10+.
        echo            This server requires Python 3.10+ and MATLAB R2022b or newer.
        echo.
        echo            MATLAB Python compatibility:
        echo              R2022b : Python 3.8, 3.9, 3.10
        echo              R2023a : Python 3.8, 3.9, 3.10
        echo              R2023b : Python 3.9, 3.10, 3.11
        echo              R2024a : Python 3.9, 3.10, 3.11
        echo              R2024b : Python 3.10, 3.11, 3.12
        echo              R2025a : Python 3.10, 3.11, 3.12
        echo.
        echo  Ignoring incompatible !MATLAB_VER!. You can upgrade MATLAB or
        echo  provide a path to a compatible installation below.
        echo.
        set "MATLAB_FOUND="
        set "MATLAB_ROOT="
        set "MATLAB_VER="
    )
)

if not defined MATLAB_FOUND (
    echo  [WARNING] No compatible MATLAB found (R2022b or newer required^).
    echo.
    echo  Enter your MATLAB installation path (e.g., C:\Program Files\MATLAB\R2024a^)
    echo  or press Enter to skip MATLAB Engine installation:
    echo.
    set /p "MATLAB_ROOT=  MATLAB path: "
    if "!MATLAB_ROOT!"=="" (
        echo.
        echo  [SKIP] Skipping MATLAB Engine API installation.
        echo         You will need to install it manually later.
        echo         See: https://github.com/HanSur94/matlab-mcp-server-python#prerequisites
        echo.
        goto :create_venv
    )
    set "MATLAB_VER=custom"
)

echo  Found MATLAB at: !MATLAB_ROOT!

:: Verify the MATLAB Engine API directory exists
set "ENGINE_API_DIR=!MATLAB_ROOT!\extern\engines\python"
if not exist "!ENGINE_API_DIR!" (
    echo  [WARNING] MATLAB Engine API not found at:
    echo            !ENGINE_API_DIR!
    echo.
    echo  Your MATLAB version may not include the Engine API for Python.
    echo  Continuing with MCP server installation only...
    echo.
) else (
    set "HAS_ENGINE_API=1"
    echo  [OK] MATLAB Engine API found.
)
echo.

:: ----------------------------------------------------------------------------
:: 4. Create virtual environment (user-local, no admin needed)
:: ----------------------------------------------------------------------------
:create_venv
echo  [3/6] Creating Python virtual environment...

set "VENV_DIR=%INSTALL_DIR%.venv"

if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo  Virtual environment already exists. Reusing it.
) else (
    python -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment at %VENV_DIR%.
        pause
        exit /b 1
    )
)

:: Activate
call "%VENV_DIR%\Scripts\activate.bat"
echo  [OK] Virtual environment ready at %VENV_DIR%
echo.

:: ----------------------------------------------------------------------------
:: 5. Install MATLAB Engine API (into the venv — no admin needed)
:: ----------------------------------------------------------------------------
echo  [4/6] Installing MATLAB Engine API for Python...

if not defined HAS_ENGINE_API (
    echo  Skipped — MATLAB Engine API directory not available.
    echo.
    goto :install_mcp
)

python -c "import matlab.engine" >nul 2>&1
if %errorlevel% equ 0 (
    echo  MATLAB Engine API already installed. Skipping.
) else (
    echo  Installing from !ENGINE_API_DIR! ...
    pip install "!ENGINE_API_DIR!" --quiet 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo  [WARNING] MATLAB Engine API installation failed.
        echo            This can happen if your MATLAB version is incompatible
        echo            with Python %PYTHON_VERSION%.
        echo.
        echo            To install manually later, run:
        echo              call "%VENV_DIR%\Scripts\activate.bat"
        echo              pip install "!ENGINE_API_DIR!"
        echo.
        echo  Continuing with MCP server installation...
    ) else (
        echo  [OK] MATLAB Engine API installed.
    )
)
echo.

:: ----------------------------------------------------------------------------
:: 6. Install MATLAB MCP Server (into the venv — no admin needed)
:: ----------------------------------------------------------------------------
:install_mcp
echo  [5/6] Installing MATLAB MCP Server...

:: Prefer local source if available, otherwise pull from PyPI
set "SOURCE_DIR=%~dp0"
if exist "%SOURCE_DIR%pyproject.toml" (
    echo  Installing from local source...
    pip install -e "%SOURCE_DIR%." --quiet
) else (
    echo  Installing from PyPI...
    pip install matlab-mcp-python --quiet
)

if %errorlevel% neq 0 (
    echo  [ERROR] Failed to install MATLAB MCP Server.
    pause
    exit /b 1
)
echo  [OK] MATLAB MCP Server installed.
echo.

:: ----------------------------------------------------------------------------
:: 7. Create data directories and launch script (all under user profile)
:: ----------------------------------------------------------------------------
echo  [6/6] Setting up configuration...

set "DATA_DIR=%LOCALAPPDATA%\matlab-mcp"

if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"
if not exist "%DATA_DIR%\results" mkdir "%DATA_DIR%\results"
if not exist "%DATA_DIR%\temp" mkdir "%DATA_DIR%\temp"
if not exist "%DATA_DIR%\monitoring" mkdir "%DATA_DIR%\monitoring"

:: Write a launch helper next to the venv
set "LAUNCH_SCRIPT=%INSTALL_DIR%start-matlab-mcp.bat"
(
    echo @echo off
    echo setlocal
    echo call "%VENV_DIR%\Scripts\activate.bat"
    echo matlab-mcp %%*
) > "%LAUNCH_SCRIPT%"

echo  [OK] Configuration ready.
echo.

:: ----------------------------------------------------------------------------
:: 8. Verify installation
:: ----------------------------------------------------------------------------
echo  ============================================================
echo   Verifying installation...
echo  ============================================================
echo.

python -c "from matlab_mcp.server import main; print('  [OK] matlab-mcp server module loads correctly')"
if %errorlevel% neq 0 (
    echo  [WARNING] Server module could not be imported. Check the errors above.
)

python -c "import matlab.engine; print('  [OK] MATLAB Engine API is available')" 2>nul
if %errorlevel% neq 0 (
    echo  [INFO] MATLAB Engine API not yet available — install it before running.
)

echo.
echo  ============================================================
echo   Installation Complete!  (no admin rights were needed)
echo  ============================================================
echo.
echo  QUICK START:
echo  ----------------------------------------------------------
echo.
echo  Start the server:
echo    "%LAUNCH_SCRIPT%"
echo.
echo  Or activate the venv manually:
echo    call "%VENV_DIR%\Scripts\activate.bat"
echo    matlab-mcp
echo.
echo  ----------------------------------------------------------
echo  CONNECT TO AI TOOLS:
echo  ----------------------------------------------------------
echo.
echo  Claude Desktop (%%APPDATA%%\Claude\claude_desktop_config.json):
echo    {
echo      "mcpServers": {
echo        "matlab": {
echo          "command": "%VENV_DIR%\Scripts\matlab-mcp.exe"
echo        }
echo      }
echo    }
echo.
echo  Claude Code:
echo    claude mcp add matlab -- "%VENV_DIR%\Scripts\matlab-mcp.exe"
echo.
echo  Cursor (.cursor/mcp.json in your project):
echo    {
echo      "mcpServers": {
echo        "matlab": {
echo          "command": "%VENV_DIR%\Scripts\matlab-mcp.exe"
echo        }
echo      }
echo    }
echo.
echo  ----------------------------------------------------------
echo  Data directory:        %DATA_DIR%
echo  Virtual environment:   %VENV_DIR%
echo  ----------------------------------------------------------
echo.

pause
endlocal
