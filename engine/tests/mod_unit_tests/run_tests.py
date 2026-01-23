#!/usr/bin/env python3
"""Python-based test runner for mod unit tests.

This runner:
1. Checks for required dependencies
2. Optionally installs missing dependencies
3. Runs pytest tests
4. Provides helpful output and error messages

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --install    # Install dependencies and run tests
    python run_tests.py --help       # Show help
"""

import sys
import subprocess
import argparse
from pathlib import Path


def check_pytest():
    """Check if pytest is available."""
    import subprocess
    # Check if pytest is available in the venv
    venv_python = get_venv_python()
    try:
        result = subprocess.run(
            [venv_python, "-c", "import pytest"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def get_venv_python():
    """Get path to venv python."""
    # Relative to this script: ../../.venv/bin/python
    script_dir = Path(__file__).parent
    venv_python = script_dir / ".." / ".." / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    # Fallback to system python
    return sys.executable
</text>

<old_text line=29>
def install_pytest():
    """Install pytest and related packages."""
    print("Installing pytest and dependencies...")
    packages = ["pytest>=8.3.0", "pytest-cov", "pytest-xdist"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        print("✓ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("✗ Failed to install dependencies")
        return False


def install_pytest():
    """Install pytest and related packages."""
    print("Installing pytest and dependencies...")
    packages = ["pytest>=8.3.0", "pytest-cov", "pytest-xdist"]
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        print("✓ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("✗ Failed to install dependencies")
        return False


def run_pytest(args):
    """Run pytest with the given arguments using venv python."""
    venv_python = get_venv_python()
    try:
        # Run pytest as a module with the venv python
        result = subprocess.run(
            [venv_python, "-m", "pytest"] + args,
            cwd=Path(__file__).parent
        )
        return result.returncode
    except FileNotFoundError:
        print(f"Error: Python not found at {venv_python}")
        print("Make sure the venv is set up: cd engine && uv venv")
        return 1
    except Exception as e:
        print(f"Error running pytest: {e}")
        return 1
</text>

<old_text line=61>
    python run_tests.py                    # Run all tests
    python run_tests.py --install          # Install deps and run tests
    python run_tests.py -v                 # Verbose output
    python run_tests.py -k prefilled       # Run only prefilled tests
    python run_tests.py --prefilled        # Run only prefilled tests
    python run_tests.py --cov              # Run with coverage
    python run_tests.py --parallel         # Run in parallel
    python run_tests.py --pdb              # Debug on failure


def main():
    parser = argparse.ArgumentParser(
        description="Run mod unit tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_tests.py                    # Run all tests
    python run_tests.py --install          # Install deps and run tests
    python run_tests.py -v                 # Verbose output
    python run_tests.py -k prefilled       # Run only prefilled tests
    python run_tests.py --prefilled        # Run only prefilled tests
    python run_tests.py --cov              # Run with coverage
    python run_tests.py --parallel         # Run in parallel
    python run_tests.py --pdb              # Debug on failure
        """
    )
    
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install pytest and dependencies before running"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times)"
    )
    parser.add_argument(
        "-k",
        metavar="EXPRESSION",
        help="Run tests matching the given expression"
    )
    parser.add_argument(
        "--prefilled",
        action="store_true",
        help="Run only Prefilled event tests"
    )
    parser.add_argument(
        "--forward-pass",
        action="store_true",
        help="Run only ForwardPass event tests"
    )
    parser.add_argument(
        "--added",
        action="store_true",
        help="Run only Added event tests"
    )
    parser.add_argument(
        "--sampled",
        action="store_true",
        help="Run only Sampled event tests"
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run only integration tests"
    )
    parser.add_argument(
        "--cov",
        action="store_true",
        help="Run with coverage report"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tests in parallel"
    )
    parser.add_argument(
        "--pdb",
        action="store_true",
        help="Drop into debugger on failure"
    )
    parser.add_argument(
        "--tb",
        choices=["auto", "long", "short", "line", "native", "no"],
        default="short",
        help="Traceback print mode"
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Additional arguments to pass to pytest"
    )
    
    args = parser.parse_args()
    
    # Print header
    print("=" * 60)
    print("  Mod Unit Tests - Pytest Runner")
    print("=" * 60)
    print()
    
    # Check and optionally install pytest
    if not check_pytest():
        print("⚠ pytest not found")
        if args.install:
            if not install_pytest():
                print("\nError: Could not install pytest")
                print("Please install manually: pip install pytest pytest-cov pytest-xdist")
                return 1
            print()
        else:
            print("\nPlease install pytest:")
            print("  pip install pytest pytest-cov pytest-xdist")
            print("\nOr run with --install flag:")
            print("  python run_tests.py --install")
            return 1
    
    # Build pytest arguments
    pytest_args = []
    
    # Add verbosity
    if args.verbose > 0:
        pytest_args.append("-" + "v" * args.verbose)
    else:
        pytest_args.append("-v")
    
    # Add traceback mode
    pytest_args.append(f"--tb={args.tb}")
    
    # Add color
    pytest_args.append("--color=yes")
    
    # Handle event type filters
    if args.prefilled:
        pytest_args.extend(["-k", "prefilled"])
        print("Running Prefilled event tests...\n")
    elif args.forward_pass:
        pytest_args.extend(["-k", "forward_pass"])
        print("Running ForwardPass event tests...\n")
    elif args.added:
        pytest_args.extend(["-k", "added"])
        print("Running Added event tests...\n")
    elif args.sampled:
        pytest_args.extend(["-k", "sampled"])
        print("Running Sampled event tests...\n")
    elif args.integration:
        pytest_args.extend(["-k", "integration"])
        print("Running integration tests...\n")
    elif args.k:
        pytest_args.extend(["-k", args.k])
        print(f"Running tests matching: {args.k}\n")
    else:
        print("Running all mod unit tests...\n")
    
    # Add coverage
    if args.cov:
        try:
            import pytest_cov
        except ImportError:
            print("Installing pytest-cov...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest-cov"])
        pytest_args.extend(["--cov=.", "--cov-report=html", "--cov-report=term"])
    
    # Add parallel execution
    if args.parallel:
        try:
            import xdist
        except ImportError:
            print("Installing pytest-xdist...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pytest-xdist"])
        pytest_args.extend(["-n", "auto"])
    
    # Add debugger
    if args.pdb:
        pytest_args.append("--pdb")
    
    # Add any additional pytest args
    if args.pytest_args:
        pytest_args.extend(args.pytest_args)
    
    # Change to test directory
    test_dir = Path(__file__).parent
    import os
    os.chdir(test_dir)
    
    # Run tests
    exit_code = run_pytest(pytest_args)
    
    # Print footer
    print()
    if exit_code == 0:
        print("=" * 60)
        print("  All tests passed! ✓")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"  Some tests failed (exit code: {exit_code})")
        print("=" * 60)
    
    if args.cov and exit_code == 0:
        print("\nCoverage report generated in htmlcov/index.html")
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())