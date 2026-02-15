import hashlib
import os

import modal
from dotenv import load_dotenv
import sys

load_dotenv()

# Keep image/env/volumes identical to prior implementation to avoid behavioral changes
cuda_version = "12.8.0"
flavor = "cudnn-devel"
operating_sys = "ubuntu24.04"
tag = f"{cuda_version}-{flavor}-{operating_sys}"

def get_admin_key():
    if os.environ.get("ADMIN_KEY"):
        return os.environ.get("ADMIN_KEY")
    else:
        print("NO ADMIN_KEY DEFINED")
        sys.exit(1)

local_backend_path = os.environ.get(
    "LOCAL_BACKEND_PATH",
    "../backend",
)
image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.13")
    .entrypoint([])
    # .apt_install("curl", "build-essential", "pkg-config", "libssl-dev", "libpq-dev")
    # .run_commands(
    #     "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y",
    # )
    # .env({"PATH": "/root/.cargo/bin:/usr/local/bin:$PATH"})
    .uv_pip_install(
        "modular==25.6", extra_index_url="https://modular.gateway.scarf.sh/simple/"
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "BACKEND_URL": "http://localhost:6767",
            "HF_HOME": "/models/hf",
            "HF_HUB_CACHE": "/models/hf/hub",
            # Debug-only UI is opt-in; staging/prod shouldn't pay for it.
            "CONCORDANCE_ENABLE_FULLPASS_DEBUG": "0",
            "MODEL_ID": os.environ.get("MODEL_ID")
            or "modularai/Llama-3.1-8B-Instruct-GGUF",
            "ADMIN_KEY": get_admin_key(),
            "HF_TOKEN": os.environ.get("HF_TOKEN", ""),
            "QUOTE_LOG_INGEST_URL": os.environ.get("QUOTE_LOG_INGEST_URL", "")
        }
    )
    .add_local_python_source(
        # Ship the entire `quote` package to avoid missing-module deploy crashes
        # when new subpackages are imported (e.g. quote.storage).
        "quote",
        "sdk.quote_mod_sdk",
        "shared",
    )
)

os.environ.setdefault("APP_NAME", "max-openai-compatible")
app = modal.App(os.environ.get("APP_NAME"))
MINUTES = 60


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


N_GPU = _env_int("N_GPU", 1)
GPU_TYPE = os.environ.get("GPU_TYPE", "A100-80GB")
MODAL_CPU = _env_int("MODAL_CPU", 4)
MODAL_MEMORY_MB = _env_int("MODAL_MEMORY_MB", 15000)
MODAL_MIN_CONTAINERS = 0
MODAL_MAX_CONTAINERS = _env_int("MODAL_MAX_CONTAINERS", 1)
MODAL_SCALEDOWN_MINUTES = _env_int("MODAL_SCALEDOWN_MINUTES", 120)
MODAL_TIMEOUT_MINUTES = _env_int("MODAL_TIMEOUT_MINUTES", 20)
models_vol = modal.Volume.from_name("models", create_if_missing=True)  # HF
mef_vol = modal.Volume.from_name("max-mef-cache", create_if_missing=True)  # MEF
logic_vol = modal.Volume.from_name(
    "exec-logic", create_if_missing=True
)  # hot-swapped execute()

# Basic gating + user/mod storage
users_vol = modal.Volume.from_name("users", create_if_missing=True)
mods_vol = modal.Volume.from_name("mods", create_if_missing=True)

MEF_PATH = "/root/.local/share/modular/.max_cache/mof/mef"
EXEC_PATH = "/logic/execute_impl.py"


# Optional helpers to push new execute() via volume (not HTTP)
@app.function(image=image, volumes={"/logic": logic_vol})
def publish_execute(code: str):
    with open(EXEC_PATH, "wb") as f:
        f.write(code.encode("utf-8"))


@app.function(image=image, volumes={"/logic": logic_vol})
def publish_execute_bytes(code: bytes):
    os.makedirs("/logic", exist_ok=True)
    with open(EXEC_PATH, "wb") as f:
        f.write(code)


import hashlib


def get_cpuinfo_sha256():
    """
    Calculates and returns the SHA-256 checksum of /proc/cpuinfo.
    """
    file_path = "/proc/cpuinfo"
    try:
        # Open the file for reading and get its content
        with open(file_path, "rb") as f:
            content = f.read()

        # Create a new SHA-256 hash object
        sha256_hash = hashlib.sha256()

        # Update the hash object with the content of the file
        sha256_hash.update(content)

        # Return the hexadecimal representation of the hash
        return sha256_hash.hexdigest()

    except FileNotFoundError:
        return f"Error: The file {file_path} was not found."
    except Exception as e:
        return f"An error occurred: {e}"


# Get the checksum and print it


print(MODAL_SCALEDOWN_MINUTES * MINUTES)
# ASGI app: thin wrapper that returns the same FastAPI app as local, plus a /publish_exec endpoint
@app.function(
    image=image,
    gpu=f"{GPU_TYPE}:{N_GPU}",
    cpu=MODAL_CPU,
    memory=MODAL_MEMORY_MB,
    volumes={
        "/models": models_vol,
        MEF_PATH: mef_vol,
        "/logic": logic_vol,
        "/users": users_vol,
        "/mods": mods_vol,
    },
    min_containers=MODAL_MIN_CONTAINERS,
    max_containers=MODAL_MAX_CONTAINERS,
    scaledown_window=max(2, min(3600, MODAL_SCALEDOWN_MINUTES * MINUTES)),
    timeout=MODAL_TIMEOUT_MINUTES * MINUTES,
    enable_memory_snapshot=True,
    experimental_options={"enable_gpu_snapshot": True},
)
@modal.asgi_app()
@modal.concurrent(max_inputs=15)
def openai_http_app():
    os.environ.setdefault("EXEC_PATH", EXEC_PATH)
    checksum = get_cpuinfo_sha256()
    print("check sum", checksum)
    os.environ.setdefault("MODULAR_MAX_CACHE_DIR", MEF_PATH + "/" + checksum)
    import pathlib as _p

    from fastapi import Body, FastAPI, HTTPException, Request
    import json as _json
    import pathlib as _pathlib

    from quote.mods.sdk_bridge import ModPayloadError, load_mod_from_payload

    from quote.api.openai.local import create_app

    api: FastAPI = create_app(os.environ.get("MODEL_ID"), remote=True)

    @api.post("/publish_exec")
    def _publish_exec(
        request: Request,
        content: bytes = Body(..., media_type="application/octet-stream"),
    ):
        # Admin key gating
        admin_key = request.headers.get("x-admin-key")
        expected = os.environ.get("ADMIN_KEY")
        if not expected:
            raise HTTPException(status_code=403, detail="admin gating not configured")
        if not admin_key or admin_key != expected:
            raise HTTPException(status_code=403, detail="invalid or missing admin key")

        p = _p.Path(EXEC_PATH)
        p.write_bytes(content)
        h = hashlib.sha256(content).hexdigest()
        # No need to reset cached module; loader compares file hash and reloads on change
        return {"ok": True, "path": str(EXEC_PATH), "sha256": h, "size": len(content)}

    # ---- Basic user gating and per-user mod registry persisted to volumes ----

    MODS_BASE = "/mods"
    USERS_PATH = os.environ.get("USERS_PATH") or "/users/users.json"

    def _ensure_parent(path: str) -> None:
        p = _pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

    def _load_users() -> set[str]:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                print("had users path")
                data = _json.load(f)
            if isinstance(data, list):
                return {str(x) for x in data}
            if isinstance(data, dict):
                return set(map(str, data.keys()))
            print("not list or dict")
            return set()
        except FileNotFoundError:
            return set()
        except Exception:
            return set()

    def _save_users(users: set[str]) -> None:
        _ensure_parent(USERS_PATH)
        print("writing to users", USERS_PATH)
        with open(USERS_PATH, "w", encoding="utf-8") as f:
            print("writing to users", sorted(list(users)))
            _json.dump(sorted(list(users)), f)

    # Remove existing routes from local.py that we want to override
    try:
        for r in list(api.router.routes):
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", set())
            if path == "/v1/mods" and "POST" in methods:
                api.router.routes.remove(r)
            elif path == "/add_user" and "POST" in methods:
                api.router.routes.remove(r)
            elif path == "/sdk" and "POST" in methods:
                api.router.routes.remove(r)
    except Exception:
        pass

    @api.post("/add_user")
    def add_user(body: dict = Body(...)):
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        user_api_key = body.get("user_api_key")
        admin_key = body.get("admin_key")
        if not isinstance(user_api_key, str) or not user_api_key.strip():
            raise HTTPException(status_code=400, detail="user_api_key is required")
        expected = os.environ.get("ADMIN_KEY")
        if not isinstance(admin_key, str) or not admin_key:
            raise HTTPException(status_code=400, detail="admin_key is required")
        if not expected:
            # Fail closed if ADMIN_KEY not configured
            raise HTTPException(status_code=403, detail="admin gating not configured")
        if admin_key != expected:
            raise HTTPException(status_code=403, detail="invalid admin_key")

        users = _load_users()
        already_present = user_api_key in users
        users.add(user_api_key)
        _save_users(users)

        # Ensure per-user mods directory exists
        user_mod_dir = _pathlib.Path(MODS_BASE) / user_api_key
        user_mod_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "user": user_api_key, "existed": already_present}

    @api.post("/v1/mods")
    def register_mod(request: Request, body: dict = Body(...)):
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")

        # Basic gating: require a valid user_api_key
        user_api_key = request.headers.get("x-user-api-key") or body.get("user_api_key")
        if not isinstance(user_api_key, str) or not user_api_key.strip():
            raise HTTPException(status_code=400, detail="user_api_key is required")
        if user_api_key not in _load_users():
            print("users", _load_users(), user_api_key)
            raise HTTPException(status_code=403, detail="unauthorized user_api_key")

        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code=400, detail="mod payload must include non-empty 'name'")

        # Validate payload using the SDK bridge
        try:
            load_mod_from_payload(body)
        except ModPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Persist the raw payload under /mods/<user_api_key>/<name>.json
        user_dir = _pathlib.Path(MODS_BASE) / user_api_key
        user_dir.mkdir(parents=True, exist_ok=True)
        mod_path = user_dir / f"{name}.json"
        try:
            mod_path.write_text(_json.dumps(body))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"failed to persist mod: {exc}") from exc

        # Update registry keyed by user: sdk/quote_mod_sdk/.mods_registry.json
        try:
            reg_path = _pathlib.Path("sdk/quote_mod_sdk/.mods_registry.json").resolve()
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            current: dict[str, dict] = {}
            try:
                current = _json.loads(reg_path.read_text())
                if not isinstance(current, dict):
                    current = {}
            except Exception:
                current = {}

            # New structure: { user_api_key: { mod_name: { payload: ... } } }
            user_map = current.get(user_api_key)
            if not isinstance(user_map, dict):
                user_map = {}
            replaced = name in user_map
            user_map[name] = {"payload": body}
            current[user_api_key] = user_map
            reg_path.write_text(_json.dumps(current))
        except Exception:
            replaced = False

        return {"name": name, "replaced": replaced, "description": body.get("description")}

    @api.post("/sdk")
    def update_sdk(request: Request, body: dict = Body(...)):
        """
        Remotely update the local SDK sources (sdk/quote_mod_sdk).
        Protected by admin API key.

        Body format:
        {
          "source": {"<relative_path>": "<python code>", ...}
        }

        Relative paths are resolved under sdk/quote_mod_sdk. Path traversal is rejected.
        After writing, SDK modules are invalidated and conversation helpers rebound.
        """
        # Admin key gating
        admin_key = request.headers.get("x-admin-key")
        expected = os.environ.get("ADMIN_KEY")
        if not expected:
            raise HTTPException(status_code=403, detail="admin gating not configured")
        if not admin_key or admin_key != expected:
            raise HTTPException(status_code=403, detail="invalid or missing admin key")

        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        source = body.get("source")
        if not isinstance(source, dict) or not source:
            raise HTTPException(
                status_code=400,
                detail="body.source must be a non-empty object {path: code}",
            )

        base = _pathlib.Path("sdk/quote_mod_sdk").resolve()
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"failed to create sdk dir: {exc}"
            ) from exc

        written: list[str] = []
        file_hashes: dict[str, str] = {}

        def _is_safe_path(root: _pathlib.Path, p: _pathlib.Path) -> bool:
            try:
                p_resolved = p.resolve()
                return (
                    str(p_resolved).startswith(str(root) + os.sep) or p_resolved == root
                )
            except Exception:
                return False

        for rel_path, code in source.items():
            if not isinstance(rel_path, str) or not isinstance(code, str):
                raise HTTPException(
                    status_code=400, detail="source mapping must be {str: str}"
                )
            # Normalize separators and strip leading ./
            norm = rel_path.replace("\\", "/").lstrip("./")
            dest = base / norm
            if not _is_safe_path(base, dest):
                raise HTTPException(
                    status_code=400,
                    detail=f"refusing to write outside sdk/quote_mod_sdk: {rel_path}",
                )
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = code.encode("utf-8")
                dest.write_bytes(data)
                written.append(norm)
                file_hashes[norm] = hashlib.sha256(data).hexdigest()
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"failed to write {rel_path}: {exc}"
                ) from exc

        try:
            import glob

            pattern = os.path.join(base, "**/*.pyc")
            files_to_delete = glob.glob(pattern, recursive=True)
            for file_to_delete in files_to_delete:
                os.remove(file_to_delete)
        except Exception:
            pass

        # Invalidate and reload sdk.quote_mod_sdk modules so future imports see new code
        try:
            import importlib
            import sys as _sys

            def _invalidate(prefix: str) -> None:
                for name in list(_sys.modules.keys()):
                    if name == prefix or name.startswith(prefix + "."):
                        try:
                            del _sys.modules[name]
                        except Exception:
                            pass

            _invalidate("sdk.quote_mod_sdk")
            _invalidate("quote_mod_sdk")  # alias used in conversation module
            importlib.invalidate_caches()
        except Exception:
            # Non-fatal: file writes succeeded; module invalidation best-effort
            pass

        bundle_hash = hashlib.sha256(
            "".join(sorted(file_hashes.values())).encode("utf-8")
        ).hexdigest()
        return {
            "updated": written,
            "file_hashes": file_hashes,
            "bundle_hash": bundle_hash,
            "base": str(base),
        }

    return api


# ---------------------------------------------------------------------------
# HF Inference endpoint (Phase 1 — activations playground)
# ---------------------------------------------------------------------------
# Lightweight image: only transformers + torch, no MAX/modular.
# Runs as a separate container with its own A10G GPU.

hf_inference_image = (
    modal.Image.from_registry(f"nvidia/cuda:{tag}", add_python="3.13")
    .entrypoint([])
    .uv_pip_install(
        "transformers",
        "torch",
        "fastapi",
        "accelerate",
        "hf_transfer",
        "pydantic",
    )
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_HOME": "/models/hf",
            "HF_HUB_CACHE": "/models/hf/hub",
            "HF_TOKEN": os.environ.get("HF_TOKEN", ""),
        }
    )
    .add_local_python_source("quote.api.hf_inference")
)


@app.function(
    image=hf_inference_image,
    gpu="A10G",
    volumes={"/models": models_vol},
    min_containers=0,
    max_containers=1,
    scaledown_window=30 * MINUTES,
    timeout=10 * MINUTES,
)
@modal.asgi_app()
@modal.concurrent(max_inputs=5)
def hf_inference_app():
    from quote.api.hf_inference import create_hf_inference_app

    return create_hf_inference_app()
