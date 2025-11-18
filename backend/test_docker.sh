#!/bin/bash
# Test Docker setup for Gun Del Sol backend and frontend
# Run this from the backend (meridinate-backend) directory

set -e

echo "============================================================"
echo "Gun Del Sol - Docker Testing Script"
echo "============================================================"
echo

# Check if Docker is running
echo "[1/6] Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not running"
    echo "Please install Docker and try again"
    exit 1
fi
echo "[OK] Docker is installed"
echo

# Test Backend Docker Build
echo "[2/6] Building backend Docker image..."
if docker build -t gun-del-sol-backend-test . > /dev/null 2>&1; then
    echo "[OK] Backend image built successfully"
else
    echo "[ERROR] Backend Docker build failed"
    echo "Run: docker build -t gun-del-sol-backend-test ."
    exit 1
fi
echo

# Test Backend Docker Run
echo "[3/6] Testing backend container..."
docker run -d --name backend-test \
    -p 5003:5003 \
    -v "$(pwd)/backend/config.json:/app/config.json:ro" \
    -v "$(pwd)/backend/api_settings.json:/app/api_settings.json:ro" \
    -v "$(pwd)/backend/monitored_addresses.json:/app/monitored_addresses.json:ro" \
    gun-del-sol-backend-test

sleep 10
if docker logs backend-test 2>&1 | grep -qi "started\|running\|OK"; then
    echo "[OK] Backend container started"
else
    echo "[WARNING] Backend may not have started properly"
    echo "Check logs: docker logs backend-test"
fi

# Test backend health
echo "Testing backend health endpoint..."
sleep 5
if curl -f http://localhost:5003/api/settings > /dev/null 2>&1; then
    echo "[OK] Backend is responding"
else
    echo "[WARNING] Backend health check failed"
    echo "Check logs: docker logs backend-test"
fi

# Cleanup backend test
docker stop backend-test > /dev/null 2>&1 || true
docker rm backend-test > /dev/null 2>&1 || true
echo

# Test Frontend Docker Build
echo "[4/6] Building frontend Docker image..."
cd ../frontend
if docker build -t gun-del-sol-frontend-test . > /dev/null 2>&1; then
    echo "[OK] Frontend image built successfully"
else
    echo "[ERROR] Frontend Docker build failed"
    echo "Check: docker build -t gun-del-sol-frontend-test ."
    cd ../meridinate-backend
    exit 1
fi
echo

# Test Frontend Docker Run
echo "[5/6] Testing frontend container..."
docker run -d --name frontend-test \
    -p 3000:3000 \
    -e NEXT_PUBLIC_SENTRY_DISABLED=true \
    -e NEXT_TELEMETRY_DISABLED=1 \
    gun-del-sol-frontend-test

sleep 15
if docker logs frontend-test 2>&1 | grep -qi "ready\|started\|listening"; then
    echo "[OK] Frontend container started"
else
    echo "[WARNING] Frontend may not have started properly"
    echo "Check logs: docker logs frontend-test"
fi

# Test frontend health
echo "Testing frontend health endpoint..."
sleep 5
if curl -f http://localhost:3000/api/health > /dev/null 2>&1; then
    echo "[OK] Frontend is responding"
else
    echo "[WARNING] Frontend health check failed"
    echo "Check logs: docker logs frontend-test"
fi

# Cleanup frontend test
docker stop frontend-test > /dev/null 2>&1 || true
docker rm frontend-test > /dev/null 2>&1 || true
echo

# Test Docker Compose
echo "[6/6] Testing Docker Compose (full stack)..."
if docker-compose up -d; then
    echo "Waiting for services to start..."
    sleep 20

    echo "Checking backend service..."
    if docker-compose ps backend | grep -qi "Up\|running"; then
        echo "[OK] Backend service is running"
    else
        echo "[WARNING] Backend service not running"
        docker-compose logs backend
    fi

    echo "Checking frontend service..."
    if docker-compose ps frontend | grep -qi "Up\|running"; then
        echo "[OK] Frontend service is running"
    else
        echo "[WARNING] Frontend service not running"
        docker-compose logs frontend
    fi
else
    echo "[ERROR] Docker Compose failed to start"
    echo "Check: docker-compose logs"
    cd ../meridinate-backend
    exit 1
fi

echo
echo "============================================================"
echo "Docker Testing Complete!"
echo "============================================================"
echo
echo "To view logs:"
echo "  Backend:  docker-compose logs -f backend"
echo "  Frontend: docker-compose logs -f frontend"
echo
echo "To stop services:"
echo "  docker-compose down"
echo
echo "To access services:"
echo "  Backend:  http://localhost:5003"
echo "  Frontend: http://localhost:3000"
echo

cd ../meridinate-backend