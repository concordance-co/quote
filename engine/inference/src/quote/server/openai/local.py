from __future__ import annotations

"""
Custom OpenAI-compatible server using MAX EngineQueue + ModelWorker,
with Quote extras (SDK, Mods, hot execute), and a tolerant Chat Completions endpoint.

This server:
- Starts a MAX model worker (separate process) and wires an EngineQueue-backed pipeline
- Uses Quote's TextGenerationPipeline in the worker with hot-swapped execute_impl
- Exposes flexible /v1/chat/completions (accepts loose tools, adds our message augmentations)
- Keeps /sdk, /v1/mods, /exec_info, /healthz endpoints
"""

import argparse
import hashlib
import importlib
import json
import logging
import os
import pathlib
import random
import uuid
import sys

logger = logging.getLogger(__name__)
from contextlib import AsyncExitStack, asynccontextmanager
from types import MethodType
from typing import Any, Callable

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from max.interfaces import (
    GenerationStatus,
    PipelinesFactory,
    PipelineTask,
    PipelineTokenizer,
    SamplingParams,
    TextGenerationOutput,
    TextGenerationRequest,
    TextGenerationRequestFunction,
    TextGenerationRequestTool,
)
from max.pipelines.lib import PIPELINE_REGISTRY, PipelineConfig
from max.serve.config import Settings
from max.serve.pipelines.model_worker import start_model_worker
from max.serve.pipelines.telemetry_worker import start_telemetry_consumer
from max.serve.queue.lora_queue import LoRAQueue
from max.serve.scheduler.queues import SchedulerZmqConfigs
from max.serve.telemetry.metrics import METRICS
from shared.conversation import (
    clear_conversation,
    set_conversation,
    set_schemas,
    read_debug_logs,
    get_mod_trace,
    get_mod_trace_data,
    clear_mod_trace,
    init_mod_trace,
)
from sse_starlette.sse import EventSourceResponse

from quote.mods.sdk_bridge import ModPayloadError, load_mod_from_payload
from quote.pipelines.token_gen_pipeline import TokenGeneratorPipeline
from quote.logs import get_accumulator

# Quote helpers
from ..core import (
    EXEC_PATH,
    augment_messages_with_params,
    format_prompt_from_messages,
    make_maybe_reload_exec,
    write_default_exec_if_missing,
)


USERS_PATH = os.environ.get("USERS_PATH") or "./users/users.json"
MODS_BASE = os.environ.get("MODS_BASE") or "./mods"

def _extract_user_api_key(request: Request, body: dict | None = None) -> str | None:
    """Extract and normalize user API key from request headers or body.

    Checks in order: Authorization header, x-api-key header, x-user-api-key header, body.user_api_key.
    Strips 'Bearer ' prefix if present.

    Args:
        request: The FastAPI request object.
        body: Optional request body dict.

    Returns:
        The extracted API key string, or None if not found.
    """
    api_key = (
        request.headers.get("Authorization")
        or request.headers.get("x-api-key")
        or request.headers.get("x-user-api-key")
    )
    if api_key is None and body is not None:
        api_key = body.get("user_api_key")

    if isinstance(api_key, str):
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:]  # Strip "Bearer " prefix
        return api_key.strip() if api_key.strip() else None
    return None


class QuotePipelineFactory:
    """Picklable factory to build Quote TextGenerationPipeline in the worker.

    Binds a hot-swapped execute() that calls execute_impl each scheduler iteration.
    """

    def __init__(self, pipeline_config: PipelineConfig, *, use_user_mods: bool = False) -> None:
        self.pipeline_config = pipeline_config
        self.use_user_mods = use_user_mods

    def __call__(self) -> Any:
        import hashlib as _hashlib

        from quote.mods.manager import ModManager
        from quote.pipelines.text_gen_pipeline import (
            TextGenerationPipeline as QuoteTGP,
        )
        from quote.mods.manager import ModManager
        import sdk.quote_mod_sdk
        import json as _json
        import pathlib as _pathlib

        from quote.custom_arch import register_all_models

        register_all_models()

        # Build tokenizer + base MAX pipeline, then extract internals
        tokenizer, max_pipeline_factory = PIPELINE_REGISTRY.retrieve_factory(
            self.pipeline_config, task=PipelineTask.TEXT_GENERATION
        )
        max_pipeline = max_pipeline_factory()

        p_model = getattr(max_pipeline, "_pipeline_model")
        adapters = getattr(max_pipeline, "_weight_adapters")

        pipeline = QuoteTGP(
            pipeline_config=self.pipeline_config,
            pipeline_model=p_model,
            eos_token_id=tokenizer.eos,  # type: ignore[arg-type]
            weight_adapters=adapters,
        )
        # Propagate remote per-user mod resolution flag to the pipeline instance
        try:
            setattr(pipeline, "use_user_mods", bool(self.use_user_mods))
        except Exception:
            pass

        # Ensure ModManager is present & wired to tokenizer
        mm = getattr(pipeline, "mod_manager", None)
        if not isinstance(mm, ModManager):
            mm = ModManager([])
            setattr(pipeline, "mod_manager", mm)
            setattr(pipeline, "_sdk_mod_manager", mm)
        try:
            mm.set_tokenizer(tokenizer)
        except Exception:
            pass

        # Hot execute binding (execute_impl)
        exec_state = {
            "exec_path": pathlib.Path(EXEC_PATH),
            "exec_hash": None,
            "exec_mod": None,
        }
        maybe_reload_exec = make_maybe_reload_exec(exec_state)

        # Persistent mod cache on the pipeline to maintain state across execute() calls
        pipeline._mod_cache = {}
        pipeline._mod_payload_hash = {}
        setattr(pipeline, "async_gen", True)

        def _get_persistent_mod(self, name: str) -> Any | None:
            # If remote mode, support per-user resolution when name is "<mod>@<user_key>"
            user_key: str | None = None
            mod_name = name
            if "@" in name:
                try:
                    mod_name, user_key = name.rsplit("@", 1)
                except Exception:
                    mod_name, user_key = name, None

            try:
                from quote.mods.sdk_bridge import load_mod_from_payload as _lmfp
            except Exception:
                return None

            cached = getattr(self, "_mod_cache", {})
            hashes = getattr(self, "_mod_payload_hash", {})

            payload: dict | None = None
            cache_key = mod_name if not user_key else f"{user_key}:{mod_name}"

            # Remote per-user resolution
            if getattr(self, "use_user_mods", False) and user_key:
                per_user_path = _pathlib.Path("/mods") / user_key / f"{mod_name}.json"
                try:
                    if per_user_path.exists():
                        payload = _json.loads(per_user_path.read_text())
                        if not isinstance(payload, dict):
                            payload = None
                except Exception:
                    payload = None

            # Global fallback registry if no per-user payload
            if payload is None:
                registry_path = _pathlib.Path(
                    "sdk/quote_mod_sdk/.mods_registry.json"
                ).resolve()
                if not registry_path.exists():
                    return None
                try:
                    data = _json.loads(registry_path.read_text())
                    payload = None
                    if isinstance(data, dict):
                        # Prefer new structure keyed by user: { user_key: { mod_name: {payload} } }
                        if user_key and isinstance(data.get(user_key), dict):
                            entry = data[user_key].get(mod_name)
                            if isinstance(entry, dict):
                                maybe = entry.get("payload")
                                if isinstance(maybe, dict):
                                    payload = maybe
                        # Fallback to legacy flat structure: { mod_name: {payload} }
                        if payload is None and isinstance(data.get(mod_name), dict):
                            maybe = data[mod_name].get("payload")
                            if isinstance(maybe, dict):
                                payload = maybe
                except Exception:
                    return None
                if not isinstance(payload, dict):
                    return None

            payload_hash = _hashlib.sha256(
                _json.dumps(payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            if cache_key in cached and hashes.get(cache_key) == payload_hash:
                return cached[cache_key]
            try:
                mod_callable = _lmfp(payload)
            except Exception:
                return None
            cached[cache_key] = mod_callable
            hashes[cache_key] = payload_hash
            setattr(self, "_mod_cache", cached)
            setattr(self, "_mod_payload_hash", hashes)
            return mod_callable

        def _hot_execute(self, inputs):  # type: ignore[no-redef]
            # Per-request mod activation based on model_name suffix
            mods_to_add: list[Any] = []
            mod_names: set[str] = set()
            for batch in getattr(inputs, "batches", []) or []:
                if not isinstance(batch, dict):
                    continue
                for _rid, ctx in batch.items():
                    model_name = getattr(ctx, "model_name", "")
                    parts = [seg for seg in str(model_name).split("/") if seg]
                    if len(parts) >= 3:
                        mod_names.add(parts[-1])

            if mod_names:
                for name in mod_names:
                    mod_callable = _get_persistent_mod(self, name)
                    if mod_callable is not None:
                        mods_to_add.append(mod_callable)

            # Temporarily extend mod manager for this execute() call
            mm_local = getattr(self, "mod_manager", None)
            prior_mods = None
            if mm_local is not None and hasattr(mm_local, "mods") and mods_to_add:
                prior_mods = list(getattr(mm_local, "mods", []))
                mm_local.mods = prior_mods + mods_to_add

            mod = maybe_reload_exec()
            try:
                result = mod.execute(self, inputs)
            except Exception:
                import traceback

                traceback.print_exc()
                err_dict = {}
                for k, v in inputs.batches[0].items():
                    err_dict[k] = TextGenerationOutput(
                        request_id=k,
                        tokens=[],
                        log_probabilities=None,
                        final_status=GenerationStatus.CANCELLED,
                    )
                return err_dict
            finally:
                if mods_to_add and mm_local is not None and prior_mods is not None:
                    try:
                        mm_local.mods = prior_mods
                    except Exception:
                        pass
            return result

        pipeline.execute = MethodType(_hot_execute, pipeline)  # type: ignore[assignment]
        return pipeline


def _normalize_tools(obj: Any) -> list[dict[str, Any]] | None:
    out: list[dict[str, Any]] = []
    if isinstance(obj, dict) and isinstance(obj.get("tool_calls"), list):
        candidates = obj["tool_calls"]
    elif isinstance(obj, dict) and isinstance(obj.get("function_call"), dict):
        fc = obj["function_call"]
        candidates = [{"type": "function", "function": fc}]
    elif isinstance(obj, dict) and isinstance(obj.get("tool_call"), dict):
        candidates = [obj["tool_call"]]
    elif isinstance(obj, list):
        candidates = obj
    else:
        return None

    for call in candidates:
        if not isinstance(call, dict):
            continue
        ctype = call.get("type") or "function"
        fn = call.get("function") or {}
        if not isinstance(fn, dict):
            fn = {}
        name = fn.get("name") or call.get("name")
        args = fn.get("arguments") if fn else call.get("arguments")
        arg_str = (
            args
            if isinstance(args, str)
            else json.dumps(args if args is not None else {})
        )
        out.append(
            {
                "id": call.get("id"),
                "type": ctype,
                "function": {"name": name, "arguments": arg_str},
            }
        )
    return out or None


def _convert_tools_to_tg(
    tools: list[dict[str, Any]] | None,
) -> list[TextGenerationRequestTool] | None:
    if not tools:
        return None
    out: list[TextGenerationRequestTool] = []
    for t in tools:
        fn = t.get("function") if isinstance(t.get("function"), dict) else None
        name = fn.get("name") if fn else None
        params = (
            fn.get("parameters")
            if fn and isinstance(fn.get("parameters"), dict)
            else {}
        )
        if isinstance(name, str) and name:
            out.append(
                TextGenerationRequestTool(
                    type="function",
                    function=TextGenerationRequestFunction(
                        name=name, description=None, parameters=params
                    ),
                )
            )
    return out or None


def _parse_schemas(response_format: dict | None, tool_schemas: list | None) -> list[dict]:
    """Extract JSON schemas from response_format and tools.

    Args:
        response_format: The response_format parameter from the request.
        tool_schemas: The tools parameter from the request.

    Returns:
        List of schema dictionaries.
    """
    schemas = []
    if response_format:
        try:
            if response_format.get("json_schema"):
                schemas.append(response_format["json_schema"]["schema"])
            else:
                schemas.append(response_format)
        except Exception as e:
            logger.debug("Error parsing response format: %s", e)

    if tool_schemas:
        try:
            schemas.extend(tool_schemas)
        except Exception as e:
            logger.debug("Error parsing tool schemas: %s", e)

    return schemas


def _parse_max_tokens(raw_max_tokens: Any) -> int | None:
    """Parse max_tokens from various input formats.

    Args:
        raw_max_tokens: The raw max_tokens value from request body.

    Returns:
        Integer token count, or None if not parseable.
    """
    if isinstance(raw_max_tokens, (int, float)):
        return int(raw_max_tokens)
    if isinstance(raw_max_tokens, str):
        try:
            return int(raw_max_tokens)
        except ValueError:
            return None
    return None


def _extract_prompt_texts(messages: list[dict]) -> tuple[str | None, str | None]:
    """Extract system and user prompt texts from messages.

    Args:
        messages: List of message dictionaries.

    Returns:
        Tuple of (system_prompt_text, user_prompt_text).
    """
    system_prompt_text = None
    user_prompt_text = None
    try:
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if role == "system" and system_prompt_text is None:
                if isinstance(content, str):
                    system_prompt_text = content
            if role == "user" and user_prompt_text is None:
                if isinstance(content, str):
                    user_prompt_text = content
    except Exception:
        pass
    return system_prompt_text, user_prompt_text


def _resolve_model_with_mod(
    model: str | None,
    default_model: str,
    registry: dict[str, Any],
    is_remote: bool,
) -> tuple[str, str, str]:
    """Resolve model string, extracting mod suffix if present.

    Args:
        model: The model string from the request.
        default_model: Default model ID to use if model is None.
        registry: The mod registry dictionary.
        is_remote: Whether this is a remote deployment.

    Returns:
        Tuple of (requested_model, model_for_response, original_model_str).
    """
    requested_model = model if isinstance(model, str) else default_model
    model_for_response = requested_model
    original_model_str = requested_model

    try:
        parts = [seg for seg in requested_model.split("/") if seg]
        if is_remote:
            if len(parts) >= 3:
                requested_model = "/".join(parts[:-1])
        else:
            if len(parts) >= 3 and parts[-1] in registry:
                requested_model = "/".join(parts[:-1])
    except Exception:
        pass

    return requested_model, model_for_response, original_model_str


def _format_chat_completion_response(
    req_id: str,
    model: str,
    text: str,
    log_probs: list | None,
    completion_tokens: int,
    include_logprobs: bool,
) -> dict[str, Any]:
    """Format a non-streaming chat completion response.

    Args:
        req_id: The request ID.
        model: The model name for the response.
        text: The generated text content.
        log_probs: Log probability data if requested.
        completion_tokens: Number of completion tokens.
        include_logprobs: Whether to include logprobs in response.

    Returns:
        OpenAI-compatible chat completion response dict.
    """
    ts = int(os.urandom(2)[0])
    return {
        "id": f"chatcmpl-{req_id}",
        "object": "chat.completion",
        "created": ts,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
                "logprobs": {"content": log_probs} if include_logprobs and log_probs else None,
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": completion_tokens,
            "total_tokens": completion_tokens,
        },
        "system_fingerprint": None,
    }


def _format_streaming_chunk(
    req_id: str,
    model: str,
    content: str | None = None,
    removed_n: int | None = None,
    finish_reason: str | None = None,
    created: int | None = None,
) -> dict[str, Any]:
    """Format a streaming chat completion chunk.

    Args:
        req_id: The request ID.
        model: The model name for the response.
        content: Token content (if emitting a token).
        removed_n: Number of removed tokens (if backtracking).
        finish_reason: Finish reason (if final chunk).
        created: Timestamp for the chunk.

    Returns:
        OpenAI-compatible streaming chunk dict.
    """
    delta = {}
    if content is not None:
        delta["content"] = content
    if removed_n is not None:
        delta["removed"] = removed_n

    return {
        "id": f"chatcmpl-{req_id}",
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


@asynccontextmanager
async def lifespan(
    app: FastAPI, tokenizer: PipelineTokenizer[Any, Any, Any], model_id: str, cfg, remote: bool = False
):
    settings = Settings()
    write_default_exec_if_missing(pathlib.Path(EXEC_PATH))

    async with AsyncExitStack() as stack:
        metric_client = await stack.enter_async_context(
            start_telemetry_consumer(settings)
        )
        METRICS.configure(client=metric_client)

        scheduler_cfg = SchedulerZmqConfigs(PipelineTask.TEXT_GENERATION)

        factory: PipelinesFactory = QuotePipelineFactory(
            cfg,
            use_user_mods=bool(remote),
        )

        worker_monitor = await stack.enter_async_context(
            start_model_worker(
                factory,
                cfg,
                settings,
                metric_client,
                scheduler_zmq_configs=scheduler_cfg,
            )
        )

        lora_queue: LoRAQueue | None = None
        pipeline = TokenGeneratorPipeline(
            model_name=model_id,
            tokenizer=tokenizer,
            lora_queue=lora_queue,
            scheduler_zmq_configs=scheduler_cfg,
            worker_monitor=worker_monitor,
        )

        app.state.pipeline = pipeline
        await stack.enter_async_context(pipeline)
        yield


def create_app(model_id: str | None = None, *, remote: bool = False) -> FastAPI:
    # Resolve tokenizer and default model id
    resolved_model = model_id or os.environ.get(
        "MODEL_ID", "modularai/Llama-3.1-8B-Instruct-GGUF"
    )
    resolved_path = os.environ.get("WEIGHT_PATH")
    if resolved_path:
        cfg = PipelineConfig(model_path=resolved_model, max_batch_size=15, max_num_steps=1, weight_path=resolved_path)
    else:
        cfg = PipelineConfig(model_path=resolved_model, max_batch_size=15, max_num_steps=1)

    from quote.custom_arch import register_all_models

    register_all_models()

    tokenizer, _ = PIPELINE_REGISTRY.retrieve_factory(
        cfg, task=PipelineTask.TEXT_GENERATION
    )

    app = FastAPI(lifespan=lambda app: lifespan(app, tokenizer, resolved_model, cfg, remote))

    # Shared state for SDK/mod endpoints
    state: dict[str, Any] = {
        "tokenizer": tokenizer,
        "model_id": resolved_model,
        "exec_path": pathlib.Path(EXEC_PATH),
        "exec_hash": None,
        "exec_mod": None,
    }
    state["maybe_reload_exec"] = make_maybe_reload_exec(state)
    state["remote"] = bool(remote)

    def _ensure_parent(path: str) -> None:
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

    def _load_users() -> set[str]:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return {str(x) for x in data}
            if isinstance(data, dict):
                return set(map(str, data.keys()))
            return set()
        except FileNotFoundError:
            return set()
        except Exception:
            return set()

    def _save_users(users: set[str]) -> None:
        _ensure_parent(USERS_PATH)
        with open(USERS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(users)), f)

    @app.post("/add_user")
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
        user_mod_dir = pathlib.Path(MODS_BASE) / user_api_key
        user_mod_dir.mkdir(parents=True, exist_ok=True)
        return {"ok": True, "user": user_api_key, "existed": already_present}


    # ---- Extra endpoints: SDK / Mods / Health ----
    @app.post("/sdk")
    def update_sdk(body: dict = Body(...)):
        """
        Remotely update the local SDK sources (sdk/quote_mod_sdk).

        Body format:
        {
          "source": {"<relative_path>": "<python code>", ...}
        }

        Relative paths are resolved under sdk/quote_mod_sdk. Path traversal is rejected.
        After writing, SDK modules are invalidated and conversation helpers rebound.
        """
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        source = body.get("source")
        if not isinstance(source, dict) or not source:
            raise HTTPException(
                status_code=400,
                detail="body.source must be a non-empty object {path: code}",
            )

        base = pathlib.Path("sdk/quote_mod_sdk").resolve()
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"failed to create sdk dir: {exc}"
            ) from exc

        written: list[str] = []
        file_hashes: dict[str, str] = {}

        def _is_safe_path(root: pathlib.Path, p: pathlib.Path) -> bool:
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

            pattern = os.path.join(base, f"**/*.pyc")
            files_to_delete = glob.glob(pattern, recursive=True)
            for file_to_delete in files_to_delete:
                os.remove(file_to_delete)
        except Exception as e:
            pass

        # Invalidate and reload sdk.quote_mod_sdk modules so future imports see new code
        try:
            import importlib
            import sys

            def _invalidate(prefix: str) -> None:
                for name in list(sys.modules.keys()):
                    if name == prefix or name.startswith(prefix + "."):
                        try:
                            del sys.modules[name]
                        except Exception:
                            pass

            _invalidate("sdk.quote_mod_sdk")
            _invalidate("quote_mod_sdk")  # alias used in conversation module
            importlib.invalidate_caches()
            # Rebind conversation helpers imported at module import time
            try:
                conv_mod = importlib.import_module("sdk.quote_mod_sdk.conversation")
                globals()["set_conversation"] = getattr(
                    conv_mod, "set_conversation", set_conversation
                )
                globals()["clear_conversation"] = getattr(
                    conv_mod, "clear_conversation", clear_conversation
                )
                globals()["set_schemas"] = getattr(
                    conv_mod, "set_schemas", clear_conversation
                )
            except Exception as e:
                # Non-fatal; continue with updated files written
                logger.debug("Failed to rebind conversation helpers: %s", e)
                pass

            manager = importlib.import_module("quote.mods.manager")
            importlib.reload(manager)
            globals()["ModManager"] = getattr(manager, "ModManager")
            state["maybe_reload_exec"]()
        except Exception as e:
            logger.debug("Error while invalidating/reloading modules: %s", e)
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

    @app.post("/v1/mods")
    def register_mod(body: dict = Body(...)):
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        name = body.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(
                status_code=400, detail="mod payload must include non-empty 'name'"
            )
        try:
            mod_callable = load_mod_from_payload(body)
        except ModPayloadError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        registry: dict[str, dict[str, Any]] = state.setdefault("mod_registry", {})
        replaced = name in registry
        registry[name] = {"callable": mod_callable, "payload": body}
        # Persist payloads for worker-side activation
        try:
            reg_path = pathlib.Path("sdk/quote_mod_sdk/.mods_registry.json").resolve()
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            payload_map = {
                n: {"payload": info.get("payload")} for n, info in registry.items()
            }
            reg_path.write_text(json.dumps(payload_map))
        except Exception:
            pass
        return {
            "name": name,
            "replaced": replaced,
            "description": body.get("description"),
        }

    @app.get("/exec_info")
    def exec_info():
        p = state["exec_path"]
        b = p.read_bytes()
        return {
            "path": str(p),
            "sha256": hashlib.sha256(b).hexdigest(),
            "stored_hash": state.get("exec_hash"),
            "ino": p.stat().st_ino,
            "mtime_ns": p.stat().st_mtime_ns,
            "size": len(b),
        }

    @app.get("/healthz")
    def healthz():
        if "tokenizer" not in state:
            return JSONResponse(
                status_code=503, content={"ok": False, "error": "initializing model"}
            )
        return {"ok": True}

    @app.get("/v1/models")
    async def list_models(request: Request):
        pipeline: TokenGeneratorPipeline = request.app.state.pipeline
        data = [
            {
                "id": pipeline.model_name,
                "object": "model",
                "created": None,
                "owned_by": "",
            }
        ]
        return {"object": "list", "data": data}

    # ---- Chat Completions (tolerant, with Quote augmentations) ----
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        try:
            body = await request.json()
        except Exception as e:
            logger.error("Failed to parse request JSON: %s", e)
            raise e
        tokenizer = state["tokenizer"]
        pipeline: TokenGeneratorPipeline = request.app.state.pipeline

        model = body.get("model")
        messages = body.get("messages")
        temperature = body.get("temperature", 0.7)
        top_p = body.get("top_p", 0.9)
        raw_max_tokens = body.get("max_tokens", body.get("max_completion_tokens"))
        stream = bool(body.get("stream", False))
        response_format = body.get("response_format")
        tools_in = body.get("tools")
        tool_choice = body.get("tool_choice")
        logprobs = body.get("logprobs")
        n_log_probs = body.get("top_logprobs")
        tool_schemas = body.get("tools")
        mod_debug_logs = body.get("mod_debug_logs")
        collection = body.get("collection")  # Collection ID (int) or name (str) to add request to

        schemas = _parse_schemas(response_format, tool_schemas)

        if not isinstance(messages, list) or not messages:
            raise HTTPException(
                status_code=400, detail="messages must be a non-empty list"
            )

        registry: dict[str, dict[str, Any]] = state.setdefault("mod_registry", {})
        requested_model, model_for_response, original_model_str = _resolve_model_with_mod(
            model, state["model_id"], registry, state.get("remote", False)
        )

        # Normalize tools and augment messages
        normalized_tools = _normalize_tools(tools_in)
        augmented_messages = augment_messages_with_params(
            messages, response_format, normalized_tools, tool_choice
        )
        formatted = format_prompt_from_messages(tokenizer, augmented_messages)
        # Capture raw prompts for ingest
        system_prompt_text, user_prompt_text = _extract_prompt_texts(messages)

        # step_count
        step_count = _parse_max_tokens(raw_max_tokens)

        # Streaming tools not supported (parity with our prior behavior)
        if (
            normalized_tools
            and stream
            and (tool_choice is None or tool_choice != "none")
        ):
            raise HTTPException(
                status_code=400, detail="Tools are not supported in streaming mode."
            )

        sampling_params = SamplingParams(
            max_new_tokens=step_count,
            top_k=10,
            top_p=float(top_p),
            min_p=0,
            temperature=float(temperature),
            ignore_eos=False,
            stop=None,
            stop_token_ids=None,
            detokenize=True,
            seed=body.get("seed", random.randint(0, 2**63 - 1)),
        )

        req_id = getattr(request.state, "request_id", None)
        if not req_id:
            req_id = str(uuid.uuid4())

        user_api_key = _extract_user_api_key(request, body)
        # In remote mode with a mod suffix, require a user_api_key and encode it in the model string
        if state.get("remote"):
            try:
                orig_parts = [seg for seg in original_model_str.split("/") if seg]
            except Exception:
                orig_parts = []
            if len(orig_parts) >= 3:
                # Prefer header for user key when remote
                user_api_key = _extract_user_api_key(request, body)
                if not user_api_key:
                    raise HTTPException(status_code=400, detail="user_api_key (X-User-Api-Key) is required when using mods in remote mode")
                try:
                    orig_parts[-1] = f"{orig_parts[-1]}@{user_api_key}"
                    original_model_str = "/".join(orig_parts)
                except Exception:
                    pass
        tg_tools = _convert_tools_to_tg(normalized_tools)
        tg_request = TextGenerationRequest(
            request_id=req_id,
            model_name=str(
                original_model_str
            ),  # includes mod suffix for worker detection
            prompt=formatted,
            sampling_params=sampling_params,
            tools=tg_tools,
            logprobs=n_log_probs if logprobs else 0,
        )
        # Record request-level metadata for ingest accumulator (persisted across 1-step executes)
        try:
            acc = get_accumulator(req_id)
            # Prefer Authorization/X-User-Api-Key headers if present
            user_api_key = _extract_user_api_key(request, body)
            # Tokenize prompts best-effort
            system_tokens = None
            user_tokens = None
            try:
                if system_prompt_text:
                    system_tokens = await tokenizer.encode(system_prompt_text, add_special_tokens=False)
                if user_prompt_text:
                    user_tokens = await tokenizer.encode(user_prompt_text, add_special_tokens=False)
            except Exception:
                system_tokens = None
                user_tokens = None
            acc.mark_request_start(
                model=model_for_response,
                user_api_key=user_api_key,
                max_tokens=step_count,
                temperature=float(temperature),
                mod_text=original_model_str,
            )
            # Set collection to add request to after ingestion
            if collection is not None:
                acc.set_collection(collection, added_by=user_api_key)
            try:
                if system_prompt_text is not None:
                    acc.request["system_prompt"] = system_prompt_text
                if user_prompt_text is not None:
                    acc.request["user_prompt"] = user_prompt_text
                if system_tokens is not None:
                    acc.request["system_prompt_token_ids"] = [int(t) for t in system_tokens]
                if user_tokens is not None:
                    acc.request["user_prompt_token_ids"] = [int(t) for t in user_tokens]
            except Exception:
                pass
            # Store active mod as a simple string for ingest
            try:
                parts_for_mod = [seg for seg in str(original_model_str).split("/") if seg]
                if len(parts_for_mod) >= 3:
                    active_mod = parts_for_mod[-1]
                    acc.request["active_mod_name"] = active_mod
            except Exception:
                pass
        except Exception:
            pass
        set_conversation(req_id, messages)
        set_schemas(req_id, schemas)
        # Initialize mod trace if debug logging is enabled
        if mod_debug_logs:
            init_mod_trace(req_id)
        if stream:
            # Create the iterator once
            token_iter = pipeline.next_token(tg_request)

            # Pull the first token *before* starting SSE so we can still return 400
            try:
                first_token = await token_iter.__anext__()
            except StopAsyncIteration:
                raise HTTPException(status_code=500, detail="No tokens produced")

            if first_token.error:
                raise HTTPException(status_code=400, detail=first_token.error)

            async def gen():
                id = f"chatcmpl-{req_id}"
                ts = None
                prompt_len = 0
                completion_tokens = 0
                total_tokens = 0
                outputs = []

                async def handle_token(token):
                    nonlocal ts, prompt_len, completion_tokens, total_tokens

                    outputs.append(token)

                    if ts is None:
                        prompt_len = token.prompt_token_count
                        # whatever you want here; this matches your original intent
                        ts = int.from_bytes(os.urandom(2), "big")

                    if token.decoded_token is not None:
                        payload = {
                            "id": id,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": model_for_response,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": token.decoded_token},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        completion_tokens += 1
                        total_tokens += 1
                        # sse-starlette is fine with plain strings
                        yield json.dumps(payload)

                    elif token.removed_n is not None:
                        payload = {
                            "id": id,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": model_for_response,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"removed": token.removed_n},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        completion_tokens = max(0, completion_tokens - token.removed_n)
                        yield json.dumps(payload)

                # 1) Handle the first (already-fetched) token
                async for chunk in handle_token(first_token):
                    yield chunk

                # 2) Handle the rest from the same iterator
                async for token in token_iter:
                    if token.error:
                        # At this point we can't change HTTP status anymore;
                        # send an SSE error payload and end the stream.
                        err_payload = {
                            "id": id,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": model_for_response,
                            "choices": [],
                            "error": {"message": token.error},
                        }
                        yield json.dumps(err_payload)
                        return

                    async for chunk in handle_token(token):
                        yield chunk

                    if token.status and token.status.is_done:
                        break

                # 3) Final chunk / usage, same logic as you had
                filtered = []
                for i, o in enumerate(outputs):
                    if o.decoded_token:
                        filtered.append(o)
                    elif o.removed_n:
                        del filtered[-1 * min(o.removed_n, i):]

                text = ""
                for o in filtered:
                    text += o.decoded_token

                final_chunk = {
                    "id": id,
                    "object": "chat.completion.chunk",
                    "created": ts,
                    "model": model_for_response,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": len(await tokenizer.encode(formatted, add_special_tokens=False)),
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                }
                logger.debug("Streaming complete: %d completion tokens", completion_tokens)
                yield json.dumps(final_chunk)

            return EventSourceResponse(gen(), ping=100000)

        # Non-streaming: collect tokens
        outputs = []
        async for tok in pipeline.next_token(tg_request):
            if tok.error:
                logger.error("Token generation error: %s", tok.error)
                raise HTTPException(status_code=400, detail=tok.error)
            else:
                outputs.append(tok)
        filtered = []
        for i, o in enumerate(outputs):
            if o.decoded_token:
                filtered.append(o)
            elif o.removed_n:
                del filtered[-1*min(o.removed_n, i):]
        text = ""
        log_probs = []
        for o in filtered:
            text += o.decoded_token
            if o.token_log_probabilities:
                top = []
                for prob in o.top_log_probabilities:
                    for k, v in prob.items():
                        top.append({"token": k, "logprob": v })
                log_probs.append({
                    "token": o.decoded_token,
                    "logprob": o.token_log_probabilities[0],
                    "top_logprobs": top
                })
        clear_conversation(req_id)
        ts = int(os.urandom(2)[0])
        try:
            if isinstance(text, str):
                start = f"<tool_call_{req_id}"
                end = f"</tool_call_{req_id}"
                if text.startswith(f"<tool_call_{req_id}"):
                    text = text.split('>', 1)[1]
                    text = text.rsplit(f"</tool_call_{req_id}", 1)[0]
                    payload = json.loads(text)
                    return _tool_calls_response(
                        f"chatcmpl-{req_id}", ts, model_for_response, [payload]
                    )
        except Exception:
            # Fall back to text response if JSON parse or normalization fails
            pass
        res = {
            "id": f"chatcmpl-{req_id}",
            "object": "chat.completion",
            "created": ts,
            "model": model_for_response,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                    "logprobs": {"content": log_probs} if tg_request.logprobs > 0 else None,
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": len(outputs),
                "total_tokens": len(outputs),
            },
            "system_fingerprint": None,
        }
        # Populate ingest accumulator with final outputs and stats
        try:
            acc = get_accumulator(req_id)
            # Merge snapshot from worker (events/mods/actions)
            snapshot_path = None
            try:
                snapshot_path = pathlib.Path("inference/src/quote/logs/tmp") / f"{req_id}.json"
                if snapshot_path.exists():
                    snap = json.loads(snapshot_path.read_text())
                    if isinstance(snap, dict):
                        snap_req = snap.get("request", {}) or {}
                        for k, v in snap_req.items():
                            acc.request.setdefault(k, v)
                        acc.events = snap.get("events", acc.events)
                        acc.mod_calls = snap.get("mod_calls", acc.mod_calls)
                        acc.mod_logs = snap.get("mod_logs", acc.mod_logs)
                        acc.actions = snap.get("actions", acc.actions)
            except Exception:
                pass
            final_token_ids = [
                int(o.token) for o in filtered if o.token is not None and o.token >= 0
            ]
            acc.set_final_output(final_token_ids, text)
            prompt_len = 0
            try:
                if system_prompt_text:
                    prompt_len += len(await tokenizer.encode(system_prompt_text, add_special_tokens=False))
                if user_prompt_text:
                    prompt_len += len(await tokenizer.encode(user_prompt_text, add_special_tokens=False))
            except Exception:
                pass
            stats_payload = {
                "prompt_tokens": int(prompt_len),
                "generated_tokens": int(len(final_token_ids)),
                "total_tokens": int(prompt_len + len(final_token_ids)),
            }
            acc.set_inference_stats(stats_payload)
            acc.mark_request_end()
            acc.finalize()
            try:
                if snapshot_path:
                    snapshot_path.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception:
            pass
        if mod_debug_logs:
            try:
                # Parse mod_debug_logs format
                trace_type = None
                ansi_color = False

                if isinstance(mod_debug_logs, dict):
                    # Object format: {"type": "trace"|"json", "ansi_color": true}
                    trace_type = mod_debug_logs.get("type", "trace")
                    ansi_color = mod_debug_logs.get("ansi_color", False)
                elif isinstance(mod_debug_logs, str):
                    # String format: "json"
                    trace_type = mod_debug_logs.lower()
                else:
                    # Boolean true -> default to formatted trace
                    trace_type = "trace"

                if trace_type == "json":
                    # Return raw JSON data structure
                    trace_data = get_mod_trace_data(req_id)
                    res["mod_debug_logs"] = trace_data if trace_data else []
                    logger.debug("Returning JSON trace with %d entries for %s", len(trace_data) if trace_data else 0, req_id)
                else:
                    # Return formatted trace string (trace type or default)
                    trace_str = get_mod_trace(req_id, ansi_color=ansi_color)
                    res["mod_debug_logs"] = trace_str if trace_str else "No trace data"
                    logger.debug("Returning formatted trace for %s: %d chars", req_id, len(trace_str) if trace_str else 0)
            except Exception as e:
                logger.error("Failed to get trace for %s: %s", req_id, e, exc_info=True)
                res["mod_debug_logs"] = {"error": str(e)}
            finally:
                clear_mod_trace(req_id)
        return res

    return app


def _tool_calls_response(
    completion_id: str, ts: int, model_id: str, tool_calls: list[dict[str, Any]]
) -> dict[str, Any]:
    # Per request: include tool calls both in message.tool_calls and as a plain JSON string in message.content
    # content_str = json.dumps(tool_calls, ensure_ascii=False)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": ts,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls",
                "logprobs": None,
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "system_fingerprint": None,
        "mod_registry": {},
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--model-id", default=os.environ.get("MODEL_ID"))
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(args.model_id), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
