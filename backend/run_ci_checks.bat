@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM Gun Del Sol - Local CI Validation Script
REM ============================================================================
REM Runs all CI checks locally before pushing to GitHub
REM Mirrors the GitHub Actions workflows for quick feedback
REM ============================================================================

title Gun Del Sol - CI Checks

set SCRIPT_DIR=%~dp0
set BACKEND_DIR=%SCRIPT_DIR%backend
set FRONTEND_DIR=%SCRIPT_DIR%..\frontend
set EXIT_CODE=0

echo.
echo ============================================================================
echo Gun Del Sol - Running CI Checks Locally
echo ============================================================================
echo.

REM Check if Python is available
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH
    exit /b 1
)

REM Check if Node.js is available
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Node.js is not installed or not in PATH
    exit /b 1
)

echo [1/7] Backend - Installing dependencies...
echo ----------------------------------------------------------------------------
cd /d "%BACKEND_DIR%"
pip install -r requirements-dev.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Failed to install backend dependencies
    set EXIT_CODE=1
    goto frontend_checks
)
echo [OK] Backend dependencies installed

echo.
echo [2/7] Backend - Checking code formatting (Black)...
echo ----------------------------------------------------------------------------
black --check --diff .
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Black formatting issues found. Run: black .
    set EXIT_CODE=1
) else (
    echo [OK] Code formatting passed
)

echo.
echo [3/7] Backend - Checking import sorting (isort)...
echo ----------------------------------------------------------------------------
isort --check-only --diff .
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Import sorting issues found. Run: isort .
    set EXIT_CODE=1
) else (
    echo [OK] Import sorting passed
)

echo.
echo [4/7] Backend - Linting with flake8...
echo ----------------------------------------------------------------------------
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Flake8 found critical issues
    set EXIT_CODE=1
) else (
    echo [OK] Linting passed
)

echo.
echo [5/7] Backend - Running tests with pytest...
echo ----------------------------------------------------------------------------
pytest --cov=app --cov-report=term -v
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Tests failed
    set EXIT_CODE=1
) else (
    echo [OK] All tests passed
)

:frontend_checks
echo.
echo [6/7] Frontend - Checking linting and formatting...
echo ----------------------------------------------------------------------------
cd /d "%FRONTEND_DIR%"

REM Check if pnpm is available
where pnpm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] pnpm not found, using npm instead
    set PKG_MANAGER=npm
    set RUN_CMD=run
) else (
    set PKG_MANAGER=pnpm
    set RUN_CMD=
)

REM Check if node_modules exists
if not exist "node_modules" (
    echo Installing frontend dependencies...
    %PKG_MANAGER% install
    if %ERRORLEVEL% NEQ 0 (
        echo [FAILED] Failed to install frontend dependencies
        set EXIT_CODE=1
        goto summary
    )
)

echo Running ESLint strict...
%PKG_MANAGER% %RUN_CMD% lint:strict
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] ESLint found issues. Run: pnpm lint:fix
    set EXIT_CODE=1
) else (
    echo [OK] Linting passed
)

echo.
echo Checking Prettier formatting...
%PKG_MANAGER% %RUN_CMD% format:check
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Prettier found formatting issues. Run: pnpm format
    set EXIT_CODE=1
) else (
    echo [OK] Formatting passed
)

echo.
echo [7/7] Frontend - Building Next.js application...
echo ----------------------------------------------------------------------------
set SKIP_ENV_VALIDATION=true
%PKG_MANAGER% %RUN_CMD% build
if %ERRORLEVEL% NEQ 0 (
    echo [FAILED] Build failed
    set EXIT_CODE=1
) else (
    echo [OK] Build succeeded
)

:summary
echo.
echo ============================================================================
echo CI Checks Summary
echo ============================================================================
if %EXIT_CODE% EQU 0 (
    echo [SUCCESS] All checks passed! Ready to push.
    echo.
) else (
    echo [FAILED] Some checks failed. Please fix the issues above.
    echo.
    echo Quick fixes:
    echo   - Backend formatting: cd backend ^&^& black . ^&^& isort .
    echo   - Frontend formatting: cd ..\frontend ^&^& pnpm lint:fix ^&^& pnpm format
    echo   - Run tests again: cd backend ^&^& pytest
    echo.
)
echo ============================================================================

cd /d "%SCRIPT_DIR%"
exit /b %EXIT_CODE%