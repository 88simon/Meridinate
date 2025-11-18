@echo off
title Meridinate - FastAPI Backend
REM ============================================================================
REM Meridinate - FastAPI Backend Launcher
REM ============================================================================
REM Starts the FastAPI service (REST API + WebSocket notifications)
REM Provides endpoints for token analysis, wallet tagging, and data management
REM Real-time WebSocket notifications for analysis completion
REM Use the Next.js frontend at localhost:3000 for the user interface
REM ============================================================================

REM NOTE: Port cleanup is handled by start.bat before launching this script
REM This script can be run standalone, so we also cleanup here as a fallback
echo Checking for existing backend services...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5003 " ^| findstr "LISTENING"') do (
    echo   Killing FastAPI on port 5003 (PID: %%a)
    taskkill /F /PID %%a >nul 2>nul
)
echo Cleaned up any existing services.

REM Wait longer for ports to be fully released (prevents "address already in use" errors)
echo Waiting for ports to release...
timeout /t 3 /nobreak >nul
echo.

set SCRIPT_DIR=%~dp0backend\

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.8+ from: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

REM Check if FastAPI is installed
python -c "import fastapi" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo FastAPI is not installed. Installing dependencies...
    echo.
    python -m pip install fastapi uvicorn[standard]
    echo.
    REM Check if FastAPI installed successfully (ignore pip warnings)
    python -c "import fastapi" 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install FastAPI
        echo Please manually run: pip install fastapi uvicorn[standard]
        echo.
        pause
        exit /b 1
    ) else (
        echo FastAPI installed successfully.
    )
)

REM Check if aiofiles is installed (async file I/O)
python -c "import aiofiles" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo aiofiles is not installed. Installing...
    echo.
    python -m pip install aiofiles
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install aiofiles
        echo Please manually run: pip install aiofiles
        echo.
        pause
        exit /b 1
    ) else (
        echo aiofiles installed successfully.
    )
)

REM Check if httpx is installed (async HTTP client)
python -c "import httpx" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo httpx is not installed. Installing...
    echo.
    python -m pip install httpx
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install httpx
        echo Please manually run: pip install httpx
        echo.
        pause
        exit /b 1
    ) else (
        echo httpx installed successfully.
    )
)

REM Check if aiosqlite is installed (async database)
python -c "import aiosqlite" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo aiosqlite is not installed. Installing...
    echo.
    python -m pip install aiosqlite
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install aiosqlite
        echo Please manually run: pip install aiosqlite
        echo.
        pause
        exit /b 1
    ) else (
        echo aiosqlite installed successfully.
    )
)

REM Check if orjson is installed (fast JSON serialization)
python -c "import orjson" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo orjson is not installed. Installing...
    echo.
    python -m pip install orjson
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install orjson
        echo Please manually run: pip install orjson
        echo.
        pause
        exit /b 1
    ) else (
        echo orjson installed successfully.
        echo.
    )
)

REM Start the FastAPI service (now includes WebSocket support)
echo.
echo Starting FastAPI service (REST + WebSocket) - Modular Architecture...
echo [DEBUG] Window will pause on error - check for error messages
start "Meridinate - FastAPI" cmd /k "cd /d "%SCRIPT_DIR%" && python -m uvicorn app.main:app --port 5003"
echo Waiting for FastAPI to start...
timeout /t 3 /nobreak >nul

REM Verify FastAPI started successfully
curl -s http://localhost:5003/health >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] FastAPI server started successfully on port 5003
) else (
    echo [WARNING] FastAPI may not have started - check the FastAPI window for errors
    echo            If the window closed immediately, there may be missing dependencies
    echo            Run: pip install -r "%SCRIPT_DIR%requirements.txt"
)
echo.

REM Keep FastAPI running in foreground
echo.
echo ============================================================================
echo Meridinate Backend - FastAPI Service Running (Modular Architecture)
echo ============================================================================
echo.
echo FastAPI (REST + WebSocket): http://localhost:5003
echo WebSocket endpoint:         ws://localhost:5003/ws
echo Health check:               http://localhost:5003/health
echo Frontend Dashboard:         http://localhost:3000
echo.
echo Note: Using modular architecture (app.main:app)
echo ============================================================================
echo.
echo Press Ctrl+C to stop the backend service
echo The FastAPI window will remain open until you close it
echo.
pause