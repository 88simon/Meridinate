@echo off
REM ============================================================
REM Meridinate - Master Launcher (Monorepo)
REM Starts all services: AutoHotkey, Backend (FastAPI), Frontend (Next.js)
REM ============================================================

title Meridinate - Launcher

echo.
echo ============================================================
echo Meridinate - Full Stack Launcher
echo ============================================================
echo.
echo [Cleanup] Killing any existing processes...

REM Kill all existing Meridinate windows by title
taskkill /FI "WINDOWTITLE eq Meridinate - Backend*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Meridinate - FastAPI*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Meridinate - Frontend*" /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Meridinate - AutoHotkey*" /F >nul 2>nul

REM Kill processes on backend port 5003
echo   - Killing processes on port 5003 (backend)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5003 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>nul
)

REM Kill processes on frontend port 3000
echo   - Killing processes on port 3000 (frontend)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>nul
)

REM Kill any Python processes running meridinate
echo   - Killing Python processes running meridinate...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /I "PID:"') do (
    wmic process where "ProcessId=%%a AND CommandLine LIKE '%%meridinate%%'" delete >nul 2>nul
)

REM Kill any Node processes running Next.js dev
echo   - Killing Node.js processes running Next.js dev...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq node.exe" /FO LIST ^| findstr /I "PID:"') do (
    wmic process where "ProcessId=%%a AND CommandLine LIKE '%%next dev%%'" delete >nul 2>nul
)

echo   [OK] Cleanup complete
echo.

REM [1/3] Launch AutoHotkey action wheel
echo [1/3] Starting AutoHotkey action wheel...
echo       Checking: %~dp0..\tools\autohotkey\action_wheel.ahk
if exist "%~dp0..\tools\autohotkey\action_wheel.ahk" (
    start "" "%~dp0..\tools\autohotkey\action_wheel.ahk"
    timeout /t 1 /nobreak >nul
    echo       [OK] Started: action_wheel.ahk
) else (
    echo       [WARNING] AutoHotkey script not found
)

echo.

REM [2/3] Launch FastAPI Backend
echo [2/3] Starting FastAPI backend...
echo       Checking: %~dp0..\apps\backend\src
if exist "%~dp0..\apps\backend\src" (
    start "Meridinate - Backend" /D "%~dp0..\apps\backend" cmd /k "title Meridinate - FastAPI Backend && call .venv\Scripts\activate.bat && cd src && python -m meridinate.main"
    timeout /t 2 /nobreak >nul
    echo       [OK] Started: FastAPI (localhost:5003)
) else (
    echo       [ERROR] Backend not found at apps\backend\src
    echo       Script will continue anyway...
)

echo.

REM [3/3] Launch Frontend
echo [3/3] Starting frontend...
echo       Checking: %~dp0..\apps\frontend\package.json
if exist "%~dp0..\apps\frontend\package.json" (
    start "Meridinate - Frontend" /D "%~dp0..\apps\frontend" cmd /k "title Meridinate - Frontend && pnpm dev"
    timeout /t 2 /nobreak >nul
    echo       [OK] Started: Frontend (localhost:3000)
) else (
    echo       [ERROR] Frontend not found at apps\frontend\package.json
    echo       Script will continue anyway...
)

echo.
echo ============================================================
echo All services started!
echo ============================================================
echo.
echo   Backend API:    http://localhost:5003
echo   Frontend:       http://localhost:3000
echo   API Docs:       http://localhost:5003/docs
echo   Health Check:   http://localhost:5003/health
echo.
echo ============================================================
echo This window will stay open. Close it to stop all services.
echo CTRL+Click the URLs above to open them in your browser.
echo ============================================================
echo.
pause
