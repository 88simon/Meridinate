@echo off
echo Testing start script...
echo.

REM Test venv check
if exist "%~dp0..\apps\backend\.venv\Scripts\python.exe" (
    echo [OK] Venv found
) else (
    echo [ERROR] Venv NOT found
    echo Path checked: %~dp0..\apps\backend\.venv\Scripts\python.exe
)

REM Test backend src
if exist "%~dp0..\apps\backend\src" (
    echo [OK] Backend src found
) else (
    echo [ERROR] Backend src NOT found
)

echo.
echo Press any key to exit...
pause
