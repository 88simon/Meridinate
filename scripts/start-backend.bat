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

echo Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo ✓ Virtual environment activated
) else (
    echo WARNING: Virtual environment not found at .venv
    echo Using system Python
)

echo.
echo Starting FastAPI backend...
echo Working directory: %CD%
echo.

cd src
python -m meridinate.main

pause
