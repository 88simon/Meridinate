@echo off
REM Test Docker setup for Gun Del Sol backend and frontend
REM Run this from the backend (meridinate-backend) directory

echo ============================================================
echo Gun Del Sol - Docker Testing Script
echo ============================================================
echo.

REM Check if Docker is running
echo [1/6] Checking Docker installation...
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not installed or not running
    echo Please install Docker Desktop and try again
    exit /b 1
)
echo [OK] Docker is installed
echo.

REM Test Backend Docker Build
echo [2/6] Building backend Docker image...
docker build -t gun-del-sol-backend-test . 2>&1 | findstr /C:"Successfully built" /C:"ERROR" /C:"failed"
if errorlevel 1 (
    echo [ERROR] Backend Docker build failed
    echo Run: docker build -t gun-del-sol-backend-test .
    exit /b 1
)
echo [OK] Backend image built successfully
echo.

REM Test Backend Docker Run
echo [3/6] Testing backend container...
docker run -d --name backend-test ^
    -p 5003:5003 ^
    -v "%cd%\backend\config.json:/app/config.json:ro" ^
    -v "%cd%\backend\api_settings.json:/app/api_settings.json:ro" ^
    -v "%cd%\backend\monitored_addresses.json:/app/monitored_addresses.json:ro" ^
    gun-del-sol-backend-test

timeout /t 10 /nobreak >nul
docker logs backend-test 2>&1 | findstr /C:"started" /C:"running" /C:"OK"
if errorlevel 1 (
    echo [WARNING] Backend may not have started properly
    echo Check logs: docker logs backend-test
) else (
    echo [OK] Backend container started
)

REM Test backend health
echo Testing backend health endpoint...
timeout /t 5 /nobreak >nul
curl -f http://localhost:5003/api/settings >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Backend health check failed
    echo Check logs: docker logs backend-test
) else (
    echo [OK] Backend is responding
)

REM Cleanup backend test
docker stop backend-test >nul 2>&1
docker rm backend-test >nul 2>&1
echo.

REM Test Frontend Docker Build
echo [4/6] Building frontend Docker image...
cd ..\frontend
docker build -t gun-del-sol-frontend-test . 2>&1 | findstr /C:"Successfully built" /C:"ERROR" /C:"failed"
if errorlevel 1 (
    echo [ERROR] Frontend Docker build failed
    echo Check: docker build -t gun-del-sol-frontend-test .
    cd ..\meridinate-backend
    exit /b 1
)
echo [OK] Frontend image built successfully
echo.

REM Test Frontend Docker Run
echo [5/6] Testing frontend container...
docker run -d --name frontend-test ^
    -p 3000:3000 ^
    -e NEXT_PUBLIC_SENTRY_DISABLED=true ^
    -e NEXT_TELEMETRY_DISABLED=1 ^
    gun-del-sol-frontend-test

timeout /t 15 /nobreak >nul
docker logs frontend-test 2>&1 | findstr /C:"ready" /C:"started" /C:"listening"
if errorlevel 1 (
    echo [WARNING] Frontend may not have started properly
    echo Check logs: docker logs frontend-test
) else (
    echo [OK] Frontend container started
)

REM Test frontend health
echo Testing frontend health endpoint...
timeout /t 5 /nobreak >nul
curl -f http://localhost:3000/api/health >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Frontend health check failed
    echo Check logs: docker logs frontend-test
) else (
    echo [OK] Frontend is responding
)

REM Cleanup frontend test
docker stop frontend-test >nul 2>&1
docker rm frontend-test >nul 2>&1
echo.

REM Test Docker Compose
echo [6/6] Testing Docker Compose (full stack)...
docker-compose up -d
if errorlevel 1 (
    echo [ERROR] Docker Compose failed to start
    echo Check: docker-compose logs
    cd ..\meridinate-backend
    exit /b 1
)

echo Waiting for services to start...
timeout /t 20 /nobreak >nul

echo Checking backend service...
docker-compose ps backend | findstr /C:"Up" /C:"running"
if errorlevel 1 (
    echo [WARNING] Backend service not running
    docker-compose logs backend
) else (
    echo [OK] Backend service is running
)

echo Checking frontend service...
docker-compose ps frontend | findstr /C:"Up" /C:"running"
if errorlevel 1 (
    echo [WARNING] Frontend service not running
    docker-compose logs frontend
) else (
    echo [OK] Frontend service is running
)

echo.
echo ============================================================
echo Docker Testing Complete!
echo ============================================================
echo.
echo To view logs:
echo   Backend:  docker-compose logs -f backend
echo   Frontend: docker-compose logs -f frontend
echo.
echo To stop services:
echo   docker-compose down
echo.
echo To access services:
echo   Backend:  http://localhost:5003
echo   Frontend: http://localhost:3000
echo.

cd ..\meridinate-backend