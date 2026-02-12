import argparse, json, requests, sys, hashlib, pathlib

p = argparse.ArgumentParser()
p.add_argument("--url", required=True, help="Endpoint URL")
# Support new 'complete' endpoint; keep 'bar' as a deprecated alias
p.add_argument(
    "--endpoint",
    choices=["complete", "bar", "exec_info", "publish_exec"],
    default="complete",
)
p.add_argument("-p", "--prompt")
p.add_argument("-m", "--max_new_tokens", type=int, default=128)
p.add_argument("--json-body", action="store_true")
p.add_argument("--file", help="Path to execute_impl.py for publish_exec")
p.add_argument("--timeout", type=float, default=60)
a = p.parse_args()

if a.endpoint in ("complete", "bar"):
    if not a.prompt:
        p.error("--prompt/-p is required for endpoint=complete")
    payload = {"user_prompt": a.prompt, "max_new_tokens": a.max_new_tokens}
    r = requests.post(
        a.url,
        json=payload if a.json_body else None,
        params=None if a.json_body else payload,
        timeout=a.timeout,
    )

elif a.endpoint == "exec_info":
    r = requests.get(a.url, timeout=a.timeout)
    if r.status_code in (404, 405):
        r = requests.post(a.url, timeout=a.timeout)

else:  # publish_exec
    if not a.file:
        p.error("--file is required for endpoint=publish_exec")
    b = pathlib.Path(a.file).read_bytes()
    # optional: print local hash so you can compare server response
    print("local_sha256:", hashlib.sha256(b).hexdigest())
    r = requests.post(
        a.url,
        data=b,
        headers={"Content-Type": "application/octet-stream"},
        timeout=a.timeout,
    )

ct = r.headers.get("content-type", "")
try:
    out = r.json() if ct.startswith("application/json") else r.text
except Exception:
    out = r.text
print(out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=2))
sys.exit(0 if r.ok else 1)
