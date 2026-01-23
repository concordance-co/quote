#!/bin/bash
# Run mod unit tests with pytest
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh -v           # Verbose output
#   ./run_tests.sh -k prefilled # Run only prefilled tests
#   ./run_tests.sh --help       # Show all options

set -e

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the test directory
cd "$SCRIPT_DIR"

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Mod Unit Tests - Pytest Runner${NC}"
echo -e "${BLUE}================================================${NC}\n"

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${YELLOW}Warning: pytest not found. Attempting to install...${NC}"
    pip install pytest pytest-cov pytest-xdist
fi

# Parse command line arguments
if [ "$#" -eq 0 ]; then
    echo -e "${GREEN}Running all mod unit tests...${NC}\n"
    pytest -v --tb=short
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (no args)           Run all tests"
    echo "  -v, --verbose       Verbose output"
    echo "  -vv                 Very verbose output"
    echo "  -k PATTERN          Run tests matching PATTERN"
    echo "  --prefilled         Run only Prefilled tests"
    echo "  --forward-pass      Run only ForwardPass tests"
    echo "  --added             Run only Added tests"
    echo "  --sampled           Run only Sampled tests"
    echo "  --integration       Run only integration tests"
    echo "  --cov               Run with coverage report"
    echo "  --parallel          Run tests in parallel"
    echo "  --pdb               Drop into debugger on failure"
    echo "  --help, -h          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                        # Run all tests"
    echo "  $0 -v                     # Verbose output"
    echo "  $0 --prefilled            # Only Prefilled tests"
    echo "  $0 -k force_tokens        # All force_tokens tests"
    echo "  $0 --cov                  # With coverage"
    echo "  $0 --parallel             # Run in parallel"
    exit 0
elif [ "$1" = "--prefilled" ]; then
    echo -e "${GREEN}Running Prefilled event tests...${NC}\n"
    pytest -v -k "prefilled" --tb=short
elif [ "$1" = "--forward-pass" ]; then
    echo -e "${GREEN}Running ForwardPass event tests...${NC}\n"
    pytest -v -k "forward_pass" --tb=short
elif [ "$1" = "--added" ]; then
    echo -e "${GREEN}Running Added event tests...${NC}\n"
    pytest -v -k "added" --tb=short
elif [ "$1" = "--sampled" ]; then
    echo -e "${GREEN}Running Sampled event tests...${NC}\n"
    pytest -v -k "sampled" --tb=short
elif [ "$1" = "--integration" ]; then
    echo -e "${GREEN}Running integration tests...${NC}\n"
    pytest -v -k "integration" --tb=short
elif [ "$1" = "--cov" ]; then
    echo -e "${GREEN}Running tests with coverage...${NC}\n"
    if ! command -v pytest-cov &> /dev/null; then
        echo -e "${YELLOW}Installing pytest-cov...${NC}"
        pip install pytest-cov
    fi
    pytest -v --cov=. --cov-report=html --cov-report=term --tb=short
    echo -e "\n${GREEN}Coverage report generated in htmlcov/index.html${NC}"
elif [ "$1" = "--parallel" ]; then
    echo -e "${GREEN}Running tests in parallel...${NC}\n"
    if ! command -v pytest-xdist &> /dev/null; then
        echo -e "${YELLOW}Installing pytest-xdist...${NC}"
        pip install pytest-xdist
    fi
    pytest -v -n auto --tb=short
elif [ "$1" = "--pdb" ]; then
    echo -e "${GREEN}Running tests with debugger...${NC}\n"
    pytest -v --pdb --tb=short
else
    # Pass all arguments directly to pytest
    echo -e "${GREEN}Running tests with custom options: $@${NC}\n"
    pytest "$@"
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}   All tests passed! ✓${NC}"
    echo -e "${GREEN}================================================${NC}"
else
    echo -e "${YELLOW}================================================${NC}"
    echo -e "${YELLOW}   Some tests failed (exit code: $EXIT_CODE)${NC}"
    echo -e "${YELLOW}================================================${NC}"
fi

exit $EXIT_CODE
