from __future__ import annotations

import os
import pytest
from typing import Any


def _add_mod_temporarily(pipeline: Any, mod_fn: Any):
    mm = getattr(pipeline, "mod_manager", None)
    if mm is None:
        from quote.mods.manager import ModManager  # type: ignore

        mm = ModManager([])
        setattr(pipeline, "mod_manager", mm)
        setattr(pipeline, "_sdk_mod_manager", mm)
    prior_mods = list(getattr(mm, "mods", []))
    mm.register(mod_fn)
    return mm, prior_mods


def _basic_messages():
    return [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Say hi."},
    ]


@pytest.mark.integration
def test_force_tokens(real_model_env) -> None:
    mi = real_model_env.mi
    pipeline = real_model_env.pipeline
    tokenizer = real_model_env.pipeline.tokenizer
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl

    force_text = "Hi"

    def mod(event: Any, tok: Any):
        from shared.types import Prefilled, ForceTokens, Noop

        if isinstance(event, Prefilled) and tok is not None:
            return ForceTokens(tok.encode(force_text, add_special_tokens=False))
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=4, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        forced_ids = tokenizer.encode(force_text, add_special_tokens=False)
        steps = max(2, len(forced_ids))
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=steps)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]
        assert isinstance(out.tokens, list)
        assert out.tokens[: len(forced_ids)] == list(forced_ids)
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass


@pytest.mark.integration
def test_force_output(real_model_env) -> None:
    mi = real_model_env.mi
    tokenizer = real_model_env.pipeline.tokenizer
    pipeline = real_model_env.pipeline
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl

    forced_text = "DONE"

    def mod(event: Any, tok: Any):
        from shared.types import Prefilled, ForceOutput, Noop

        if isinstance(event, Prefilled) and tok is not None:
            return ForceOutput(tok.encode(forced_text, add_special_tokens=False))
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=8, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=4)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]
        forced_ids = tokenizer.encode(forced_text, add_special_tokens=False)
        assert out.tokens == list(forced_ids)
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass


@pytest.mark.integration
def test_tool_calls(real_model_env) -> None:
    mi = real_model_env.mi
    tokenizer = real_model_env.pipeline.tokenizer
    pipeline = real_model_env.pipeline
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl

    payload = {"tool_calls": [{"type": "function", "function": {"name": "echo", "arguments": {"text": "hi"}}}]}

    def mod(event: Any, _tok: Any):
        from shared.types import Prefilled, ToolCalls, Noop

        if isinstance(event, Prefilled):
            return ToolCalls(payload)
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=8, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=4)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]

        # Expected encoding pattern matches execute_impl._encode_tool_calls
        expected_text = f"<tool_call_{req_id}>" + __import__("json").dumps(payload) + f"</tool_call_{req_id}>"
        expected_ids = tokenizer.encode(expected_text, add_special_tokens=False)
        assert out.tokens == list(expected_ids)
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass


@pytest.mark.integration
def test_adjusted_logits_passthrough(real_model_env) -> None:
    mi = real_model_env.mi
    tokenizer = real_model_env.pipeline.tokenizer
    pipeline = real_model_env.pipeline
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl

    # Returns AdjustedLogits with original logits (no-op, but exercises integration)
    def mod(event: Any, _tok: Any):
        from shared.types import ForwardPass, AdjustedLogits, Noop
        try:
            if isinstance(event, ForwardPass) and getattr(event, "logits", None) is not None:
                return AdjustedLogits(event.logits)
        except Exception:
            pass
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=4, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=2)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]
        assert isinstance(out.tokens, list)
        assert len(out.tokens) >= 1
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass


@pytest.mark.integration
def test_backtrack_with_reinjection(real_model_env) -> None:
    mi = real_model_env.mi
    tokenizer = real_model_env.pipeline.tokenizer
    pipeline = real_model_env.pipeline
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl

    reinject_text = "B"
    reinject_ids = tokenizer.encode(reinject_text, add_special_tokens=False)

    def mod(event: Any, _tok: Any):
        from shared.types import Sampled, Backtrack, Noop

        if isinstance(event, Sampled) and event.step == 0:
            return Backtrack(n=1, tokens=list(reinject_ids))
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=4, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=3)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]
        assert isinstance(out.tokens, list)
        assert len(out.tokens) >= len(reinject_ids)
        assert out.tokens[: len(reinject_ids)] == list(reinject_ids)
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass


@pytest.mark.integration
def test_adjusted_prefill(real_model_env) -> None:
    mi = real_model_env.mi
    tokenizer = real_model_env.pipeline.tokenizer
    pipeline = real_model_env.pipeline
    format_prompt_from_messages = real_model_env.format_prompt_from_messages
    execute_impl = real_model_env.execute_impl
    def mod(event: Any, _tok: Any):
        from shared.types import Prefilled, AdjustedPrefill, Noop

        if isinstance(event, Prefilled):
            prompt_text = tokenizer.decode(event.context_info.tokens[:event.context_info._prompt_len])
            new_text = prompt_text.replace("Say hi.", "Say bye.")
            prefill_ids = tokenizer.encode(new_text, add_special_tokens=False)
            # Set new prefill tokens; choose a small max_steps to exercise code path
            return AdjustedPrefill(tokens=list(prefill_ids), max_steps=20)
        return Noop()

    mm, prior = _add_mod_temporarily(pipeline, mod)
    try:
        formatted = format_prompt_from_messages(tokenizer, _basic_messages())
        req_id = f"req-mod-actions-{os.urandom(4).hex()}"
        sampling = mi.SamplingParams(
            max_new_tokens=3, top_k=1, top_p=1.0, min_p=0, temperature=0.0, detokenize=True, seed=42
        )
        tg_req = mi.TextGenerationRequest(
            request_id=req_id,
            model_name=str(real_model_env.model_id),
            prompt=formatted,
            sampling_params=sampling,
            tools=None,
        )
        ctx = real_model_env.new_context(tg_req)
        inputs = mi.TextGenerationInputs(batches=[{req_id: ctx}], num_steps=20)
        outputs = execute_impl.execute(pipeline, inputs)
        out = outputs[req_id]
        # Minimal assertion: action executed and tokens were generated
        assert isinstance(out.tokens, list)
        assert len(out.tokens) >= 1
    finally:
        mm.mods = prior
        try:
            mm.forced_queues.clear()
            mm.forced_reason_queues.clear()
        except Exception:
            pass
