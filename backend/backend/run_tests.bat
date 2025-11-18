@echo off
title Gun Del Sol - Test Suite
REM ============================================================================
REM Gun Del Sol - Test Runner
REM ============================================================================
REM Runs the pytest test suite for the modular FastAPI backend
REM ============================================================================

echo.
echo ============================================================================
echo Gun Del Sol - Test Suite
echo ============================================================================
echo.

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if pytest is installed
python -c "import pytest" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo pytest is not installed. Installing test dependencies...
    echo.
    python -m pip install pytest pytest-asyncio pytest-mock pytest-cov
    echo.
)

REM Run tests
echo Running test suite...
echo.

REM Run pytest with verbose output and coverage
python -m pytest -v --tb=short

echo.
echo ============================================================================
echo.

REM Check if tests passed
if %ERRORLEVEL% EQU 0 (
    echo [OK] All tests passed!
) else (
    echo [FAIL] Some tests failed. Check the output above.
)

echo.
echo To run specific tests:
echo   pytest tests/routers/test_watchlist.py
echo   pytest -m unit
echo   pytest -m integration
echo.
echo To generate coverage report:
echo   pytest --cov=app --cov-report=html
echo.

pause