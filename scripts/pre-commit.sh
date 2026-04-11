#!/usr/bin/env bash
# Pre-commit hook replicating all CI checks from .github/workflows/ci.yml
# Checks: ruff lint, ruff format, mypy type check, compile smoke test
#
# Install: cp scripts/pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
# Or:      ln -sf ../../scripts/pre-commit.sh .git/hooks/pre-commit

set -euo pipefail

HOOKS_DIR=".claude/hooks"
FAILED=0

# Resolve repo root (works in worktrees too)
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "pre-commit: $HOOKS_DIR not found, skipping checks"
    exit 0
fi

echo "=== pre-commit: Running CI checks ==="

# 1. Ruff lint
echo ""
echo "--- ruff check ---"
if ! ruff check "$HOOKS_DIR"; then
    echo "FAIL: ruff check found lint errors"
    FAILED=1
fi

# 2. Ruff format
echo ""
echo "--- ruff format --check ---"
if ! ruff format --check "$HOOKS_DIR"; then
    echo "FAIL: ruff format found formatting issues (run: ruff format $HOOKS_DIR)"
    FAILED=1
fi

# 3. Mypy type check
echo ""
echo "--- mypy ---"
if ! mypy "$HOOKS_DIR" --ignore-missing-imports --no-error-summary; then
    echo "FAIL: mypy found type errors"
    FAILED=1
fi

# 4. Smoke test — all hooks compile
echo ""
echo "--- compile check ---"
for f in "$HOOKS_DIR"/*.py; do
    if ! python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>&1; then
        echo "FAIL: $f failed to compile"
        FAILED=1
    fi
done

echo ""
if [ "$FAILED" -ne 0 ]; then
    echo "=== pre-commit: FAILED — fix errors before committing ==="
    exit 1
fi

echo "=== pre-commit: All checks passed ==="
exit 0
