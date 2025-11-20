@echo off
title Meridinate - Debug Launcher

echo ============================================================
echo Meridinate - Debug Mode
echo ============================================================
echo.

REM Show current directory
echo Current directory: %CD%
echo Script directory: %~dp0
echo.

REM Test backend path
echo Testing backend path:
if exist "%~dp0..\apps\backend\src" (
    echo [OK] Backend src found
) else (
    echo [ERROR] Backend src NOT found
)
echo.

REM Test venv path
echo Testing venv path:
if exist "%~dp0..\apps\backend\.venv\Scripts\python.exe" (
    echo [OK] Venv Python found
    echo Path: %~dp0..\apps\backend\.venv\Scripts\python.exe
) else (
    echo [ERROR] Venv Python NOT found
    echo Looking for: %~dp0..\apps\backend\.venv\Scripts\python.exe
)
echo.

REM Test launching backend
echo Would launch backend with:
echo   Working dir: %~dp0..\apps\backend\src
echo   Command: ..\.venv\Scripts\python.exe -m meridinate.main
echo.

echo Press any key to test actual backend launch...
pause
echo.

echo Launching backend in new window...
start "Meridinate - Backend (Debug)" cmd /k "cd /d %~dp0..\apps\backend\src && echo Working directory: %CD% && echo Python: ..\.venv\Scripts\python.exe && echo. && echo Press any key to start backend... && pause && ..\.venv\Scripts\python.exe -m meridinate.main"

echo.
echo Backend window should have opened.
echo Check if it shows any errors.
echo.
pause
