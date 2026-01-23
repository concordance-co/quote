#!/bin/bash
# Simple test runner for mod unit tests
# Uses the project's venv to run pytest

set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Path to venv python
VENV_PYTHON="$SCRIPT_DIR/../../.venv/bin/python"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    echo "Please set up the venv first:"
    echo "  cd engine && uv venv"
    exit 1
fi

# Change to test directory
cd "$SCRIPT_DIR"

# Run pytest with all arguments passed through
exec "$VENV_PYTHON" -m pytest "$@"
