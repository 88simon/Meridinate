@echo off
REM ============================================================
REM Meridinate - Frontend Only Launcher
REM Starts Next.js frontend development server
REM ============================================================

title Meridinate - Frontend Launcher

echo.
echo ============================================================
echo Meridinate - Frontend Service
echo ============================================================
echo.
echo [Cleanup] Killing any existing frontend processes...

REM Kill processes on frontend port 3000
echo   - Killing processes on port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo     Killing PID %%a
    taskkill /PID %%a /F
)

REM Kill any Node processes running Next.js dev
echo   - Killing Node.js processes running Next.js dev...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq node.exe" /FO LIST ^| findstr /I "PID:"') do (
    wmic process where "ProcessId=%%a AND CommandLine LIKE '%%next dev%%'" delete >nul 2>nul
)

echo   [OK] Cleanup complete
echo.

cd /d "%~dp0..\apps\frontend"

if not exist "package.json" (
    echo ERROR: Frontend not found at apps\frontend
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Starting Next.js development server...
echo Working directory: %CD%
echo.

pnpm dev

pause
