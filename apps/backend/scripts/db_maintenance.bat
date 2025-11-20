@echo off
REM SQLite Database Maintenance Runner
REM Runs database maintenance tasks (VACUUM, ANALYZE, integrity check)

cd /d "%~dp0\.."

echo ========================================
echo SQLite Database Maintenance
echo ========================================
echo.

REM Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo Warning: Virtual environment not found at .venv
    echo Attempting to use system Python...
)

REM Run maintenance script
python scripts\db_maintenance.py --all

echo.
echo ========================================
echo Maintenance Complete
echo ========================================
pause
