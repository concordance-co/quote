#!/usr/bin/env python3

"""Demo runner that registers one of several example mods.

Adds four CLI options that mirror scripts/register_mod.py behavior but
are hardcoded to load module `examples.demos.mod` and entrypoints:
  --backtrack       -> backtrack_demo
  --force-output    -> force_output_demo
  --tool-call       -> tool_call_demo
  --adjust-logits   -> adjust_logits_demo

Posts a JSON payload to the local Quote server `/v1/mods` endpoint.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


MODULE = "examples.demos.mods"
DEFAULT_URL = "http://localhost:8000/v1/mods"
MOD_FILE_CANDIDATES = [Path("examples/demos/mods.py")]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Register a demo mod from examples.demos.mod with the local server."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--backtrack", action="store_true", help="Use backtrack_demo entrypoint")
    group.add_argument("--force-output", action="store_true", help="Use force_output_demo entrypoint")
    group.add_argument("--tool-call", action="store_true", help="Use tool_call_demo entrypoint")
    group.add_argument("--adjust-logits", action="store_true", help="Use adjust_logits_demo entrypoint")

    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Mods endpoint URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the curl command without executing it",
    )
    return parser.parse_args()


def resolve_mod_file() -> Path:
    for candidate in MOD_FILE_CANDIDATES:
        if candidate.exists() and candidate.is_file():
            return candidate
    # If nothing matched, default to the first (expected) path for error reporting
    return MOD_FILE_CANDIDATES[0]


def main() -> int:
    args = parse_args()

    if args.backtrack:
        entrypoint = "backtrack_demo"
        name = "backtrack_demo"
    elif args.force_output:
        entrypoint = "force_output_demo"
        name = "force_output_demo"
    elif args.tool_call:
        entrypoint = "tool_call_demo"
        name = "tool_call_demo"
    elif args.adjust_logits:
        entrypoint = "adjust_logits_demo"
        name = "adjust_logits_demo"
    else:
        print("error: no demo option selected", file=sys.stderr)
        return 1

    mod_path = resolve_mod_file()
    if not mod_path.exists():
        print(
            f"error: expected mod file not found: {mod_path}. "
            f"Ensure `examples/demos/mod.py` exists and exports {entrypoint}.",
            file=sys.stderr,
        )
        return 1

    try:
        source_text = mod_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"error: failed reading {mod_path}: {e}", file=sys.stderr)
        return 1

    payload = {
        "name": name,
        "language": "python",
        "module": MODULE,
        "entrypoint": entrypoint,
        "source": source_text,
    }

    payload_json = json.dumps(payload)
    print(payload_json)

    command = [
        "curl",
        "-sS",
        "-X",
        "POST",
        args.url,
        "-H",
        "Content-Type: application/json",
        "-d",
        payload_json,
    ]

    if args.preview:
        escaped = payload_json.replace("'", "\\'")
        print(
            f"curl -sS -X POST {args.url} -H 'Content-Type: application/json' -d '{escaped}'"
        )
        return 0

    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
