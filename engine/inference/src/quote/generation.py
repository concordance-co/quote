from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any

from shared.types import (
    Added,
    AdjustedLogits,
    AdjustedPrefill,
    Backtrack,
    EmitError,
    ForceOutput,
    ForceTokens,
    ForwardPass,
    ModAction,
    ModEvent,
    Prefilled,
    Sampled,
    ToolCalls,
)

from quote.activations.store import ActivationStore
from quote.backends.interface import Backend, GenerationConfig
from quote.features.sae_extract import MinimalSAEExtractor
from quote.logs.logger import IngestAccumulator
from quote.mods.manager import ModManager


@dataclass
class GenerationResult:
    output_ids: list[int]
    output_text: str
    events: list[ModEvent] = field(default_factory=list)
    actions: list[ModAction] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _is_terminal(action: ModAction) -> bool:
    return isinstance(action, (ForceOutput, ToolCalls, EmitError))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode_token(tokenizer: Any, token_id: int) -> str | None:
    if tokenizer is None:
        return None
    try:
        return str(tokenizer.decode([int(token_id)]))
    except Exception:
        return None


def _enqueue_forced(mod_manager: ModManager, request_id: str, tokens: list[int]) -> None:
    if not tokens:
        return
    mod_manager.forced_queues.setdefault(request_id, []).extend(int(t) for t in tokens)


def _serialize_action_details(action: ModAction, tokenizer: Any = None, added_tokens: list[int] | None = None) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if isinstance(action, ForceTokens):
        tokens = list(getattr(action, "tokens", []) or [])
        if added_tokens is not None:
            tokens = list(added_tokens) + tokens
        details["tokens"] = [int(t) for t in tokens]
        details["token_count"] = len(tokens)
    elif isinstance(action, AdjustedPrefill):
        tokens = list(getattr(action, "tokens", []) or [])
        details["token_count"] = len(tokens)
        details["adjusted_max_steps"] = int(getattr(action, "max_steps", 0))
    elif isinstance(action, AdjustedLogits):
        logits = getattr(action, "logits", None)
        if logits is not None and hasattr(logits, "shape"):
            details["logits_shape"] = list(logits.shape)
        token_temp = getattr(action, "token_temp", None)
        if token_temp is not None:
            details["temperature"] = float(token_temp)
    elif isinstance(action, ForceOutput):
        tokens = list(getattr(action, "tokens", []) or [])
        details["tokens"] = [int(t) for t in tokens]
        details["token_count"] = len(tokens)
    elif isinstance(action, Backtrack):
        details["backtrack_steps"] = int(getattr(action, "n", 0))
        tokens = getattr(action, "tokens", None)
        if tokens is not None:
            details["tokens"] = [int(t) for t in tokens]
            details["token_count"] = len(tokens)
    elif isinstance(action, ToolCalls):
        details["has_tool_calls"] = True
    elif isinstance(action, EmitError):
        details["error_message"] = str(getattr(action, "err_str", ""))
    return details


def _record_action(
    accumulator: IngestAccumulator,
    *,
    event_name: str,
    step: int,
    action: ModAction,
    tokenizer: Any = None,
    added_tokens: list[int] | None = None,
) -> None:
    action_type = action.__class__.__name__
    mod_name = str(getattr(action, "_source", "unspecified"))
    mod_logs = getattr(action, "_mod_logs", None)
    if action_type == "Noop" and not mod_logs:
        return
    mod_call_idx = accumulator.add_mod_call(mod_name=mod_name, event_type=event_name, step=step)
    if mod_logs and mod_call_idx is not None:
        accumulator.add_mod_log(mod_call_sequence=mod_call_idx, mod_name=mod_name, log_message=str(mod_logs))
    if action_type != "Noop":
        accumulator.add_action(
            mod_call_sequence=mod_call_idx,
            action_type=action_type,
            action_order=0,
            created_at=int(time.time()),
            details=_serialize_action_details(action, tokenizer=tokenizer, added_tokens=added_tokens),
        )


def _finalize(
    *,
    backend: Backend,
    request_id: str,
    accumulator: IngestAccumulator,
    events: list[ModEvent],
    actions: list[ModAction],
    start_time: float,
    terminal_action: ModAction | None = None,
) -> GenerationResult:
    if isinstance(terminal_action, ForceOutput):
        output_ids = [int(t) for t in getattr(terminal_action, "tokens", [])]
    else:
        output_ids = backend.get_completion_ids(request_id)
    output_text = backend.decode(output_ids)

    accumulator.set_final_output(output_ids, output_text)
    accumulator.mark_request_end(completed_at=_iso_now())
    accumulator.finalize()

    metadata: dict[str, Any] = {
        "request_id": request_id,
        "completed_at": _iso_now(),
        "duration_ms": int((time.time() - start_time) * 1000),
        "steps_executed": len([e for e in events if isinstance(e, Added)]),
    }
    if terminal_action is not None:
        metadata["terminal_action"] = terminal_action.__class__.__name__
        if isinstance(terminal_action, ToolCalls):
            metadata["tool_calls"] = getattr(terminal_action, "tool_calls", None)
        if isinstance(terminal_action, EmitError):
            metadata["error"] = getattr(terminal_action, "err_str", "")

    return GenerationResult(
        output_ids=output_ids,
        output_text=output_text,
        events=events,
        actions=actions,
        metadata=metadata,
    )


def generate(
    *,
    backend: Backend,
    input_ids: list[int],
    request_id: str,
    mod_manager: ModManager,
    config: GenerationConfig | None = None,
    accumulator: IngestAccumulator | None = None,
    activation_store: ActivationStore | None = None,
    sae_extractor: MinimalSAEExtractor | None = None,
) -> GenerationResult:
    cfg = config or GenerationConfig()
    start_time = time.time()
    events: list[ModEvent] = []
    actions: list[ModAction] = []
    tokenizer = backend.tokenizer()
    acc = accumulator or IngestAccumulator(request_id)
    acc.mark_request_start(
        model=getattr(backend, "_model_id", None),
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        created_at=_iso_now(),
    )
    stop_tokens = set(int(t) for t in (cfg.stop_tokens or []))

    prefilled = backend.prefill(request_id, list(input_ids), cfg.max_tokens)
    events.append(prefilled)
    acc.add_event(
        "Prefilled",
        step=prefilled.step,
        created_at=int(time.time()),
        prompt_length=len(getattr(prefilled, "input_ids", []) or input_ids),
        max_steps=prefilled.max_steps,
    )

    for action in mod_manager.dispatch(prefilled):
        actions.append(action)
        _record_action(acc, event_name="Prefilled", step=prefilled.step, action=action, tokenizer=tokenizer)
        if isinstance(action, AdjustedPrefill):
            max_steps = int(getattr(action, "max_steps", 0) or cfg.max_tokens)
            prefilled = backend.prefill(request_id, list(action.tokens), max_steps)
            events.append(prefilled)
            acc.upsert_event(
                "Prefilled",
                step=prefilled.step,
                created_at=int(time.time()),
                prompt_length=len(getattr(prefilled, "input_ids", []) or []),
                max_steps=prefilled.max_steps,
            )
        elif isinstance(action, ForceTokens):
            _enqueue_forced(mod_manager, request_id, list(action.tokens))
        elif _is_terminal(action):
            return _finalize(
                backend=backend,
                request_id=request_id,
                accumulator=acc,
                events=events,
                actions=actions,
                start_time=start_time,
                terminal_action=action,
            )

    while len(backend.get_completion_ids(request_id)) < int(cfg.max_tokens):
        fp = backend.forward_pass(request_id)
        events.append(fp)

        top_tokens = None
        try:
            top_vals, top_idx = fp.top_k_logprob(20)
            top_tokens = [
                {"token": int(t), "logprob": float(v)}
                for t, v in zip(top_idx[0], top_vals[0])
            ]
        except Exception:
            top_tokens = None

        acc.add_event(
            "ForwardPass",
            step=fp.step,
            created_at=int(time.time()),
            top_tokens=top_tokens,
        )

        if activation_store is not None and sae_extractor is not None:
            try:
                source_mode = "inline" if sae_extractor.mode == "inline" else "nearline"
                curr_ids = backend.get_input_ids(request_id)
                curr_tok = curr_ids[-1] if curr_ids else None
                rows = sae_extractor.extract_top_k(
                    hidden_states=getattr(fp, "hidden_states", None),
                    request_id=request_id,
                    step=fp.step,
                    token_position=max(0, len(curr_ids) - 1),
                    token_id=curr_tok,
                    model_id=getattr(backend, "_model_id", ""),
                    source_mode=source_mode,
                )
                if rows:
                    activation_store.write_feature_rows(rows)
            except Exception:
                # Feature extraction is best-effort in Phase 0.
                pass

        current_logits: Any = fp.logits
        step_temperature = float(cfg.temperature)
        restart_loop = False

        for action in mod_manager.dispatch(fp):
            actions.append(action)
            _record_action(acc, event_name="ForwardPass", step=fp.step, action=action, tokenizer=tokenizer)
            if isinstance(action, AdjustedLogits):
                current_logits = action.logits
                if action.token_temp is not None:
                    step_temperature = float(action.token_temp)
            elif isinstance(action, ForceTokens):
                _enqueue_forced(mod_manager, request_id, list(action.tokens))
            elif isinstance(action, Backtrack):
                n = max(0, int(action.n))
                if n > 0:
                    backend.rewind_kv_cache(request_id, n + 1)
                    restart_loop = True
                toks = getattr(action, "tokens", None)
                if toks:
                    _enqueue_forced(mod_manager, request_id, list(toks))
                break
            elif _is_terminal(action):
                return _finalize(
                    backend=backend,
                    request_id=request_id,
                    accumulator=acc,
                    events=events,
                    actions=actions,
                    start_time=start_time,
                    terminal_action=action,
                )

        if restart_loop:
            continue

        forced_queue = mod_manager.forced_queues.get(request_id, [])
        sampled_event: Sampled | None = None
        if forced_queue:
            token = int(forced_queue.pop(0))
            forced = True
        else:
            sampled_event = backend.sample(
                request_id,
                current_logits,
                temperature=step_temperature,
                top_p=cfg.top_p,
                top_k=cfg.top_k,
            )
            token = int(sampled_event.sampled_token)
            forced = False
            events.append(sampled_event)
            acc.add_event(
                "Sampled",
                step=sampled_event.step,
                created_at=int(time.time()),
                sampled_token=token,
                token_text=_decode_token(tokenizer, token),
            )

            sampled_backtrack = False
            for action in mod_manager.dispatch(sampled_event):
                actions.append(action)
                _record_action(acc, event_name="Sampled", step=sampled_event.step, action=action, tokenizer=tokenizer)
                if isinstance(action, ForceTokens):
                    _enqueue_forced(mod_manager, request_id, list(action.tokens))
                elif isinstance(action, Backtrack):
                    n = max(0, int(action.n))
                    if n > 0:
                        backend.rewind_kv_cache(request_id, n)
                        sampled_backtrack = True
                    toks = getattr(action, "tokens", None)
                    if toks:
                        _enqueue_forced(mod_manager, request_id, list(toks))
                    break
                elif _is_terminal(action):
                    return _finalize(
                        backend=backend,
                        request_id=request_id,
                        accumulator=acc,
                        events=events,
                        actions=actions,
                        start_time=start_time,
                        terminal_action=action,
                    )
            if sampled_backtrack:
                continue

        added = backend.add_tokens(request_id, [token], forced)
        events.append(added)
        acc.add_event(
            "Added",
            step=added.step,
            created_at=int(time.time()),
            added_tokens=list(added.added_tokens),
            added_token_count=len(added.added_tokens),
            forced=bool(added.forced),
        )

        added_backtrack = False
        for action in mod_manager.dispatch(added):
            actions.append(action)
            _record_action(
                acc,
                event_name="Added",
                step=added.step,
                action=action,
                tokenizer=tokenizer,
                added_tokens=list(added.added_tokens),
            )
            if isinstance(action, ForceTokens):
                forced_tokens = [int(t) for t in list(action.tokens)]
                if added.forced:
                    mod_manager.forced_queues[request_id] = forced_tokens
                else:
                    mod_manager.forced_queues[request_id] = [int(t) for t in (list(added.added_tokens) + forced_tokens)]
            elif isinstance(action, Backtrack):
                n = max(0, int(action.n) - 1)
                if n > 0:
                    backend.rewind_kv_cache(request_id, n)
                    added_backtrack = True
                toks = getattr(action, "tokens", None)
                if toks:
                    _enqueue_forced(mod_manager, request_id, list(toks))
                break
            elif _is_terminal(action):
                return _finalize(
                    backend=backend,
                    request_id=request_id,
                    accumulator=acc,
                    events=events,
                    actions=actions,
                    start_time=start_time,
                    terminal_action=action,
                )
        if added_backtrack:
            continue

        if stop_tokens and token in stop_tokens:
            break
        eos_id = backend.eos_token_id()
        if eos_id is not None and token == int(eos_id):
            break

    if activation_store is not None:
        try:
            activation_store.cleanup_old_rows()
        except Exception:
            pass

    return _finalize(
        backend=backend,
        request_id=request_id,
        accumulator=acc,
        events=events,
        actions=actions,
        start_time=start_time,
        terminal_action=None,
    )
