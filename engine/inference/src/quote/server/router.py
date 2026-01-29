from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from typing import Any, Optional

import requests

DEFAULT_LOCAL_OPENAI = os.environ.get("LOCAL_OPENAI_BASE", "http://127.0.0.1:8000")
DEFAULT_REMOTE_OPENAI_BASE = os.environ.get("REMOTE_OPENAI_BASE") or os.environ.get(
    "OPENAI_BASE"
)


def _print(obj: Any) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(str(obj))


def _json_or_text(resp: requests.Response) -> Any:
    ct = resp.headers.get("content-type", "")
    try:
        return resp.json() if ct.startswith("application/json") else resp.text
    except Exception:
        return resp.text


def do_health(mode: str, base: Optional[str], exec_info_url: Optional[str]) -> int:
    if mode == "local-openai":
        base_url = base or DEFAULT_LOCAL_OPENAI
        print(f"[health] GET {base_url}/healthz")
        # Prefer healthz, fall back to exec_info
        r = requests.get(f"{base_url}/healthz", timeout=30)
        if not r.ok:
            print(f"[health] GET {base_url}/exec_info")
            r = requests.get(f"{base_url}/exec_info", timeout=30)
        _print(_json_or_text(r))
        return 0 if r.ok else 1
    if mode == "remote-openai":
        base = base or DEFAULT_REMOTE_OPENAI_BASE
        if not base:
            print(
                "--base is required for remote-openai health (or set OPENAI_BASE/REMOTE_OPENAI_BASE)",
                file=sys.stderr,
            )
            return 2
        url = f"{base}/exec_info"
        print(f"[health] GET {url}")
        r = requests.get(url, timeout=30)
        _print(_json_or_text(r))
        return 0 if r.ok else 1
    print(f"Unknown mode: {mode}", file=sys.stderr)
    return 2


def do_publish(mode: str, base: Optional[str], file_path: str, admin_key: Optional[str] = None) -> int:
    b = pathlib.Path(file_path).read_bytes()
    print("local_sha256:", hashlib.sha256(b).hexdigest())
    headers = {"Content-Type": "application/octet-stream"}
    # Add admin key header for protected endpoint
    key = admin_key or os.environ.get("ADMIN_KEY")
    if key:
        headers["X-Admin-Key"] = key
    if mode == "remote-openai":
        base = base or DEFAULT_REMOTE_OPENAI_BASE
        if not base:
            print(
                "--base is required for remote-openai publish (or set OPENAI_BASE/REMOTE_OPENAI_BASE)",
                file=sys.stderr,
            )
            return 2
        r = requests.post(f"{base}/publish_exec", data=b, headers=headers, timeout=60)
        _print(_json_or_text(r))
        return 0 if r.ok else 1
    print(
        "Publish is only supported for remote modes (remote-openai, remote-dev).",
        file=sys.stderr,
    )
    return 2


def do_generate(
    mode: str,
    base: Optional[str],
    bar_url: Optional[str],
    complete_url: Optional[str],
    prompt: Optional[str],
    max_tokens: int,
    model: Optional[str],
    temperature: float,
    top_p: float,
    stream: bool,
) -> int:
    if mode in ("local-openai", "remote-openai"):
        if not prompt:
            print("--prompt is required", file=sys.stderr)
            return 2
        base_url = base or (
            DEFAULT_LOCAL_OPENAI
            if mode == "local-openai"
            else DEFAULT_REMOTE_OPENAI_BASE
        )
        if not base_url:
            print(
                "--base is required for remote-openai generate (or set OPENAI_BASE/REMOTE_OPENAI_BASE)",
                file=sys.stderr,
            )
            return 2
        body = {
            "model": model
            or os.environ.get("MODEL_ID", "modularai/Llama-3.1-8B-Instruct-GGUF"),
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        url = f"{base_url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if not stream:
            r = requests.post(url, headers=headers, json=body, timeout=120)
            _print(_json_or_text(r))
            return 0 if r.ok else 1
        # streaming
        body["stream"] = True
        with requests.post(
            url, headers=headers, json=body, stream=True, timeout=300
        ) as r:
            if not r.ok:
                _print(_json_or_text(r))
                return 1
            try:
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        s = line.decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    if s.startswith("data: "):
                        payload = s[len("data: ") :]
                        print(payload)
            finally:
                pass
        return 0

    print(f"Unknown mode: {mode}", file=sys.stderr)
    return 2


def main() -> None:
    p = argparse.ArgumentParser(
        description="Router for local/remote dev/openai servers"
    )
    p.add_argument(
        "--mode",
        choices=["local-openai", "remote-openai"],
        required=True,
    )
    p.add_argument(
        "--action",
        choices=["health", "exec-info", "publish-exec", "generate", "publish-sdk"],
        default="generate",
    )

    # Common flags
    p.add_argument(
        "--base", help="Base URL for openai modes (or to override local bases)"
    )
    p.add_argument("--model", help="Model name for OpenAI chat")

    # Generation params
    p.add_argument("--prompt")
    p.add_argument("--max_tokens", type=int, default=256)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--top_p", type=float, default=0.9)
    p.add_argument("--stream", action="store_true")

    # Publish file / SDK
    p.add_argument("--file", help="Path to execute_impl.py for remote publish")
    p.add_argument(
        "--sdk-root", help="Path to local SDK root (default sdk/quote_mod_sdk)"
    )
    p.add_argument(
        "--admin-key",
        help="Admin API key for protected endpoints (or set ADMIN_KEY env var)",
    )

    a = p.parse_args()

    print("a.action", a.action)
    if a.action == "health":
        sys.exit(do_health(a.mode, a.base, a.exec_info_url))

    if a.action == "exec-info":
        # Alias to health that always hits exec_info
        if a.mode in ("local-openai",):
            url = f"{a.base or DEFAULT_LOCAL_OPENAI}/exec_info"
            r = requests.get(url, timeout=30)
            _print(_json_or_text(r))
            sys.exit(0 if r.ok else 1)
        if a.mode == "remote-openai":
            if not a.base:
                print("--base required for remote-openai exec-info", file=sys.stderr)
                sys.exit(2)
            r = requests.get(f"{a.base}/exec_info", timeout=30)
            _print(_json_or_text(r))
            sys.exit(0 if r.ok else 1)
    if a.action == "publish-exec":
        if not a.file:
            print("--file is required for publish-exec", file=sys.stderr)
            sys.exit(2)
        sys.exit(do_publish(a.mode, a.base, a.file, a.admin_key))

    if a.action == "publish-sdk":
        # Only supported for OpenAI-compatible servers which expose /sdk
        if a.mode not in ("local-openai", "remote-openai"):
            print(
                "publish-sdk is only supported for local-openai or remote-openai modes",
                file=sys.stderr,
            )
            sys.exit(2)
        base_url = a.base or (
            DEFAULT_LOCAL_OPENAI
            if a.mode == "local-openai"
            else DEFAULT_REMOTE_OPENAI_BASE
        )
        if not base_url:
            print(
                "--base is required for remote-openai publish-sdk (or set OPENAI_BASE/REMOTE_OPENAI_BASE)",
                file=sys.stderr,
            )
            sys.exit(2)
        sdk_root = pathlib.Path(a.sdk_root or "sdk/quote_mod_sdk")
        if not sdk_root.exists() or not sdk_root.is_dir():
            print(f"SDK root not found: {sdk_root}", file=sys.stderr)
            sys.exit(2)
        # Build source mapping of relative .py files under sdk_root
        source: dict[str, str] = {}
        for pth in sdk_root.rglob("*.py"):
            if "__pycache__" in pth.parts:
                continue
            rel = pth.relative_to(sdk_root).as_posix()
            try:
                code = pth.read_text(encoding="utf-8")
            except Exception:
                # Best-effort; skip unreadable files
                continue
            source[rel] = code
        if not source:
            print(f"No Python sources found under {sdk_root}", file=sys.stderr)
            sys.exit(2)
        url = f"{base_url}/sdk"
        headers = {"Content-Type": "application/json"}
        # Add admin key header for protected endpoint
        key = a.admin_key or os.environ.get("ADMIN_KEY")
        if key:
            headers["X-Admin-Key"] = key
        print(f"[publish-sdk] POST {url} (files={len(source)})")
        print("source", source)
        r = requests.post(url, headers=headers, json={"source": source}, timeout=120)
        _print(_json_or_text(r))
        sys.exit(0 if r.ok else 1)

    if a.action == "generate":
        sys.exit(
            do_generate(
                a.mode,
                a.base,
                a.bar_url,
                a.complete_url,
                a.prompt,
                a.max_tokens,
                a.model,
                a.temperature,
                a.top_p,
                a.stream,
            )
        )


if __name__ == "__main__":
    main()
