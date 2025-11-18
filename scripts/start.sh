#!/bin/bash
# ============================================================
# Meridinate - Master Launcher (Monorepo)
# Starts all services: Backend (FastAPI), Frontend (Next.js)
# ============================================================

echo ""
echo "============================================================"
echo "Meridinate - Full Stack Launcher"
echo "============================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# [1/2] Launch FastAPI Backend
echo "[1/2] Starting FastAPI backend..."
if [ -d "$PROJECT_ROOT/apps/backend/src" ]; then
    cd "$PROJECT_ROOT/apps/backend/src"
    python -m meridinate.main &
    BACKEND_PID=$!
    echo "       Started: FastAPI (PID: $BACKEND_PID) - localhost:5003"
    sleep 2
else
    echo "       ERROR: Backend not found at apps/backend/src"
fi

echo ""

# [2/2] Launch Frontend
echo "[2/2] Starting frontend..."
if [ -f "$PROJECT_ROOT/apps/frontend/package.json" ]; then
    cd "$PROJECT_ROOT/apps/frontend"
    pnpm dev &
    FRONTEND_PID=$!
    echo "       Started: Frontend (PID: $FRONTEND_PID) - localhost:3000"
else
    echo "       ERROR: Frontend not found at apps/frontend"
fi

echo ""
echo "============================================================"
echo "All services started!"
echo "============================================================"
echo ""
echo "   Backend API:    http://localhost:5003"
echo "   Frontend:       http://localhost:3000"
echo "   API Docs:       http://localhost:5003/docs"
echo "   Health Check:   http://localhost:5003/health"
echo ""
echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for both processes
wait
