#!/usr/bin/env python3
"""Runner for mod unit tests.

This script always prefers the project virtualenv at:
  engine/.venv/bin/python

It executes pytest from this directory so local pytest.ini is respected.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _engine_root(script_dir: Path) -> Path:
    return script_dir.parent.parent


def _venv_python(script_dir: Path) -> Path:
    return _engine_root(script_dir) / ".venv" / "bin" / "python"


def _resolve_python(script_dir: Path) -> str:
    venv_py = _venv_python(script_dir)
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _has_pytest(py: str) -> bool:
    try:
        proc = subprocess.run(
            [py, "-c", "import pytest"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=8,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _install_deps(script_dir: Path) -> int:
    engine_root = _engine_root(script_dir)
    inference_dir = engine_root / "inference"
    if not shutil.which("uv"):
        print("Error: uv is not installed; cannot auto-install test deps.")
        return 1
    cmd = ["uv", "add", "--dev", "pytest", "pytest-cov", "pytest-xdist"]
    proc = subprocess.run(cmd, cwd=str(inference_dir), check=False)
    return int(proc.returncode)


def _build_pytest_args(args: argparse.Namespace) -> list[str]:
    out: list[str] = []

    verbosity = args.verbose if args.verbose > 0 else 1
    out.append("-" + ("v" * verbosity))
    out.append(f"--tb={args.tb}")
    out.append("--color=yes")

    if args.prefilled:
        out.extend(["-k", "prefilled"])
    elif args.forward_pass:
        out.extend(["-k", "forward_pass"])
    elif args.added:
        out.extend(["-k", "added"])
    elif args.sampled:
        out.extend(["-k", "sampled"])
    elif args.integration:
        out.extend(["-k", "integration"])
    elif args.k:
        out.extend(["-k", args.k])

    if args.cov:
        out.extend(["--cov=.", "--cov-report=html", "--cov-report=term"])
    if args.parallel:
        out.extend(["-n", "auto"])
    if args.pdb:
        out.append("--pdb")

    out.extend(args.pytest_args)
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run mod unit tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py
  python run_tests.py --prefilled
  python run_tests.py --forward-pass
  python run_tests.py -k force_tokens
  python run_tests.py --cov
  python run_tests.py --parallel
        """.strip(),
    )
    parser.add_argument("--install", action="store_true", help="Install pytest deps with uv before running")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (repeat for more)")
    parser.add_argument("-k", metavar="EXPR", help="Filter tests by keyword expression")
    parser.add_argument("--prefilled", action="store_true", help="Run only Prefilled event tests")
    parser.add_argument("--forward-pass", dest="forward_pass", action="store_true", help="Run only ForwardPass event tests")
    parser.add_argument("--added", action="store_true", help="Run only Added event tests")
    parser.add_argument("--sampled", action="store_true", help="Run only Sampled event tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--cov", action="store_true", help="Run with coverage")
    parser.add_argument("--parallel", action="store_true", help="Run with pytest-xdist")
    parser.add_argument("--pdb", action="store_true", help="Drop into pdb on failure")
    parser.add_argument(
        "--tb",
        choices=["auto", "long", "short", "line", "native", "no"],
        default="short",
        help="Traceback style",
    )
    parser.add_argument("pytest_args", nargs="*", help="Additional args forwarded to pytest")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    script_dir = Path(__file__).resolve().parent
    py = _resolve_python(script_dir)

    print("=" * 60)
    print("  Mod Unit Tests - Runner")
    print("=" * 60)
    print(f"python: {py}")
    print(f"cwd: {script_dir}")
    print()

    if args.install:
        rc = _install_deps(script_dir)
        if rc != 0:
            return rc

    if not _has_pytest(py):
        print("Error: pytest is not available in the selected Python environment.")
        print("Try one of:")
        print("  1) python run_tests.py --install")
        print("  2) cd engine/inference && uv add --dev pytest pytest-cov pytest-xdist")
        return 1

    pytest_args = _build_pytest_args(args)
    cmd = [py, "-m", "pytest", *pytest_args]
    proc = subprocess.run(cmd, cwd=str(script_dir), check=False)
    rc = int(proc.returncode)

    print()
    if rc == 0:
        print("=" * 60)
        print("  All tests passed")
        print("=" * 60)
    else:
        print("=" * 60)
        print(f"  Tests failed (exit code: {rc})")
        print("=" * 60)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

