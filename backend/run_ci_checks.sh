#!/bin/bash
# ============================================================================
# Gun Del Sol - Local CI Validation Script (Unix/Linux/macOS)
# ============================================================================
# Runs all CI checks locally before pushing to GitHub
# Mirrors the GitHub Actions workflows for quick feedback
# ============================================================================

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"
EXIT_CODE=0

echo ""
echo "============================================================================"
echo "Gun Del Sol - Running CI Checks Locally"
echo "============================================================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 is not installed or not in PATH"
    exit 1
fi

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed or not in PATH"
    exit 1
fi

echo "[1/7] Backend - Installing dependencies..."
echo "----------------------------------------------------------------------------"
cd "$BACKEND_DIR"
python3 -m pip install -r requirements-dev.txt --quiet || {
    echo "[FAILED] Failed to install backend dependencies"
    EXIT_CODE=1
    exit $EXIT_CODE
}
echo "[OK] Backend dependencies installed"

echo ""
echo "[2/7] Backend - Checking code formatting (Black)..."
echo "----------------------------------------------------------------------------"
if ! black --check --diff .; then
    echo "[FAILED] Black formatting issues found. Run: black ."
    EXIT_CODE=1
else
    echo "[OK] Code formatting passed"
fi

echo ""
echo "[3/7] Backend - Checking import sorting (isort)..."
echo "----------------------------------------------------------------------------"
if ! isort --check-only --diff .; then
    echo "[FAILED] Import sorting issues found. Run: isort ."
    EXIT_CODE=1
else
    echo "[OK] Import sorting passed"
fi

echo ""
echo "[4/7] Backend - Linting with flake8..."
echo "----------------------------------------------------------------------------"
if ! flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics; then
    echo "[FAILED] Flake8 found critical issues"
    EXIT_CODE=1
else
    echo "[OK] Linting passed"
fi

echo ""
echo "[5/7] Backend - Running tests with pytest..."
echo "----------------------------------------------------------------------------"
if ! pytest --cov=app --cov-report=term -v; then
    echo "[FAILED] Tests failed"
    EXIT_CODE=1
else
    echo "[OK] All tests passed"
fi

echo ""
echo "[6/7] Frontend - Checking linting and formatting..."
echo "----------------------------------------------------------------------------"
cd "$FRONTEND_DIR"

# Check if pnpm is available
if command -v pnpm &> /dev/null; then
    PKG_MANAGER="pnpm"
else
    echo "[WARNING] pnpm not found, using npm instead"
    PKG_MANAGER="npm"
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    $PKG_MANAGER install || {
        echo "[FAILED] Failed to install frontend dependencies"
        EXIT_CODE=1
        exit $EXIT_CODE
    }
fi

echo "Running ESLint strict..."
if ! $PKG_MANAGER run lint:strict; then
    echo "[FAILED] ESLint found issues. Run: pnpm lint:fix"
    EXIT_CODE=1
else
    echo "[OK] Linting passed"
fi

echo ""
echo "Checking Prettier formatting..."
if ! $PKG_MANAGER run format:check; then
    echo "[FAILED] Prettier found formatting issues. Run: pnpm format"
    EXIT_CODE=1
else
    echo "[OK] Formatting passed"
fi

echo ""
echo "[7/7] Frontend - Building Next.js application..."
echo "----------------------------------------------------------------------------"
export SKIP_ENV_VALIDATION=true
if ! $PKG_MANAGER run build; then
    echo "[FAILED] Build failed"
    EXIT_CODE=1
else
    echo "[OK] Build succeeded"
fi

echo ""
echo "============================================================================"
echo "CI Checks Summary"
echo "============================================================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "[SUCCESS] All checks passed! Ready to push."
    echo ""
else
    echo "[FAILED] Some checks failed. Please fix the issues above."
    echo ""
    echo "Quick fixes:"
    echo "  - Backend formatting: cd backend && black . && isort ."
    echo "  - Frontend formatting: cd ../frontend && pnpm lint:fix && pnpm format"
    echo "  - Run tests again: cd backend && pytest"
    echo ""
fi
echo "============================================================================"

cd "$SCRIPT_DIR"
exit $EXIT_CODE