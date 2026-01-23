#!/usr/bin/env python3

"""Register a mod with the local Quote server via curl.

Supports:
 - Single-file payload: {language, module?, entrypoint, source: "..."}
 - Multi-file bundle: {language, module, entrypoint, source: {"path.py": "code", ...}}
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serialize a mod file and POST it to the local /v1/mods endpoint."
    )
    parser.add_argument(
        "file",
        type=Path,
        nargs="?",
        help="Path to the Python source file containing the mod (omit when using --files/--dir)",
    )
    parser.add_argument(
        "--name",
        required=False,
        help="Name to register the mod under (defaults to the file stem)",
    )
    parser.add_argument(
        "--entrypoint",
        required=True,
        help="Entrypoint function name exported by the file",
    )
    parser.add_argument(
        "--module",
        default=None,
        help=(
            "Import path for the entry module (e.g., examples.tau2.mod3).\n"
            "Required when using --files/--dir. Optional for single-file (defaults to client_mod)."
        ),
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8001/v1/mods",
        help="Mods endpoint URL (default: http://localhost:8001/v1/mods)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        help="One or more Python files to include as a multi-file bundle",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        help="Directory to include all .py files from (recursively)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the curl command without executing it",
    )
    return parser.parse_args()


def _gather_files(dir_path: Path | None, files: list[Path] | None) -> list[Path]:
    collected: list[Path] = []
    if dir_path:
        if not dir_path.exists() or not dir_path.is_dir():
            print(f"error: --dir does not exist or is not a directory: {dir_path}", file=sys.stderr)
            sys.exit(1)
        for p in dir_path.rglob("*.py"):
            if p.is_file():
                collected.append(p)
    if files:
        for f in files:
            if not f.exists() or not f.is_file():
                print(f"error: file not found: {f}", file=sys.stderr)
                sys.exit(1)
            collected.append(f)
    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in collected:
        s = str(p.resolve())
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


def _build_source_map(paths: list[Path], module: str | None) -> dict[str, str]:
    # Determine a base root such that the entry module path exists under it.
    # This ensures bundle keys reflect the intended import path (e.g., examples/tau2/mod3.py).
    resolved = [p.resolve() for p in paths]
    base_root = None
    if module:
        # Try to locate the entry file among provided files
        mod_parts = module.split(".")
        candidate_rel_py = Path(*mod_parts).with_suffix(".py")
        candidate_rel_init = Path(*mod_parts) / "__init__.py"
        for p in resolved:
            parts = p.parts
            matched_len = None
            if len(parts) >= len(candidate_rel_py.parts) and tuple(parts[-len(candidate_rel_py.parts):]) == tuple(candidate_rel_py.parts):
                matched_len = len(candidate_rel_py.parts)
            elif len(parts) >= len(candidate_rel_init.parts) and tuple(parts[-len(candidate_rel_init.parts):]) == tuple(candidate_rel_init.parts):
                matched_len = len(candidate_rel_init.parts)
            if matched_len is not None:
                base_root = Path(*parts[: len(parts) - matched_len])
                break
    if base_root is None:
        # Fallback to lowest common ancestor of all files
        ancestors = [str(p) for p in resolved]
        base_root = Path(os.path.commonpath(ancestors)) if ancestors else Path.cwd()
    src: dict[str, str] = {}
    for p in resolved:
        rel = p.relative_to(base_root)
        key = rel.as_posix()
        src[key] = p.read_text(encoding="utf-8")
    # If only a single file and module given, ensure the entry module key exists
    if module and len(paths) == 1:
        mod_key = module.replace(".", "/") + ("/__init__.py" if paths[0].name == "__init__.py" else ".py")
        if mod_key not in src:
            src[mod_key] = paths[0].read_text(encoding="utf-8")
    return src


def main() -> int:
    args = parse_args()
    if args.dir or args.files:
        if not args.module:
            print("error: --module is required when using --files/--dir", file=sys.stderr)
            return 1
        multi_files = _gather_files(args.dir, args.files)
        if not multi_files:
            print("error: no Python files found to include", file=sys.stderr)
            return 1
        src_map = _build_source_map(multi_files, args.module)
        payload = {
            "name": args.name or (args.module.split(".")[-1] if args.module else "bundle"),
            "language": "python",
            "module": args.module,
            "entrypoint": args.entrypoint,
            "source": src_map,
        }
    else:
        if args.file is None:
            print("error: provide a FILE or use --files/--dir", file=sys.stderr)
            return 1
        if not args.file.exists():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 1
        source_text = args.file.read_text(encoding="utf-8")
        payload = {
            "name": args.name or args.file.stem,
            "language": "python",
            "module": args.module or "client_mod",
            "entrypoint": args.entrypoint,
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
