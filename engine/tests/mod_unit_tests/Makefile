# Makefile for Mod Unit Tests
# Provides convenient shortcuts for running pytest tests

.PHONY: help test install clean coverage parallel prefilled forward-pass added sampled integration verbose

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Mod Unit Tests - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make test              # Run all tests"
	@echo "  make install test      # Install dependencies and run tests"
	@echo "  make prefilled         # Run only Prefilled tests"
	@echo "  make coverage          # Run with coverage report"
	@echo "  make parallel          # Run tests in parallel"

install: ## Install pytest and dependencies
	@echo "Installing pytest and dependencies..."
	@python3 -m pip install pytest pytest-cov pytest-xdist
	@echo "✓ Dependencies installed"

test: ## Run all tests
	@echo "Running all mod unit tests..."
	@python3 run_tests.py

verbose: ## Run tests with verbose output
	@echo "Running tests with verbose output..."
	@python3 run_tests.py -vv

prefilled: ## Run Prefilled event tests
	@echo "Running Prefilled event tests..."
	@python3 run_tests.py --prefilled

forward-pass: ## Run ForwardPass event tests
	@echo "Running ForwardPass event tests..."
	@python3 run_tests.py --forward-pass

added: ## Run Added event tests
	@echo "Running Added event tests..."
	@python3 run_tests.py --added

sampled: ## Run Sampled event tests
	@echo "Running Sampled event tests..."
	@python3 run_tests.py --sampled

integration: ## Run integration tests
	@echo "Running integration tests..."
	@python3 run_tests.py --integration

coverage: ## Run tests with coverage report
	@echo "Running tests with coverage..."
	@python3 run_tests.py --cov
	@echo ""
	@echo "Coverage report: htmlcov/index.html"

parallel: ## Run tests in parallel
	@echo "Running tests in parallel..."
	@python3 run_tests.py --parallel

watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "Running tests in watch mode..."
	@pip show pytest-watch > /dev/null 2>&1 || pip install pytest-watch
	@ptw -- -v

debug: ## Run tests with debugger on failure
	@echo "Running tests with debugger..."
	@python3 run_tests.py --pdb

quick: ## Run tests with minimal output
	@pytest -q --tb=line

clean: ## Clean test artifacts
	@echo "Cleaning test artifacts..."
	@rm -rf .pytest_cache __pycache__ htmlcov .coverage
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Clean complete"

# Convenience aliases
all: test
t: test
v: verbose
c: coverage
p: parallel
i: install
