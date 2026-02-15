from __future__ import annotations

import hashlib
import pathlib
import importlib.util
import os
import sys
import time
from typing import Any, AsyncGenerator, Callable, cast
import json

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from max.pipelines.lib import (
    PIPELINE_REGISTRY,
    PipelineConfig,
    SpeechTokenGenerationPipeline,
    PipelineModel,
    TextTokenizer,
)
from max.serve.pipelines.llm import AudioGeneratorPipeline
from max.interfaces import (
    PipelineTask,
    TextGenerationInputs,
    TextGenerationRequestMessage,
)

from quote.pipelines.text_gen_pipeline import TextGenerationPipeline
from quote.mods.manager import ModManager
from shared.types import ModAction, ModEvent
from shared.conversation import clear_conversation

# Path used by local servers for hot-swapped execute() contents.
# Default to the packaged implementation so installed wheels work without repo files.
_DEFAULT_EXEC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "hot" / "execute_impl.py"
)
EXEC_PATH = pathlib.Path(os.environ.get("EXEC_PATH", str(_DEFAULT_EXEC_PATH))).resolve()


def write_default_exec_if_missing(exec_path: pathlib.Path) -> None:
    print("Writing default exec path")
    exec_path.parent.mkdir(parents=True, exist_ok=True)
    if exec_path.exists():
        return
    exec_path.write_text(
        "import numpy as np\n"
        "from max.driver import Tensor\n"
        "from max.dtype import DType\n"
        "def execute(pipeline, inputs):\n"
        "    # default: delegate to pipeline’s built-in execute\n"
        "    return pipeline.execute(inputs)\n"
    )


def make_maybe_reload_exec(state: dict[str, Any]) -> Callable[[], Any]:
    def _maybe_reload_execute():
        code = state["exec_path"].read_bytes()
        h = hashlib.sha256(code).hexdigest()
        if h == state.get("exec_hash") and state.get("exec_mod") is not None:
            return state["exec_mod"]
        spec = importlib.util.spec_from_file_location(
            "execute_impl", str(state["exec_path"])
        )
        if spec is None:
            raise RuntimeError("Failed to create spec for execute_impl.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["execute_impl"] = mod
        assert spec.loader
        spec.loader.exec_module(mod)
        if not hasattr(mod, "execute"):
            raise RuntimeError(
                "execute_impl.py must define execute(pipeline, inputs) -> outputs"
            )
        state["exec_mod"], state["exec_hash"] = mod, h
        return mod

    return _maybe_reload_execute


def format_prompt_from_messages(
    tokenizer: TextTokenizer, messages: list[dict[str, Any]]
) -> str:
    if not isinstance(messages, list) or not messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list")
    conv: list[TextGenerationRequestMessage] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if not isinstance(content, str):
            tool_call = m.get("tool_calls")
            if not isinstance(tool_call, list):
                raise HTTPException(
                    status_code=400, detail="Only string message.content is supported"
                )
            content = json.dumps(tool_call)
        conv.append(
            TextGenerationRequestMessage(role=role if role else "user", content=content)
        )
    return tokenizer.apply_chat_template(conv, None, None)


def augment_messages_with_params(
    messages: list[dict[str, Any]],
    response_format: dict | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any | None,
) -> list[dict[str, Any]]:
    sys_instructions: list[str] = []

    # response_format shims
    if isinstance(response_format, dict):
        rtype = response_format.get("type")
        if rtype == "json_object":
            sys_instructions.append(
                "Respond with a valid JSON object only. Do not include any non-JSON text."
            )
        elif rtype == "json_schema":
            schema_obj = {}
            js = response_format.get("json_schema")
            if isinstance(js, dict):
                schema_obj = js.get("schema") or js.get("schema_") or {}
            if schema_obj:
                sys_instructions.append(
                    "Respond only with JSON that strictly matches this JSON Schema. "
                    "Do not include any text outside the JSON. Schema: "
                    + json.dumps(schema_obj)
                )
            else:
                sys_instructions.append(
                    "Respond with a valid JSON object only. Do not include any non-JSON text."
                )

    # tools shims (non-streaming only upstream)
    if tools:
        tool_summaries = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            ttype = t.get("type")
            if ttype == "function" and isinstance(t.get("function"), dict):
                fn = t["function"]
                tool_summaries.append(
                    {
                        "type": "function",
                        "name": fn.get("name"),
                        "description": fn.get("description"),
                        "parameters": fn.get("parameters") or {},
                    }
                )
            else:
                tool_summaries.append(
                    {
                        "type": ttype or "custom",
                        "name": t.get("name") or t.get("custom", {}).get("name"),
                    }
                )

        choice_mode = tool_choice
        choice_desc = None
        if isinstance(tool_choice, dict):
            ttype = tool_choice.get("type")
            if ttype == "function" and isinstance(tool_choice.get("function"), dict):
                fname = tool_choice["function"].get("name")
                choice_desc = f"Call the function '{fname}' using the format below."
            elif ttype == "custom" and isinstance(tool_choice.get("custom"), dict):
                cname = tool_choice["custom"].get("name")
                choice_desc = f"Call the custom tool '{cname}' using the format below."
            elif ttype == "allowed_tools":
                choice_mode = tool_choice.get("mode") or "auto"

        mode = choice_mode if isinstance(choice_mode, str) else None
        if mode != "none":
            sys_instructions.append(
                "You can call tools. Available tools are described as JSON schemas: "
                + json.dumps(tool_summaries)
            )
            if mode == "required":
                sys_instructions.append("You must call one or more tools.")
            elif mode in (None, "auto"):
                sys_instructions.append(
                    "Decide whether to call a tool based on the request."
                )
            if choice_desc:
                sys_instructions.append(choice_desc)
            sys_instructions.append(
                "If you call tools, respond ONLY with JSON of this shape and nothing else: "
                '{"tool_calls":[{"type":"function","function":{"name":"<tool_name>","arguments":{...}}}]}'
            )

    if not sys_instructions:
        return messages

    sys_msg = {"role": "system", "content": "\n".join(sys_instructions)}
    return [sys_msg] + messages


def init_pipeline(
    model_id_env: str | None,
) -> tuple[TextTokenizer, TextGenerationPipeline, str]:
    # Avoid Hugging Face tokenizers fork/thread warning noise in server contexts
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    model_id = (
        model_id_env
        or os.environ.get("MODEL_ID")
        or "modularai/Llama-3.1-8B-Instruct-GGUF"
    )
    mbs = (
        int(os.environ.get("MAX_BATCH_SIZE"))
        or 10
    )
    cfg = PipelineConfig(model_path=model_id, max_batch_size=mbs)
    print("mbs", cfg.max_batch_size)
    tokenizer, pinstance = PIPELINE_REGISTRY.retrieve_factory(
        cfg, task=PipelineTask.TEXT_GENERATION
    )
    pipeline_instance = pinstance()
    if isinstance(
        pipeline_instance, (AudioGeneratorPipeline, SpeechTokenGenerationPipeline)
    ):
        raise RuntimeError(f"Unexpected pipeline type: {type(pipeline_instance)}")
    if not hasattr(pipeline_instance, "_weight_adapters") or not hasattr(
        pipeline_instance, "_pipeline_model"
    ):
        raise RuntimeError("Pipeline instance missing MAX internals")
    adapters = pipeline_instance._weight_adapters
    p_model = pipeline_instance._pipeline_model
    if not isinstance(p_model, PipelineModel):
        raise RuntimeError(f"Pipeline model check failed: {type(p_model)}")
    p_custom = TextGenerationPipeline(
        pipeline_config=cfg,
        pipeline_model=p_model,
        eos_token_id=tokenizer.eos if isinstance(tokenizer, TextTokenizer) else 0,
        weight_adapters=adapters,
    )
    mod_manager = getattr(p_custom, "mod_manager", None)
    if not isinstance(mod_manager, ModManager):
        mod_manager = ModManager([])
    try:
        mod_manager.set_tokenizer(tokenizer)
    except Exception:
        pass
    setattr(p_custom, "mod_manager", mod_manager)
    setattr(p_custom, "_sdk_mod_manager", mod_manager)
    assert isinstance(tokenizer, TextTokenizer), "Incorrect Tokenizer Type"
    return tokenizer, p_custom, model_id


async def sse_chat_gen(
    get_exec_mod: Callable[[], Any],
    tokenizer: TextTokenizer,
    p_custom: Any,
    model_id: str,
    ctx: Any,
    req_id: str,
    max_tokens: int,
    *,
    mod_callable: Callable[[ModEvent, Any | None], ModAction] | None = None,
) -> AsyncGenerator[bytes, None]:
    created_ts = int(time.time())
    emitted = ""
    steps = 0
    mod_manager = getattr(p_custom, "mod_manager", None)
    prior_mods: list[Any] | None = None
    if mod_callable is not None and isinstance(mod_manager, ModManager):
        prior_mods = list(mod_manager.mods)
        mod_manager.mods = prior_mods + [mod_callable]
    try:
        first = {
            "id": f"chatcmpl-{os.urandom(6).hex()}",
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_id,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}
            ],
        }
        yield (f"data: {json.dumps(first, ensure_ascii=False)}\n\n").encode("utf-8")

        while steps < int(max_tokens):
            inputs = TextGenerationInputs(batches=[{ctx.request_id: ctx}], num_steps=1)
            exec_mod = get_exec_mod()
            outputs = exec_mod.execute(p_custom, inputs)
            text = await tokenizer.decode(cast(Any, outputs[req_id].tokens))
            delta = text[len(emitted) :]
            if delta:
                chunk = {
                    "id": first["id"],
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": model_id,
                    "choices": [
                        {"index": 0, "delta": {"content": delta}, "finish_reason": None}
                    ],
                }
                yield (f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n").encode(
                    "utf-8"
                )
                emitted = text
            steps += 1
            if getattr(ctx, "is_done", False):
                break

        final_chunk = {
            "id": first["id"],
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield (f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n").encode(
            "utf-8"
        )
        yield b"data: [DONE]\n\n"
    finally:
        if prior_mods is not None and isinstance(mod_manager, ModManager):
            mod_manager.mods = prior_mods
            try:
                mod_manager.forced_queues.clear()
                mod_manager.forced_reason_queues.clear()
            except Exception:
                pass
        try:
            p_custom.release(ctx.request_id)
        except Exception:
            pass
        try:
            clear_conversation(req_id)
        except Exception:
            pass


def openai_style_error(
    status_code: int, message: str, code: str | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "param": None,
            "code": code,
        }
    }


def make_streaming_response(gen: AsyncGenerator[bytes, None]) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream")
