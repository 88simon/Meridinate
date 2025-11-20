@echo off
REM ============================================================
REM Meridinate - Backend Only Launcher
REM Starts FastAPI backend service
REM ============================================================

title Meridinate - Backend Launcher

echo.
echo ============================================================
echo Meridinate - Backend Service
echo ============================================================
echo.
echo [Cleanup] Killing any existing backend processes...

REM Kill processes on backend port 5003
echo   - Killing processes on port 5003...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5003 ^| findstr LISTENING') do (
    echo     Killing PID %%a
    taskkill /PID %%a /F
)

REM Kill any Python processes running meridinate
echo   - Killing Python processes running meridinate...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr /I "PID:"') do (
    wmic process where "ProcessId=%%a AND CommandLine LIKE '%%meridinate%%'" delete >nul 2>nul
)

echo   [OK] Cleanup complete
echo.

cd /d "%~dp0..\apps\backend"

if not exist "src\meridinate" (
    echo ERROR: Backend source not found at apps\backend\src\meridinate
    echo Current directory: %CD%
    pause
    exit /b 1
)

echo Checking virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo ✓ Virtual environment found at .venv
) else (
    echo ERROR: Virtual environment not found at .venv
    echo Please run: python -m venv .venv
    echo Then: .venv\Scripts\activate.bat
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo Starting FastAPI backend...
echo Working directory: %CD%
echo Python: %CD%\.venv\Scripts\python.exe
echo.

cd src
..\.venv\Scripts\python.exe -m meridinate.main

pause
