@echo off
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set EXIT_CODE=0

echo.
echo ============================================================================
echo meridinate-frontend - running ci checks
echo ============================================================================
echo.

where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [error] node not installed or not in path
    exit /b 1
)

where pnpm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [error] pnpm not installed or not in path
    echo install: npm install -g pnpm
    exit /b 1
)

cd /d "%SCRIPT_DIR%"

echo [1/5] installing dependencies...
echo ----------------------------------------------------------------------------
pnpm install --frozen-lockfile
if %ERRORLEVEL% NEQ 0 (
    echo [failed] dependency install
    exit /b 1
)
echo [ok] dependencies installed

echo.
echo [2/5] running eslint...
echo ----------------------------------------------------------------------------
pnpm lint
if %ERRORLEVEL% NEQ 0 (
    echo [failed] lint errors found
    set EXIT_CODE=1
) else (
    echo [ok] lint passed
)

echo.
echo [3/5] running eslint strict...
echo ----------------------------------------------------------------------------
pnpm lint:strict
if %ERRORLEVEL% NEQ 0 (
    echo [failed] lint strict found warnings
    set EXIT_CODE=1
) else (
    echo [ok] lint strict passed
)

echo.
echo [4/5] checking formatting...
echo ----------------------------------------------------------------------------
pnpm format:check
if %ERRORLEVEL% NEQ 0 (
    echo [failed] formatting issues found. run: pnpm format
    set EXIT_CODE=1
) else (
    echo [ok] formatting passed
)

echo.
echo [5/5] type checking...
echo ----------------------------------------------------------------------------
pnpm type-check
if %ERRORLEVEL% NEQ 0 (
    echo [failed] type errors found
    set EXIT_CODE=1
) else (
    echo [ok] type check passed
)

echo.
echo ============================================================================
if %EXIT_CODE% EQU 0 (
    echo [success] all checks passed
) else (
    echo [failed] some checks failed
    echo.
    echo quick fixes:
    echo   - formatting: pnpm format
    echo   - lint: pnpm lint:fix
)
echo ============================================================================

exit /b %EXIT_CODE%
