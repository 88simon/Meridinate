#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXIT_CODE=0

echo ""
echo "============================================================================"
echo "meridinate-frontend - running ci checks"
echo "============================================================================"
echo ""

if ! command -v node &> /dev/null; then
    echo "[error] node not installed or not in path"
    exit 1
fi

if ! command -v pnpm &> /dev/null; then
    echo "[error] pnpm not installed or not in path"
    echo "install: npm install -g pnpm"
    exit 1
fi

cd "$SCRIPT_DIR"

echo "[1/5] installing dependencies..."
echo "----------------------------------------------------------------------------"
pnpm install --frozen-lockfile || {
    echo "[failed] dependency install"
    exit 1
}
echo "[ok] dependencies installed"

echo ""
echo "[2/5] running eslint..."
echo "----------------------------------------------------------------------------"
if ! pnpm lint; then
    echo "[failed] lint errors found"
    EXIT_CODE=1
else
    echo "[ok] lint passed"
fi

echo ""
echo "[3/5] running eslint strict..."
echo "----------------------------------------------------------------------------"
if ! pnpm lint:strict; then
    echo "[failed] lint strict found warnings"
    EXIT_CODE=1
else
    echo "[ok] lint strict passed"
fi

echo ""
echo "[4/5] checking formatting..."
echo "----------------------------------------------------------------------------"
if ! pnpm format:check; then
    echo "[failed] formatting issues found. run: pnpm format"
    EXIT_CODE=1
else
    echo "[ok] formatting passed"
fi

echo ""
echo "[5/5] type checking..."
echo "----------------------------------------------------------------------------"
if ! pnpm type-check; then
    echo "[failed] type errors found"
    EXIT_CODE=1
else
    echo "[ok] type check passed"
fi

echo ""
echo "============================================================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo "[success] all checks passed"
else
    echo "[failed] some checks failed"
    echo ""
    echo "quick fixes:"
    echo "  - formatting: pnpm format"
    echo "  - lint: pnpm lint:fix"
fi
echo "============================================================================"

exit $EXIT_CODE
