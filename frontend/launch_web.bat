@echo off
title Meridinate - Frontend
REM ============================================================================
REM Meridinate - Frontend Launcher
REM ============================================================================
REM Starts the Next.js development server on http://localhost:3000
REM ============================================================================

set SCRIPT_DIR=%~dp0

REM Check if Node.js is installed
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Node.js is not installed or not in PATH
    echo.
    echo Please install Node.js from: https://nodejs.org/
    echo.
    pause
    exit /b 1
)

REM Check if pnpm is installed (this repo uses pnpm)
where pnpm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo pnpm is not installed. Installing via npm...
    echo.
    call npm install -g pnpm
    echo.
    REM Verify pnpm installation
    where pnpm >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo WARNING: pnpm not available after install, falling back to npm
        set USE_NPM=1
    ) else (
        echo pnpm installed successfully
        set USE_NPM=0
    )
) else (
    set USE_NPM=0
)

REM Check if node_modules exists
if not exist "%SCRIPT_DIR%node_modules" (
    echo Installing dependencies...
    echo.
    cd /d "%SCRIPT_DIR%"
    if "%USE_NPM%"=="1" (
        echo Using npm install...
        call npm install
    ) else (
        echo Using pnpm install ^(faster^)...
        call pnpm install
    )
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo ERROR: Failed to install dependencies
        echo.
        pause
        exit /b 1
    )
)

REM Start the Next.js development server
echo.
echo Starting Meridinate Frontend...
echo.
echo FastAPI ^(Primary^): http://localhost:5003
echo Flask API ^(Legacy^): http://localhost:5001
echo Frontend:          http://localhost:3000
echo.
cd /d "%SCRIPT_DIR%"
title Meridinate - Frontend
if "%USE_NPM%"=="1" (
    call npm run dev
) else (
    call pnpm dev
)
title Meridinate - Frontend

REM If we get here, the server was stopped
echo.
echo Frontend stopped.
pause
