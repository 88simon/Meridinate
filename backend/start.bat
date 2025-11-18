@echo off
title Meridinate - Launcher
REM ============================================================================
REM Meridinate - Master Launcher
REM ============================================================================
REM Starts all Meridinate services:
REM   1. AutoHotkey action wheel (action_wheel.ahk)
REM   2. FastAPI backend (localhost:5003) - REST API + WebSocket
REM   3. Next.js frontend dashboard (localhost:3000) - Main UI
REM ============================================================================

REM Kill any existing services (idempotent startup)
echo Checking for existing services...

REM Kill all existing Meridinate windows by title
taskkill /FI "WINDOWTITLE eq Meridinate - Backend*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Meridinate - FastAPI*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Meridinate - Frontend*" /F >nul 2>nul

REM Also kill by port (fallback for any orphaned processes)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    echo   Killing process on port 3000 (PID: %%a)
    taskkill /F /PID %%a >nul 2>nul
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5003 " ^| findstr "LISTENING"') do (
    echo   Killing process on port 5003 (PID: %%a)
    taskkill /F /PID %%a >nul 2>nul
)

echo Cleaned up all existing services.

REM Wait for ports to be fully released (prevents "address already in use" errors)
echo Waiting for ports to release...
timeout /t 3 /nobreak >nul
echo.

echo ============================================================================
echo Meridinate - Starting all services...
echo ============================================================================
echo.

REM Launch AutoHotkey script
echo [1/3] Starting AutoHotkey action wheel...
if exist "%~dp0action_wheel.ahk" (
    start "Meridinate - Action Wheel" "%~dp0action_wheel.ahk"
    echo       Started: action_wheel.ahk
) else (
    echo       WARNING: action_wheel.ahk not found
)
echo.

REM Launch Backend API (FastAPI with integrated WebSocket)
echo [2/3] Starting FastAPI backend...
if exist "%~dp0start_backend.bat" (
    start "Meridinate - Backend" /D "%~dp0" cmd /k start_backend.bat
    echo       Started: FastAPI ^(localhost:5003^) - REST API + WebSocket
) else (
    echo       WARNING: start_backend.bat not found
)
echo.

REM Launch Frontend
echo [3/3] Starting frontend...
if exist "%~dp0..\frontend\launch_web.bat" (
    start "Meridinate - Frontend" /D "%~dp0..\frontend" cmd /k "title Meridinate - Frontend && launch_web.bat"
    echo       Started: Frontend ^(localhost:3000^)
) else (
    echo       WARNING: ..\frontend\launch_web.bat not found
)
echo.

echo ============================================================================
echo All services started!
echo ============================================================================
echo.
echo Action Wheel:            Running in background
echo FastAPI Backend:         http://localhost:5003
echo   - REST API:            http://localhost:5003/health
echo   - WebSocket:           ws://localhost:5003/ws
echo Frontend Dashboard:      http://localhost:3000
echo.
echo NOTE: Access the dashboard at http://localhost:3000
echo       FastAPI handles all API requests and real-time notifications
echo       WebSocket support integrated for instant analysis updates
echo.
echo Close the individual windows to stop each service.
echo ============================================================================
echo.
pause
