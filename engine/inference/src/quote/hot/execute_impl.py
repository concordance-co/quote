from max.driver import Tensor

import logging
import numpy as np
import json
import time

logger = logging.getLogger(__name__)

from max.interfaces import TextGenerationInputs, GenerationStatus, LogProbabilities

from numpy.typing import NDArray
from quote.pipelines.text_gen_pipeline import TextGenerationPipeline
from max import driver
from max.pipelines.core import TextContext
from max.nn.kv_cache import KVCacheInputsSequence
from max.nn.kv_cache.paged_cache.block_manager import BlockManager
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from quote.logs.logger import IngestAccumulator, get_accumulator
from quote.logs.metrics import get_last_step_logits_rows
from quote.logs.emit import emit_step_events
from quote.mods.manager import ModManager
from shared.types import (
    AdjustedPrefill,
    EmitError,
    ForceTokens,
    ForceOutput,
    ToolCalls,
    ForwardPass,
    AdjustedLogits,
    Prefilled,
    Sampled,
    Added,
    Backtrack,
)
from shared.conversation import (
    append_trace_event,
)
import faulthandler

faulthandler.enable()

###############################################################################
# Constants
###############################################################################

_MAX_TOOL_PAYLOAD_CHARS = 2048
_MAX_ACTION_TOKEN_PREVIEW = 128
_ERROR_TOKEN_MARKER = -999_999_999_999


###############################################################################
# Request State Management
###############################################################################

@dataclass
class RequestState:
    """Consolidated state for a single request during generation.

    This dataclass tracks all per-request state during the execute loop,
    including terminal actions, backtracking state, and accumulator references.
    """
    request_id: str
    batch_index: int
    accumulator: Optional[IngestAccumulator] = None

    # Terminal action state
    terminal_force_output: Optional[List[int]] = None
    terminal_tool_call: Any = None
    terminal_error: Optional[str] = None
    is_done: bool = False

    # Backtracking and placeholder state
    placeholder_position: Optional[int] = None
    skip_progress: bool = False
    skip_token: Optional[int] = None
    rewind_n: Optional[int] = None
    prev_completion_idx: Optional[int] = None

    # Sampling parameters (cached for logging)
    top_k: int = 0
    top_p: float = 1.0
    temperature: float = 1.0

    def mark_done(self) -> None:
        """Mark this request as complete."""
        self.is_done = True

    def set_terminal_force_output(self, tokens: List[int]) -> None:
        """Set terminal ForceOutput and mark done."""
        self.terminal_force_output = tokens
        self.mark_done()

    def set_terminal_tool_call(self, payload: Any) -> None:
        """Set terminal ToolCalls and mark done."""
        self.terminal_tool_call = payload
        self.mark_done()

    def set_terminal_error(self, err_str: str) -> None:
        """Set terminal error and mark done."""
        self.terminal_error = err_str
        self.mark_done()

    def has_terminal_action(self) -> bool:
        """Check if this request has any terminal action set."""
        return (self.terminal_force_output is not None or
                self.terminal_tool_call is not None or
                self.terminal_error is not None)

    def reset_step_flags(self) -> None:
        """Reset per-step flags for the next iteration."""
        self.skip_progress = False


@dataclass
class BatchState:
    """Consolidated state for the entire batch during generation.

    Provides convenient access to request states and batch-wide operations.
    """
    request_states: Dict[str, RequestState] = field(default_factory=dict)
    request_id_order: List[str] = field(default_factory=list)

    def __getitem__(self, rid: str) -> RequestState:
        return self.request_states[rid]

    def __iter__(self):
        return iter(self.request_id_order)

    def items(self):
        for rid in self.request_id_order:
            yield rid, self.request_states[rid]

    def all_done(self) -> bool:
        """Check if all requests are done."""
        return all(rs.is_done for rs in self.request_states.values())

    def done_count(self) -> int:
        """Return number of completed requests."""
        return sum(1 for rs in self.request_states.values() if rs.is_done)

    def get_done_request_ids(self) -> Set[str]:
        """Return set of done request IDs."""
        return {rid for rid, rs in self.request_states.items() if rs.is_done}

    def get_terminal_force_outputs(self) -> Dict[str, List[int]]:
        """Get dict of request_id -> force_output tokens for terminal actions."""
        return {
            rid: rs.terminal_force_output
            for rid, rs in self.request_states.items()
            if rs.terminal_force_output is not None
        }

    def get_terminal_tool_calls(self) -> Dict[str, Any]:
        """Get dict of request_id -> tool_call payload for terminal actions."""
        return {
            rid: rs.terminal_tool_call
            for rid, rs in self.request_states.items()
            if rs.terminal_tool_call is not None
        }

    def get_terminal_errors(self) -> Dict[str, str]:
        """Get dict of request_id -> error string for terminal actions."""
        return {
            rid: rs.terminal_error
            for rid, rs in self.request_states.items()
            if rs.terminal_error is not None
        }


###############################################################################
# Action Processing Helpers
###############################################################################

def _process_terminal_action(action: Any, request_state: RequestState) -> bool:
    """Process a terminal action (ForceOutput, ToolCalls, EmitError).

    Args:
        action: The action to process.
        request_state: The request state to update.

    Returns:
        True if action was terminal and processed, False otherwise.
    """
    if isinstance(action, ForceOutput):
        request_state.set_terminal_force_output(list(getattr(action, "tokens", [])))
        return True
    elif isinstance(action, ToolCalls):
        request_state.set_terminal_tool_call(getattr(action, "tool_calls", None))
        return True
    elif isinstance(action, EmitError):
        request_state.set_terminal_error(getattr(action, "err_str", None))
        return True
    return False


def _process_force_tokens_action(
    action: ForceTokens,
    mod_manager: ModManager,
    rid: str,
) -> None:
    """Process a ForceTokens action by adding tokens to the forced queue.

    Args:
        action: The ForceTokens action.
        mod_manager: The mod manager instance.
        rid: The request ID.
    """
    tokens = list(getattr(action, "tokens", []) or [])
    if tokens:
        mod_manager.forced_queues.setdefault(rid, []).extend(tokens)
        if hasattr(mod_manager, "forced_reason_queues"):
            src = getattr(action, "_source", None)
            mod_manager.forced_reason_queues.setdefault(rid, []).extend(
                [str(src)] * len(tokens)
            )


def _process_backtrack_action(
    action: Backtrack,
    request_state: RequestState,
    mod_manager: ModManager,
    context: Any,
    pipeline: Any,
    event_phase: str,
) -> Optional[int]:
    """Process a Backtrack action.

    Args:
        action: The Backtrack action.
        request_state: The request state to update.
        mod_manager: The mod manager instance.
        context: The request context.
        pipeline: The pipeline instance.
        event_phase: Which event phase ('forward_pass', 'sampled', 'added').

    Returns:
        The rewind_n value if backtrack was processed, None otherwise.
    """
    rid = request_state.request_id

    # If explicit empty reinject tokens were provided, mark to skip progress
    if getattr(action, "tokens", None) is not None and not list(
        getattr(action, "tokens", []) or []
    ):
        request_state.skip_progress = True

    # Add replacement tokens to forced queue if provided
    if action.tokens:
        mod_manager.forced_queues.setdefault(rid, []).extend(list(action.tokens))
        if hasattr(mod_manager, "forced_reason_queues"):
            src = getattr(action, "_source", None)
            mod_manager.forced_reason_queues.setdefault(rid, []).extend(
                [str(src)] * len(list(action.tokens))
            )

    # Store previous completion index for backtrack calculation
    request_state.prev_completion_idx = context._completion_start_idx

    # Calculate rewind amount based on event phase
    # Note: For 'added' phase, caller already decremented action.n before calling
    rewind_n = action.n
    if event_phase == 'forward_pass':
        # Pre-Added: add 1 because sampled token hasn't been added yet
        rewind_n = action.n + 1
    # For 'sampled' and 'added' phases, use action.n as-is

    # Perform the cache rewind
    rewind_cache(pipeline, context, action.n)
    request_state.rewind_n = rewind_n

    return rewind_n


###############################################################################
# Additional helpers for structure and clarity
###############################################################################


def _get_or_init_mod_manager(pipeline: TextGenerationPipeline) -> ModManager:
    """Get a ModManager from the pipeline, initializing and wiring tokenizer if needed."""
    mod_manager = getattr(pipeline, "mod_manager", None)
    if not isinstance(mod_manager, ModManager):
        mod_manager = getattr(pipeline, "_sdk_mod_manager", None)
    if not isinstance(mod_manager, ModManager):
        mod_manager = ModManager()
    setattr(pipeline, "mod_manager", mod_manager)
    setattr(pipeline, "_sdk_mod_manager", mod_manager)
    try:
        mod_manager.set_tokenizer(getattr(pipeline, "tokenizer", None))
    except Exception:
        pass
    return mod_manager


def _compute_placeholder_token_id(tokenizer: Any) -> Optional[int]:
    """Determine an ID to use for temporary 'placeholder' tokens when backtracking.

    We attempt to use the last token id of the encoding of the string "©".
    Returns None if no tokenizer is available or encoding fails.
    """
    try:
        enc = tokenizer.encode("©", False)
        if isinstance(enc, (list, tuple)) and len(enc) > 0:
            return int(enc[-1])
    except Exception:
        pass
    return None


def _get_eos_token_id(tokenizer: Any) -> Optional[int]:
    """Best-effort retrieval of the EOS token id from a tokenizer."""
    if tokenizer is None:
        return None
    try:
        # Prefer explicit attribute when available
        eid = getattr(tokenizer, "eos_token_id", None)
        if isinstance(eid, (int, np.integer)):
            return int(eid)
    except Exception:
        pass
    # Fallback to encoding the eos token string if present
    try:
        eos_tok = getattr(tokenizer, "eos_token", None)
        if eos_tok is None:
            return None
        if hasattr(tokenizer, "encode"):
            enc = tokenizer.encode(eos_tok, add_special_tokens=False)
            if isinstance(enc, (list, tuple)) and len(enc) > 0:
                # Most tokenizers will provide a single-id encoding for EOS
                return int(enc[-1])
    except Exception:
        pass
    return None


def _compute_tensor_bitmask(
    bitmask: Optional[np.ndarray], vocab_size: Optional[int], device: Any
) -> Optional[Tensor]:
    """Expand packed 32-bit bitmask to a boolean mask tensor of shape [B, V]."""
    if bitmask is None or vocab_size is None:
        return None
    bits = 2 ** np.arange(32, dtype=np.int32)
    bm = (bitmask[..., np.newaxis] & bits) != 0
    bm = bm.reshape(bitmask.shape[0], -1).astype(np.bool_)
    bm = bm[:, 0:vocab_size]
    return Tensor.from_numpy(bm).to(device)


###############################################################################
# Logging and Serialization Helpers
###############################################################################

def _truncate_tokens(tokens: Any, limit: int = _MAX_ACTION_TOKEN_PREVIEW) -> list[int]:
    try:
        ints = [int(t) for t in tokens]
    except Exception:
        return []
    if len(ints) <= limit:
        return ints
    return ints[:limit]


def _stringify_tool_payload(payload: Any) -> str:
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload)
        except Exception:
            text = str(payload)
    if len(text) <= _MAX_TOOL_PAYLOAD_CHARS:
        return text
    truncated = text[:_MAX_TOOL_PAYLOAD_CHARS]
    return f"{truncated}... (truncated)"


def _serialize_mod_descriptor(mod: Any) -> dict[str, Any]:
    name = getattr(mod, "__name__", None)
    if name is None:
        name = getattr(mod, "__class__", type(mod)).__name__
    description = getattr(mod, "__doc__", None)
    entry: dict[str, Any] = {"name": str(name)}
    if isinstance(description, str) and description.strip():
        entry["description"] = description.strip()
    return entry


def _log_mod_action(
    accumulator: Optional[IngestAccumulator],
    *,
    request_id: str,
    step: int,
    event_name: str,
    action: Any,
    tokenizer: Any = None,
) -> None:
    if accumulator is None:
        return
    if action is None:
        return
    action_type = action.__class__.__name__
    mod_logs = getattr(action, "_mod_logs", None)
    # Skip Noop actions unless they have logs attached
    if action_type == "Noop" and not mod_logs:
        return
    payload: dict[str, Any] = {}

    if isinstance(action, ForceTokens):
        tokens = getattr(action, "tokens", [])
        payload["tokens"] = list(tokens) if isinstance(tokens, (list, tuple)) else []
        payload["tokens_as_text"] = (
            [tokenizer.decode([t]) for t in tokens] if tokenizer and isinstance(tokens, (list, tuple)) else []
        )
        payload["token_count"] = (
            len(tokens) if isinstance(tokens, (list, tuple)) else None
        )
    elif isinstance(action, AdjustedPrefill):
        tokens = getattr(action, "tokens", [])
        payload["tokens"] = list(tokens) if isinstance(tokens, (list, tuple)) else []
        payload["tokens_as_text"] = (
            [tokenizer.decode([t]) for t in tokens] if tokenizer and isinstance(tokens, (list, tuple)) else []
        )
        payload["token_count"] = (
            len(tokens) if isinstance(tokens, (list, tuple)) else None
        )
        payload["adjusted_max_steps"] = getattr(action, "max_steps", None)
    elif isinstance(action, AdjustedLogits):
        logits: Tensor | None = getattr(action, "logits", None)
        if logits is not None:
            payload["logits_shape"] = list(logits.shape)
        payload["note"] = "raw logits omitted"
    elif isinstance(action, ForceOutput):
        tokens = getattr(action, "tokens", [])
        payload["tokens"] = list(tokens) if isinstance(tokens, (list, tuple)) else []
        payload["tokens_as_text"] = (
            [tokenizer.decode([t]) for t in tokens] if tokenizer and isinstance(tokens, (list, tuple)) else []
        )
        payload["token_count"] = (
            len(tokens) if isinstance(tokens, (list, tuple)) else None
        )
    elif isinstance(action, ToolCalls):
        data = getattr(action, "tool_calls", None)
        payload["tool_calls"] = _stringify_tool_payload(data)
    elif isinstance(action, Backtrack):
        payload["backtrack_steps"] = getattr(action, "n", None)
        tokens = getattr(action, "tokens", None)
        if tokens is not None:
            payload["tokens"] = list(tokens) if isinstance(tokens, (list, tuple)) else []
            payload["tokens_as_text"] = (
                [tokenizer.decode([t]) for t in tokens] if tokenizer and isinstance(tokens, (list, tuple)) else []
            )
            payload["token_count"] = (
                len(tokens) if isinstance(tokens, (list, tuple)) else None
            )

    mod_name = getattr(action, "_source", None) or "unspecified"
    mod_call_idx = accumulator.add_mod_call(
        mod_name=mod_name,
        event_type=str(event_name),
        step=step,
    )
    # Add mod logs if captured during dispatch
    if mod_logs and mod_call_idx is not None:
        accumulator.add_mod_log(
            mod_call_sequence=mod_call_idx,
            mod_name=mod_name,
            log_message=mod_logs,
        )
    # Only record action if it's not a Noop (Noops with logs still get mod_call/mod_log recorded above)
    if action_type != "Noop":
        accumulator.add_action(
            mod_call_sequence=mod_call_idx,
            action_type=action_type,
            action_order=0,
            created_at=int(time.time()),
            details=payload if payload else None,
        )


def _encode_tool_calls(
    request_id: str, payload: Any, tokenizer: Any
) -> Optional[list[int]]:
    """
    Encode a ToolCalls payload into tokens using the provided tokenizer if possible.
    Supports HF-like tokenizer.encode or callable returning {'input_ids': ...}.
    """
    text = f"<tool_call_{request_id}>"
    text += payload if isinstance(payload, str) else json.dumps(payload)
    text = text + f"</tool_call_{request_id}>"
    tokens_override = None
    if tokenizer is None:
        return None
    if hasattr(tokenizer, "encode"):
        return tokenizer.encode(text, add_special_tokens=False)
    if callable(tokenizer):
        enc = tokenizer(text)
        if isinstance(enc, dict) and "input_ids" in enc:
            ids = enc["input_ids"]
            if isinstance(ids, list):
                return ids
    return tokens_override


###############################################################################
# Output Finalization
###############################################################################

def _finalize_output_for_request(
    pipeline: TextGenerationPipeline,
    request_state: RequestState,
    context: Any,
    executed_steps: int,
    generated_tokens_host: np.ndarray,
    compute_log_probabilities: bool,
    batch_log_probabilities: list[LogProbabilities],
    placeholder_token_id: Optional[int],
):
    """Finalize output for a single request.

    Args:
        pipeline: The text generation pipeline.
        request_state: The request's state including terminal actions.
        context: The request context.
        executed_steps: Number of steps executed.
        generated_tokens_host: Generated tokens array on host.
        compute_log_probabilities: Whether to compute log probs.
        batch_log_probabilities: Log probabilities for the batch.
        placeholder_token_id: Token ID used for placeholders.

    Returns:
        TextGenerationOutput for this request.
    """
    request_id = request_state.request_id
    batch_index = request_state.batch_index

    # Apply non-terminal generated tokens to context
    for step in range(executed_steps):
        if request_state.has_terminal_action():
            break
        next_token = int(generated_tokens_host[batch_index, step])
        if placeholder_token_id is not None and next_token == placeholder_token_id:
            continue
        log_probs = None
        if compute_log_probabilities and (
            log_probs_for_step := batch_log_probabilities[step]
        ):
            log_probs = log_probs_for_step
        if context._completion_start_idx < context._prompt_len:
            context._completion_start_idx += 1
            context._completion_end_idx += 1
        context.update(new_token=next_token, log_probabilities=log_probs)
        if context.is_done:
            break

    out = context.to_generation_output()
    # Apply terminal overrides if present
    if request_state.terminal_force_output is not None:
        out.tokens = request_state.terminal_force_output
    elif request_state.terminal_tool_call is not None:
        payload = request_state.terminal_tool_call
        tok = getattr(pipeline, "tokenizer", None)
        try:
            encoded = _encode_tool_calls(request_id, payload, tok)
            if encoded is not None:
                out.tokens = encoded
        except Exception as e:
            logger.warning("ToolCalls encode failed: %s", e)

    if placeholder_token_id is not None and hasattr(out, "tokens"):
        out.tokens = [int(t) for t in out.tokens if int(t) != placeholder_token_id]
    # Never include EOS token id in final output tokens
    try:
        eos_id = _get_eos_token_id(getattr(pipeline, "tokenizer", None))
        if eos_id is not None and hasattr(out, "tokens"):
            out.tokens = [int(t) for t in out.tokens if int(t) != int(eos_id)]
    except Exception:
        pass
    return out


###############################################################################
# Batch Initialization
###############################################################################

def _initialize_batch_state(
    pipeline: TextGenerationPipeline,
    inputs: TextGenerationInputs,
    batch: Dict[str, Any],
    mod_manager: ModManager,
) -> BatchState:
    """Initialize BatchState with RequestState for each request.

    Args:
        pipeline: The text generation pipeline.
        inputs: The generation inputs.
        batch: The sorted batch dictionary.
        mod_manager: The mod manager instance.

    Returns:
        Initialized BatchState with all request states.
    """
    request_id_order = list(batch.keys())
    batch_state = BatchState(request_id_order=request_id_order)

    serialized_mods = [
        _serialize_mod_descriptor(mod) for mod in getattr(mod_manager, "mods", [])
    ]
    mod_names = [entry.get("name") for entry in serialized_mods if entry.get("name")]
    active_mod_text = ", ".join(sorted(set(mod_names))) if mod_names else None

    for idx, rid in enumerate(request_id_order):
        pipeline.step_for_request(rid)

        # Initialize forced queues
        if rid not in mod_manager.forced_queues:
            mod_manager.forced_queues[rid] = []
        if (
            getattr(mod_manager, "forced_reason_queues", None) is not None
            and rid not in mod_manager.forced_reason_queues
        ):
            mod_manager.forced_reason_queues[rid] = []

        # Get accumulator and sampling params
        accumulator = get_accumulator(rid)

        # Extract sampling parameters
        try:
            top_k = int(getattr(batch[rid], "sampling_params").top_k)
            top_p = float(getattr(batch[rid], "sampling_params").top_p)
            temperature = float(getattr(batch[rid], "sampling_params").temperature)
        except Exception:
            top_k, top_p, temperature = 0, 1.0, 1.0

        # Create request state
        request_state = RequestState(
            request_id=rid,
            batch_index=idx,
            accumulator=accumulator,
            top_k=top_k,
            top_p=top_p,
            temperature=temperature,
        )
        batch_state.request_states[rid] = request_state

        # Get model name for logging
        model_name_for_req = getattr(batch[rid], "model_name", None) or getattr(
            pipeline, "model_name", None
        )
        if model_name_for_req is None:
            try:
                model_name_for_req = getattr(
                    getattr(pipeline, "_pipeline_config"), "model_config"
                ).model_path
            except Exception:
                model_name_for_req = None

        # Mark request start in accumulator
        max_tokens = inputs.num_steps
        if getattr(batch[rid], "sampling_params", None) is not None:
            max_tokens = getattr(batch[rid], "sampling_params").max_new_tokens or inputs.num_steps

        accumulator.mark_request_start(
            model=model_name_for_req,
            max_tokens=max_tokens,
            temperature=temperature,
            mod_text=active_mod_text,
        )

    return batch_state


def execute(pipeline: TextGenerationPipeline, inputs: TextGenerationInputs):
    """Run the main generation loop with ModManager hooks and backtracking support.

    The generation loop proceeds through these phases:

    1. **Initialization**: Prepare batch, sampling state, and per-request tracking
    2. **Prefill**: Process initial prompts, allow mods to adjust or issue terminal actions
    3. **Generation Loop**: For each step up to num_steps:
       - Forward pass: compute logits, allow AdjustedLogits/ForceTokens/Backtrack/Terminal mods
       - Sample: select token (or override with forced token)
       - Post-sample: emit Sampled and Added events for mods
       - State update: maintain KV cache, prepare next inputs, handle backtracks
    4. **Finalization**: Build outputs per request, apply terminal overrides, clean placeholders

    Args:
        pipeline: The text generation pipeline.
        inputs: Generation inputs including batch and num_steps.

    Returns:
        Dict mapping request_id to TextGenerationOutput.
    """
    # === Phase 1: Initialization ===
    batch = pipeline._maybe_sort_loras(inputs.batch)
    request_id_order = list(batch.keys())
    batch_index_by_request = {rid: idx for idx, rid in enumerate(request_id_order)}

    if pipeline.batch_info_output_fname is not None:
        pipeline._record_batch_info(inputs.batch.values(), inputs.num_steps)

    context_batch = list(inputs.batch.values())
    batch_top_n = [c.log_probabilities for c in context_batch]
    compute_log_probabilities = any(batch_top_n)

    # Initialize mod manager and batch state
    mod_manager = _get_or_init_mod_manager(pipeline)
    batch_state = _initialize_batch_state(pipeline, inputs, batch, mod_manager)



    # ==========================================================================
    # Phase 2: Prefill - Emit Prefilled events and process initial mod actions
    # ==========================================================================
    for rid, context in batch.items():
        ev_prefilled = Prefilled(
            request_id=rid,
            step=pipeline.get_step_for_request(rid),
            max_steps=inputs.num_steps,
            context_info=context,
        )

        acc_prefill = batch_state[rid].accumulator
        if acc_prefill is not None:
            acc_prefill.upsert_event(
                "Prefilled",
                step=pipeline.get_step_for_request(rid),
                created_at=int(time.time()),
                prompt_length=context._prompt_len,
                max_steps=inputs.num_steps,
            )

        # Add Prefill event to trace
        prefill_details = {"prompt_length": context._prompt_len}
        # append_trace_event(rid, "Prefill", 0, prefill_details)

        for action in mod_manager.dispatch(ev_prefilled):
            _log_mod_action(
                batch_state[rid].accumulator,
                request_id=rid,
                step=pipeline.get_step_for_request(rid),
                event_name="Prefilled",
                action=action,
                tokenizer=getattr(pipeline, "tokenizer", None),
            )
            if isinstance(action, (ForceOutput, ToolCalls, EmitError)):
                _process_terminal_action(action, batch_state[rid])
                break
            elif isinstance(action, AdjustedPrefill):
                # Overwrite this request's input prompt with AdjustedPrefill.tokens and optionally cap max steps
                new_prompt_tokens = [
                    int(t) for t in getattr(action, "tokens", []) or []
                ]
                # Update num_steps if the action provided a positive max_steps
                ms = int(getattr(action, "max_steps", 0))
                if ms > 0:
                    num_steps = ms
                if new_prompt_tokens:
                    try:
                        new_len = len(new_prompt_tokens)
                        context.tokens[:new_len] = new_prompt_tokens
                        context._active_idx = new_len
                        context._end_idx = new_len
                        context._completion_start_idx = context._active_idx
                        context._completion_end_idx = context._active_idx
                        context._prompt_len = new_len
                    except Exception as e:
                        logger.warning("AdjustedPrefill failed to overwrite prompt for %s: %s", rid, e)
                break
            elif isinstance(action, ForceTokens):
                _process_force_tokens_action(action, mod_manager, rid)

    model_inputs, num_steps, bitmask = pipeline.prepare_batch(
        context_batch, inputs.num_steps
    )

    generated_tokens = Tensor.from_numpy(
        np.empty((len(context_batch), 0), dtype=np.int64)
    ).to(pipeline._devices[0])

    temperature = Tensor.from_numpy(
        np.array(
            [c.sampling_params.temperature for c in context_batch], dtype=np.float32
        )
    ).to(pipeline._devices[0])
    top_k_np = np.array(
        [c.sampling_params.top_k for c in context_batch], dtype=np.int64
    )
    top_k = Tensor.from_numpy(top_k_np).to(pipeline._devices[0])
    max_k = Tensor.from_numpy(np.array(np.max(top_k_np), dtype=np.int64))
    top_p = Tensor.from_numpy(
        np.array([c.sampling_params.top_p for c in context_batch], dtype=np.float32)
    ).to(pipeline._devices[0])
    seed = Tensor.from_numpy(
        np.array(
            [c.sampling_params.seed + c.current_length for c in context_batch],
            dtype=np.uint64,
        )
    ).to(pipeline._devices[0])

    if pipeline._pipeline_config.sampling_config.do_penalties:
        frequency_data = [
            pipeline._build_token_frequency_csr(context_batch, num_steps),
            pipeline._build_token_frequency_csr(
                context_batch, num_steps, include_prompt=True
            ),
        ]
        frequency_penalty = Tensor.from_numpy(
            np.array(
                [c.sampling_params.frequency_penalty for c in context_batch],
                dtype=np.float32,
            )
        ).to(pipeline._devices[0])
        presence_penalty = Tensor.from_numpy(
            np.array(
                [c.sampling_params.presence_penalty for c in context_batch],
                dtype=np.float32,
            )
        ).to(pipeline._devices[0])
        repetition_penalty = Tensor.from_numpy(
            np.array(
                [c.sampling_params.repetition_penalty for c in context_batch],
                dtype=np.float32,
            )
        ).to(pipeline._devices[0])
    else:
        pipeline._check_need_penalties(context_batch)
        frequency_data = None
        frequency_penalty = None
        presence_penalty = None
        repetition_penalty = None

    min_tokens_masks = pipeline._build_min_tokens_masks(context_batch, num_steps)

    curr_step_inputs = model_inputs
    prompt_lens = [len(context.tokens) for context in context_batch]

    batch_log_probabilities: list[list[LogProbabilities]] = [[] for i in range(len(context_batch))]

    # Placeholder handling for backtrack/rectangular outputs
    PLACEHOLDER_TOKEN_ID = _compute_placeholder_token_id(
        getattr(pipeline, "tokenizer", None)
    )
    assert PLACEHOLDER_TOKEN_ID, "Unsupported tokenizer"

    # Track positions (column indices) in generated_tokens that currently contain temporary placeholders per request.
    placeholder_positions: Dict[str, int | None] = {
        rid: None for rid in request_id_order
    }
    # Track per-request intent to skip progress for this step (backtrack with empty reinject tokens)
    skip_step_progress: Dict[str, bool] = {rid: False for rid in request_id_order}
    skip_step_token: Dict[str, int | None] = {rid: None for rid in request_id_order}

    rewind_cache_n = {}

    # ==========================================================================
    # Phase 3: Main Generation Loop
    # ==========================================================================
    # Each iteration:
    #   1. Check early termination conditions
    #   2. Execute forward pass and dispatch ForwardPass events to mods
    #   3. Sample tokens (or apply forced tokens)
    #   4. Dispatch Sampled events to mods
    #   5. Dispatch Added events to mods
    #   6. Update KV cache and prepare inputs for next step
    #   7. Handle backtracking and placeholder management
    # ==========================================================================
    for i in range(num_steps):
        prev_completion_idx = {}
        num_done = batch_state.done_count()
        ctx_batch = len(context_batch)
        if num_done == ctx_batch and context_batch[0]._start_idx != 0:
            # check if we can end early, we cannot if we have pending forced tokens
            has_pending_forced = False
            if mod_manager:
                for rid in request_id_order:
                    if has_pending_forced:
                        break
                    if batch_state[rid].is_done:
                        continue
                    has_pending_forced = len(mod_manager.forced_queues.get(rid, [])) > 0
            if not has_pending_forced:
                break
        model_outputs = pipeline._pipeline_model.execute(
            model_inputs=curr_step_inputs
        )  # EXECUTE ON FULL BATCH
        logits_for_sampling = model_outputs.logits
        temp_for_sampling = temperature
        last_adjusted: Optional[Tensor] = None

        # Track whether we've already accepted ForceTokens for a request this step
        forced_added_this_step: set[str] = set()
        if isinstance(mod_manager, ModManager):
            for rid in request_id_order:
                offsets = getattr(model_outputs, "logit_offsets", None)
                if offsets:
                    bidx = batch_index_by_request[rid]
                    start = offsets[bidx]
                    # logit offsets start with [0] so bidx+1 guaranteed to exist
                    logits = model_outputs.logits[start:offsets[bidx+1]]
                    ev_fp = ForwardPass(
                        request_id=rid,
                        step=pipeline.get_step_for_request(rid),
                        logits=logits,
                    )
                else:
                    ev_fp = ForwardPass(
                        request_id=rid,
                        step=pipeline.get_step_for_request(rid),
                        logits=model_outputs.logits,
                    )

                # Capture event details for trace
                fp_details = {}
                try:
                    # Get current generated text
                    context = batch.get(rid)
                    tokens_list = curr_step_inputs.tokens.to_numpy()
                    if pipeline.tokenizer:
                        text = pipeline.tokenizer.decode(tokens_list)
                        fp_details["input_text"] = text

                    # Get top tokens from logits
                    bidx = batch_index_by_request[rid]
                    if offsets:
                        start = offsets[bidx]
                        logits_slice = model_outputs.logits[start:offsets[bidx+1]]
                    else:
                        logits_slice = model_outputs.logits

                    if logits_slice is not None:
                        logits_np = logits_slice.to_numpy() if hasattr(logits_slice, 'to_numpy') else np.asarray(logits_slice)
                        if logits_np.ndim > 1:
                            logits_np = logits_np.reshape(-1)
                        # Compute log-softmax for stability
                        m = np.max(logits_np)
                        log_probs = logits_np - (m + np.log(np.exp(logits_np - m).sum()))
                        top_indices = np.argsort(log_probs)[-20:][::-1]
                        top_tokens = []
                        for idx in top_indices:
                            token_entry = {"token": int(idx), "logprob": float(log_probs[idx])}
                            if pipeline.tokenizer:
                                try:
                                    token_entry["token_str"] = pipeline.tokenizer.decode([int(idx)])
                                except Exception:
                                    token_entry["token_str"] = f"[{idx}]"
                            else:
                                token_entry["token_str"] = f"[{idx}]"
                            top_tokens.append(token_entry)
                        fp_details["top_tokens"] = top_tokens
                except Exception as e:
                    logger.debug("Failed to capture ForwardPass trace details for %s: %s", rid, e)

                # append_trace_event(rid, "ForwardPass", i, fp_details)
                acc_fp = batch_state[rid].accumulator
                if acc_fp is not None:
                    acc_fp.add_event(
                        "ForwardPass",
                        step=pipeline.get_step_for_request(rid),
                        created_at=int(time.time()),
                        input_text=fp_details.get("input_text"),
                        top_tokens=fp_details.get("top_tokens"),
                    )
                for action in mod_manager.dispatch(ev_fp):
                    _log_mod_action(
                        batch_state[rid].accumulator,
                        request_id=rid,
                        step=pipeline.get_step_for_request(rid),
                        event_name="ForwardPass",
                        action=action,
                        tokenizer=getattr(pipeline, "tokenizer", None),
                    )
                    if isinstance(action, AdjustedLogits):
                        if isinstance(action.logits, Tensor):
                            logits = action.logits.to(model_outputs.logits.device)
                        elif isinstance(action.logits, NDArray[Any]):
                            logits = Tensor.from_numpy(action.logits).to(model_outputs.logits.device)
                        else:
                            logger.warning("Invalid type in action logits: expected Tensor or ndarray, got %s", type(action.logits))
                            continue
                        if not last_adjusted:
                            last_adjusted = model_outputs.logits.copy()

                        start = None
                        if offsets:
                            start = offsets[bidx]
                        if start:
                            last_adjusted[start:offsets[bidx+1]].inplace_copy_from(logits)
                        else:
                            last_adjusted = logits

                        if action.token_temp:
                            temp_as_numpy = Tensor.from_numpy(
                                np.zeros(temperature.shape, dtype=np.uint32)
                            )
                            temp_as_numpy.inplace_copy_from(temperature)
                            temp_as_numpy = temp_as_numpy.to_numpy()
                            temp_as_numpy[batch_index_by_request[rid]] = (
                                action.token_temp
                            )
                            temp_for_sampling = Tensor.from_numpy(temp_as_numpy).to(
                                pipeline._devices[0]
                            )
                    elif isinstance(action, ForceTokens):
                        if rid not in forced_added_this_step:
                            _process_force_tokens_action(action, mod_manager, rid)
                            forced_added_this_step.add(rid)
                    elif isinstance(action, Backtrack):
                        rs = batch_state[rid]
                        _process_backtrack_action(
                            action, rs, mod_manager,
                            inputs.batch[rid], pipeline, 'forward_pass'
                        )
                        skip_step_progress[rid] = rs.skip_progress
                        prev_completion_idx[rid] = rs.prev_completion_idx
                        rewind_cache_n[rid] = rs.rewind_n
                        break
                    elif isinstance(action, (ForceOutput, ToolCalls, EmitError)):
                        _process_terminal_action(action, batch_state[rid])
                        break
                    # Others => Noop
            if last_adjusted is not None:
                logits_for_sampling = last_adjusted

        tensor_bitmask = _compute_tensor_bitmask(
            bitmask, pipeline.vocab_size, pipeline._devices[0]
        )

        new_tokens, new_generated_tokens, new_seed = pipeline.sample_logits(
            logits_for_sampling,
            generated_tokens,
            top_k,
            max_k,
            temp_for_sampling,
            top_p,
            seed,
            logit_offsets=model_outputs.logit_offsets,
            bitmask=tensor_bitmask,
            frequency_data=frequency_data,
            min_tokens_mask=min_tokens_masks[i] if min_tokens_masks else None,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            repetition_penalty=repetition_penalty,
        )

        generated_tokens = new_generated_tokens
        seed = new_seed

        # === Sampled event (per-request, after selecting token) ===
        # Track tokens to inject directly into generated outputs for requests that are terminal
        tokens_np = None
        try:
            tokens_np = new_tokens.copy()
        except Exception:
            tokens_np = None

        step_adjusted = last_adjusted is not None
        logits_to_log = (
            last_adjusted if last_adjusted is not None else model_outputs.logits
        )
        batch_indices = list(batch_index_by_request.values())
        raw_logits_rows = get_last_step_logits_rows(
            logits_obj=logits_to_log, batch_indices=batch_indices
        )

        # This pattern can be abstracted into helper function
        if isinstance(mod_manager, ModManager) and tokens_np is not None:
            for rid in request_id_order:
                if batch_state[rid].is_done:
                    continue
                bidx = batch_index_by_request[rid]

                # If this request is marked to skip progress, do not emit Sampled for it
                if skip_step_progress.get(rid, False):
                    continue

                tmp = Tensor.from_numpy(np.zeros(tokens_np[bidx].shape, dtype=np.int64))
                tmp.inplace_copy_from(tokens_np[bidx])
                sampled_tok = int(tmp.item())

                # Capture sampled token details for trace
                sampled_details = {}
                try:
                    if pipeline.tokenizer:
                        token_text = pipeline.tokenizer.decode([sampled_tok])
                        sampled_details["token_text"] = token_text
                except Exception:
                    pass
                # append_trace_event(rid, "Sampled", i, sampled_details)
                acc_sampled = batch_state[rid].accumulator
                if acc_sampled is not None:
                    acc_sampled.add_event(
                        "Sampled",
                        step=pipeline.get_step_for_request(rid),
                        created_at=int(time.time()),
                        sampled_token=sampled_tok,
                        token_text=sampled_details.get("token_text"),
                    )

                ev_sampled = Sampled(
                    request_id=rid,
                    step=pipeline.get_step_for_request(rid),
                    sampled_token=sampled_tok,
                )
                for action in mod_manager.dispatch(ev_sampled):
                    _log_mod_action(
                        batch_state[rid].accumulator,
                        request_id=rid,
                        step=pipeline.get_step_for_request(rid),
                        event_name="Sampled",
                        action=action,
                        tokenizer=getattr(pipeline, "tokenizer", None),
                    )
                    if isinstance(action, ForceTokens):
                        if rid not in forced_added_this_step:
                            _process_force_tokens_action(action, mod_manager, rid)
                            forced_added_this_step.add(rid)
                    elif isinstance(action, Backtrack):
                        rs = batch_state[rid]
                        _process_backtrack_action(
                            action, rs, mod_manager,
                            inputs.batch[rid], pipeline, 'sampled'
                        )
                        skip_step_progress[rid] = rs.skip_progress
                        prev_completion_idx[rid] = rs.prev_completion_idx
                        rewind_cache_n[rid] = rs.rewind_n
                        break
                    elif isinstance(action, (ForceOutput, ToolCalls, EmitError)):
                        _process_terminal_action(action, batch_state[rid])
                        break

        # === Added event (per-request, after appending token to generated buffer) ===
        if isinstance(mod_manager, ModManager) and tokens_np is not None:
            for rid in request_id_order:
                if batch_state[rid].is_done:
                    continue
                bidx = batch_index_by_request[rid]
                q = mod_manager.forced_queues.get(rid, [])
                forced = False
                if q:
                    added_toks = q
                    forced = True
                else:
                    tmp = Tensor.from_numpy(np.zeros((1,), dtype=np.int64))
                    tmp.inplace_copy_from(tokens_np[bidx])
                    added_toks = [int(tmp.item())]

                # If this request is marked to skip progress, do not emit Added for it
                if skip_step_progress.get(rid, False) or (rewind_cache_n.get(rid) and not q):
                    continue

                # Capture Added event details for trace
                added_details = {
                    "token_count": len(added_toks),
                    "forced": forced
                }
                if forced and pipeline.tokenizer and len(added_toks) <= 5:
                    # Show forced tokens if not too many
                    try:
                        token_texts = [pipeline.tokenizer.decode([tok]) for tok in added_toks]
                        added_details["tokens"] = token_texts
                    except Exception:
                        pass
                # append_trace_event(rid, "Added", i, added_details)
                acc_added = batch_state[rid].accumulator
                if acc_added is not None:
                    acc_added.add_event(
                        "Added",
                        step=pipeline.get_step_for_request(rid),
                        created_at=int(time.time()),
                        added_tokens=added_toks,
                        added_token_count=len(added_toks),
                        forced=forced,
                    )

                ev_added = Added(
                    request_id=rid,
                    step=pipeline.get_step_for_request(rid),
                    added_tokens=added_toks,
                    forced=forced,
                )
                for action in mod_manager.dispatch(ev_added):
                    _log_mod_action(
                        batch_state[rid].accumulator,
                        request_id=rid,
                        step=pipeline.get_step_for_request(rid),
                        event_name="Added",
                        action=action,
                        tokenizer=getattr(pipeline, "tokenizer", None),
                    )
                    if isinstance(action, ForceTokens):
                        if rid not in forced_added_this_step:
                            # Include already-added tokens first, then forced tokens
                            # Result: "hello" + " world" = "hello world"
                            forced_tokens = list(getattr(action, "tokens", []) or [])
                            combined = list(added_toks) + forced_tokens
                            mod_manager.forced_queues[rid] = combined
                            if hasattr(mod_manager, "forced_reason_queues"):
                                src = getattr(action, "_source", None)
                                mod_manager.forced_reason_queues[rid] = [str(src)] * len(combined)
                            forced_added_this_step.add(rid)
                    elif isinstance(action, Backtrack):
                        rs = batch_state[rid]
                        # Added event: decrement n by 1 since token is already added
                        action.n = max(0, action.n - 1)
                        _process_backtrack_action(
                            action, rs, mod_manager,
                            inputs.batch[rid], pipeline, 'added'
                        )
                        skip_step_progress[rid] = rs.skip_progress
                        prev_completion_idx[rid] = rs.prev_completion_idx
                        rewind_cache_n[rid] = rs.rewind_n
                        break
                    elif isinstance(action, (ForceOutput, ToolCalls, EmitError)):
                        _process_terminal_action(action, batch_state[rid])
                        break

        # Increment step counter for active requests after processing all events
        for rid in request_id_order:
            if not batch_state[rid].is_done:
                pipeline.step_for_request(rid)

        assert isinstance(curr_step_inputs.kv_cache_inputs, KVCacheInputsSequence), (
            "prepare_batch instantiates and passes this as a KVCacheInputsSequence"
        )
        assert isinstance(curr_step_inputs.kv_cache_inputs.kv_cache_inputs, list), (
            "increment_cache_lengths instantiates and passes this as a list"
        )

        curr_step_inputs.kv_cache_inputs.kv_cache_inputs = (  # type: ignore[assignment, attr-defined]
            pipeline._pipeline_model.kv_manager.increment_cache_lengths(
                curr_step_inputs.kv_cache_inputs.kv_cache_inputs,  # type: ignore[attr-defined]
                curr_step_inputs,
            )
        )

        new_tokens_clone = Tensor.from_numpy(
            np.zeros(new_tokens.shape, dtype=np.int64)
        ).to(new_tokens.device)
        new_tokens_clone.inplace_copy_from(new_tokens)
        new_tokens_clone_np = new_tokens_clone.to_numpy()

        curr_step_inputs = pipeline._pipeline_model.prepare_next_token_inputs(
            new_tokens, curr_step_inputs
        )

        # Pseudocode of how the following works:
        #
        #
        # Update curr_step_inputs and generated outputs:
        #   By default:
        #       generated_tokens.append(sampled)
        #       curr_step_input is correct (tokens = sampled, offset_rows += 1, cache_lengths += 1, max_lengths[1: ])
        #   Do the default flow then:
        #       - handle backtrack
        #            - rewind_cache_n[rid] > 0:
        #                - placeholder_pos[rid] = max(0, placeholder_id[rid] - rewind_cache_n[rid])
        #                - generated_tokens[placeholder_pos[rid]:] = placeholder_token_id
        #                - skip_progress[rid] = True
        #            - update cache_lengths
        #                - cache_lengths[bidx].inplace_copy_from(cache_lengths_clone[bidx].item() - rewind_cache_n[rid])
        #       - mark_done:
        #            - sampled && !q && eos == sampled && !skip_progress => mark_done
        #            - q && eos in q                                     => mark_done
        #            - else                                              => noop
        #       - add to generated_tokens:
        #            - q and done     => add q[:-1] to generated_tokens[placeholder_id[rid]:], placeholder_pos[rid] += (q - 1)
        #            - q and !done    => add q to generated_tokens[placeholder_id[rid]:], placeholder_pos[rid] += q
        #            - !q             => noop
        #       - update curr_step_inputs if q:
        #            - update tokens and offsets:
        #                - curr_step_inputs.tokens = q
        #                - curr_step_inputs.input_row_offsets = [i + max(1, forced_queues[rid]) for i in range(0, len(reqs))]
        #            - update max_lengths
        #                - cache_lengths must be updated prior to running this
        #                - find the largest sequence for the batch
        #                    - max_seq = max([cache_lengths_clone[batch_index_by_request[rid]].item() - rewind_cache_n[rid] for rid, bidx in enumerate(request_id_order)])
        #                - construct the new max
        #                    - max_sequences = np.ones((max_sequences - max_seq,)) # [1, 1, 1, 1, ...]
        #                    - max_sequences[0] = max_seq
        #                    - max_steps = np.arange(max_seq, steps)
        #                    - new_max = np.stack(max_sequences, max_steps)
        #                - curr_step_inputs.max_lengths = Tensor.from_numpy(new_max) # max lengths lives on the cpu
        #        - invariants
        #            - offsets cover the input tokens
        #                - input_row_offsets[-1] == curr_step_inputs.tokens.shape[0]
        #            - the largest input fits in next max_lengths
        #                - max([input_row_offsets[i] - input_row_offsets[i - 1] for i in range(1, len(input_row_offsets))]) == max_lengths[0, 0]
        #            - cache_lengths includes only the the values we care about
        #                - cache_lengths[rid] == prompts[rid] + len(generated_tokens[placeholder_id[rid]:])
        #        - len(marked_done) == len(batch) => break inference loop

        eos_id = _get_eos_token_id(getattr(pipeline, "tokenizer", None))
        max_generated_for_step = 0
        max_sequence_for_step = 1
        max_backtrack = None
        add_skip_token_to_output = False
        offsets = [i for i in range(0, len(request_id_order) + 1)]
        for rid in request_id_order:
            bidx = batch_index_by_request[rid]
            q = mod_manager.forced_queues.get(rid, [])
            forced = len(q) > 0

            if forced:
                offsets[bidx + 1] = len(q)

            num_placeholders = generated_tokens.shape[1] - (
                placeholder_positions[rid] or 0
            )

            # ================
            # HANDLE_BACKTRACK
            # ================
            if rewind_cache_n.get(rid) and rewind_cache_n[rid] > 0:
                if not forced:
                    # We add one to rewind_cache_n to backtrack 1 extra token if !forced so that on the next fwd pass we can have a meaningful token.
                    # For example, if we have "Hello, there. My name is Brock. What's your name?", and after a normal backtrack, we would
                    # have something like: "Hello, there. My name is Brock.", but the current `next_token` is sampled based on "Hello, there. My name is Brock. What's your name?"
                    #
                    # So for a relevant `next_token`, we have to rewind one extra and store that token to be assigned into curr_step_inputs.tokens
                    # rewind_cache_n[rid] += 1

                    if (
                        context_batch[bidx].active_idx
                        == context_batch[bidx]._prompt_len
                    ):
                        skip_step_token[rid] = context_batch[bidx].tokens[
                            context_batch[bidx].active_idx
                        ]
                    else:
                        # guaranteed to exist
                        idx = prev_completion_idx[rid] - rewind_cache_n[rid]
                        skip_step_token[rid] = context_batch[bidx].tokens[idx]
                        add_skip_token_to_output = True

                max_backtrack = max(
                    max_backtrack if max_backtrack else 0, rewind_cache_n[rid]
                )

                # update placeholder tokens in generated_tokens
                subseq_len = min(
                    num_placeholders + rewind_cache_n[rid], generated_tokens.shape[1]
                )
                subseq = Tensor.from_numpy(
                    np.repeat(PLACEHOLDER_TOKEN_ID, subseq_len)
                ).to(generated_tokens.device)
                generated_tokens[
                    bidx, max(0, generated_tokens.shape[1] - subseq_len) :
                ].inplace_copy_from(subseq)
                placeholder_positions[rid] = max(
                    0, (placeholder_positions[rid] or 0) - rewind_cache_n[rid]
                )
                skip_step_progress[rid] = (
                    skip_step_token.get(rid) is None or not add_skip_token_to_output
                )

                # HANDLE CACHE_LENGTHS: update considered kv cache
                kv_len_inputs = len(curr_step_inputs.kv_cache_inputs.kv_cache_inputs)
                for i in range(0, kv_len_inputs):
                    cache_lengths_clone = Tensor.from_numpy(
                        np.zeros(
                            curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                                i
                            ].cache_lengths.shape,
                            dtype=np.uint32,
                        )
                    ).to(
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                            i
                        ].cache_lengths.device
                    )
                    cache_lengths_clone.inplace_copy_from(
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                            i
                        ].cache_lengths
                    )
                    cache_lengths_clone_np = cache_lengths_clone.to_numpy()
                    new_len = Tensor.from_numpy(
                        np.asarray(
                            int(cache_lengths_clone_np[bidx]) - rewind_cache_n[rid],
                            dtype=np.uint32,
                        )
                    )
                    curr_step_inputs.kv_cache_inputs.kv_cache_inputs[i].cache_lengths[
                        bidx
                    ].inplace_copy_from(new_len)

            # ================
            # MARK DONE
            # ================
            if eos_id:
                if (
                    not skip_step_progress[rid]
                    and not forced
                    and int(new_tokens_clone_np[bidx]) == eos_id
                ):
                    batch_state[rid].mark_done()
                elif forced:
                    if any([int(tok) == int(eos_id) for tok in q]):
                        batch_state[rid].mark_done()

            # ================
            # PREWORK
            # ================
            max_generated_for_step = max(
                max_generated_for_step, max(0, len(q) - num_placeholders)
            )
            max_sequence_for_step = max(max_sequence_for_step, len(q))

        expanded_generated_tokens = None
        if max_generated_for_step > 0:
            expanded_np = np.zeros(
                (
                    generated_tokens.shape[0],
                    generated_tokens.shape[1] + max_generated_for_step,
                ),
                dtype=np.int64,
            )
            expanded_generated_tokens = Tensor.from_numpy(expanded_np).to(
                generated_tokens.device
            )

        updated_generated_tokens = (
            expanded_generated_tokens if expanded_generated_tokens else generated_tokens
        )

        for i in range(1, len(offsets)):
            offsets[i] = offsets[i] + offsets[i - 1]

        updated_tokens = np.zeros((offsets[len(offsets) - 1]), dtype=np.int64)

        for rid in request_id_order:
            bidx = batch_index_by_request[rid]
            q = mod_manager.forced_queues.get(rid, [])
            forced = len(q) > 0

            php = placeholder_positions[rid]
            if php is not None:
                pos = min(php, generated_tokens.shape[1])
            else:
                pos = generated_tokens.shape[1] - 1

            # ================
            # EXPAND GENERATED TOKENS WITH PLACEHOLDER
            # ================
            if expanded_generated_tokens:
                expanded_generated_tokens[
                    bidx, : generated_tokens.shape[1]
                ].inplace_copy_from(generated_tokens[bidx, :])
                placeholder_extension = Tensor.from_numpy(
                    np.repeat(PLACEHOLDER_TOKEN_ID, max_generated_for_step)
                ).to(generated_tokens.device)
                expanded_generated_tokens[
                    bidx, generated_tokens.shape[1] :
                ].inplace_copy_from(placeholder_extension)
                placeholder_positions[rid] = (
                    placeholder_positions[rid]
                    if placeholder_positions[rid] is not None
                    else generated_tokens.shape[1] - 1
                )
                pos = placeholder_positions[rid]

            # ================
            # ADD FORCED/SAMPLED TO GENERATED TOKENS
            # ================
            sampled_tok = (
                np.asarray([int(skip_step_token[rid])])
                if skip_step_token.get(rid)
                else np.asarray([int(new_tokens_clone_np[bidx])], dtype=np.int64)
            )
            tokens_to_add = np.asarray(q, dtype=np.int64) if q else sampled_tok
            new_gt = Tensor.from_numpy(
                np.repeat(
                    PLACEHOLDER_TOKEN_ID, updated_generated_tokens[bidx, :].shape[0]
                )
            ).to(generated_tokens.device)
            new_gt.inplace_copy_from(updated_generated_tokens[bidx, :])
            new_gt_np = new_gt.to_numpy().copy()
            if forced:
                new_gt_np[-1] = PLACEHOLDER_TOKEN_ID
                new_gt_np[pos : pos + len(tokens_to_add)] = tokens_to_add
                updated_generated_tokens[bidx, :].inplace_copy_from(
                    Tensor.from_numpy(new_gt_np).to(generated_tokens.device)
                )
                placeholder_positions[rid] = (placeholder_positions[rid] or 0) + len(
                    tokens_to_add
                )
            else:
                if skip_step_token.get(rid) and add_skip_token_to_output:
                    # backtrack but keeps some of the generated content
                    new_gt_np[-1] = PLACEHOLDER_TOKEN_ID
                    new_gt_np[pos] = tokens_to_add
                elif not skip_step_token.get(rid):
                    # standard sampled token
                    new_gt_np[-1] = PLACEHOLDER_TOKEN_ID
                    new_gt_np[pos] = tokens_to_add
                else:
                    # backtrack into original prompt
                    new_gt_np[-1] = PLACEHOLDER_TOKEN_ID
                    pass
                updated_generated_tokens[bidx, :].inplace_copy_from(
                    Tensor.from_numpy(new_gt_np).to(generated_tokens.device)
                )
                if skip_step_progress[rid] == False:
                    if placeholder_positions[rid] is not None:
                        placeholder_positions[rid] = (
                            placeholder_positions[rid] or 0
                        ) + 1
                    else:
                        placeholder_positions[rid] = updated_generated_tokens.shape[1]

            # ================
            # UPDATE STEP TOKENS
            # ================
            updated_tokens[offsets[bidx] : offsets[bidx + 1]] = tokens_to_add
            if skip_step_token[rid]:
                # we backtracked without forcing tokens. We need to throw away the sampled token, and use the skip_step_token
                skip_step_token[rid] = None

        generated_tokens = updated_generated_tokens

        for rid in request_id_order:
            bidx = batch_index_by_request[rid]
            q = mod_manager.forced_queues.get(rid, [])
            forced = len(q) > 0

            # ================
            # UPDATE STEP TOKENS & OFFSETS
            # ================
            curr_step_inputs.tokens = Tensor.from_numpy(updated_tokens).to(
                curr_step_inputs.tokens.device
            )
            if isinstance(curr_step_inputs.input_row_offsets, Tensor):
                device = curr_step_inputs.input_row_offsets.device
            else:
                device = driver.CPU()
            curr_step_inputs.input_row_offsets = Tensor.from_numpy(
                np.asarray(offsets, np.uint32)
            ).to(device)

            # ================
            # UPDATE STEP MAX LENGTHS
            # ================
            len_kv_inputs = len(curr_step_inputs.kv_cache_inputs.kv_cache_inputs)
            if max_backtrack is not None:
                # if we backtracked, we have to reconstruct the max_lengths tensor
                for i in range(0, len_kv_inputs):
                    if (
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                            i
                        ].max_lengths.shape[0]
                        == 0
                    ):
                        # we are done anyway
                        break
                    start = (
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[i]
                        .max_lengths[0, 1]
                        .item()
                        - max_backtrack
                    )
                    end = num_steps + max(prompt_lens)
                    max_sequences = np.ones((end - start,), dtype=np.uint32)
                    max_sequences[0] = max_sequence_for_step
                    max_steps = np.arange(start, end, dtype=np.uint32)
                    new_max = np.stack((max_sequences, max_steps), axis=1)
                    # max_lengths lives on the CPU
                    curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                        i
                    ].max_lengths = Tensor.from_numpy(new_max)
            else:
                # otherwise, we can just chop off max_sequence_for_step
                for i in range(0, len_kv_inputs):
                    ml = curr_step_inputs.kv_cache_inputs.kv_cache_inputs[i].max_lengths
                    # If max_lengths does not have enough rows (e.g. short scheduler step), rebuild a minimal valid window
                    if ml.shape[0] < max_sequence_for_step or ml.shape[0] == 0:
                        start = 0
                        end = max(prompt_lens) + max_sequence_for_step
                        max_sequences = np.ones((max(1, end - start),), dtype=np.uint32)
                        max_sequences[0] = max_sequence_for_step
                        max_steps = np.arange(
                            start, start + max_sequences.shape[0], dtype=np.uint32
                        )
                        new_max = np.stack((max_sequences, max_steps), axis=1)
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                            i
                        ].max_lengths = Tensor.from_numpy(new_max)
                    else:
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                            i
                        ].max_lengths = ml[max_sequence_for_step - 1 :, :]
                        curr_step_inputs.kv_cache_inputs.kv_cache_inputs[i].max_lengths[
                            0, 0
                        ] = max_sequence_for_step

            # ================
            # LogProbabilities
            # ================
            if compute_log_probabilities:
                if q:
                    for t in q:
                        batch_log_probabilities[bidx].append(
                            LogProbabilities(token_log_probabilities=[float(1.0)], top_log_probabilities=[{int(t): float(1.0)}])
                        )
                else:
                    logprobs, top_k_values, top_k_indices = logsoftmax_topk(logits_for_sampling.to_numpy(), context_batch[bidx].log_probabilities)
                    top_log_prob = []
                    for i in range(context_batch[bidx].log_probabilities):
                        top_log_prob.append({int(top_k_indices[0, i]): float(top_k_values[0, i])})
                    batch_log_probabilities[bidx].append(
                        LogProbabilities(token_log_probabilities=[float(logprobs[0, updated_tokens[0]])], top_log_probabilities=top_log_prob)
                    )

            # ================
            # CLEANUP
            # ================
            if q:
                del mod_manager.forced_queues[rid]
            if not getattr(pipeline, "async_gen", False):
                if rewind_cache_n.get(rid):
                    del rewind_cache_n[rid]

        tokens_as_numpy = Tensor.from_numpy(
            np.zeros(
                (
                    curr_step_inputs.kv_cache_inputs.kv_cache_inputs[
                        0
                    ].cache_lengths.shape[0],
                ),
                dtype=np.uint32,
            )
        )
        tokens_as_numpy.inplace_copy_from(
            curr_step_inputs.kv_cache_inputs.kv_cache_inputs[0].cache_lengths
        )
        tokens_as_numpy = tokens_as_numpy.to_numpy()
        offsets_as_numpy = Tensor.from_numpy(
            np.zeros((curr_step_inputs.input_row_offsets.shape[0],), dtype=np.uint32)
        )
        offsets_as_numpy.inplace_copy_from(curr_step_inputs.input_row_offsets)
        offsets_as_numpy = offsets_as_numpy.to_numpy()
        emit_step_events(
            step=pipeline.get_step_for_request(rid),
            request_id_order=request_id_order,
            done_requests=batch_state.get_done_request_ids(),
            next_step_tokens=tokens_as_numpy,
            next_step_row_offsets=offsets_as_numpy,
            raw_logits_rows=raw_logits_rows,
            batch_index_by_request=batch_index_by_request,
            req_top_k={rid: batch_state[rid].top_k for rid in request_id_order},
            req_top_p={rid: batch_state[rid].top_p for rid in request_id_order},
            req_temperature={rid: batch_state[rid].temperature for rid in request_id_order},
            adjusted_logits=bool(step_adjusted),
            req_accumulators={rid: batch_state[rid].accumulator for rid in request_id_order},
            tokenizer=getattr(pipeline, "tokenizer", None),
            forced_origin=None,
            step_ts=int(time.time()),
        )

        # Reset skip flags for next iteration
        for rid in list(skip_step_progress.keys()):
            skip_step_progress[rid] = False

        # Per-request backtrack is applied immediately via _backtrack_request; no batch-wide fallback here.
        # If all requests are done, terminate now (avoid extra compute).
        if batch_state.all_done():
            has_pending_forced = False
            if mod_manager:
                for rid in request_id_order:
                    if has_pending_forced:
                        break
                    if batch_state[rid].is_done:
                        continue
                    has_pending_forced = len(mod_manager.forced_queues.get(rid, [])) > 0
            if not has_pending_forced:
                if compute_log_probabilities:
                    batch_log_probabilities.append(None)
                break


        if i == num_steps - 1:
            break

    # ==========================================================================
    # Phase 4: Finalization - Build outputs and apply terminal overrides
    # ==========================================================================
    mod_manager.forced_queues = {}
    # Access delayed_backtrack to ensure it exists (side effect)
    _ = mod_manager.delayed_backtrack
    setattr(pipeline, "mod_manager", mod_manager)

    generated_tokens_host = generated_tokens.copy(driver.CPU()).to_numpy()
    executed_steps = generated_tokens_host.shape[1]
    if executed_steps > 1:
        pipeline._pipeline_model.kv_manager.fetch(batch.values(), executed_steps - 1)

    res = {}
    for request_id, context in batch.items():
        request_state = batch_state[request_id]
        was_prompt_prefill = context._start_idx == 0
        new_start = context.end_idx
        out = _finalize_output_for_request(
            pipeline=pipeline,
            request_state=request_state,
            context=context,
            executed_steps=executed_steps,
            generated_tokens_host=generated_tokens_host,
            compute_log_probabilities=compute_log_probabilities,
            batch_log_probabilities=batch_log_probabilities[request_state.batch_index],
            placeholder_token_id=PLACEHOLDER_TOKEN_ID,
        )
        if len(out.tokens) != 0:
            context._start_idx = new_start

        res[request_id] = out

        # Defer final stats/output calculation to server layer (has full request context).
        accumulator = request_state.accumulator
        if accumulator is not None:
            try:
                snapshot_dir = getattr(pipeline, "logs_snapshot_dir", None) or "inference/src/quote/logs/tmp"
                accumulator.snapshot_to_file(f"{snapshot_dir}/{request_id}.json")
            except Exception:
                pass

        if getattr(pipeline, "async_gen", False):
            if mod_manager.delayed_panic.get(request_id):
                out.final_status = GenerationStatus.CANCELLED
                out.tokens = mod_manager.delayed_panic.get(request_id)
            if mod_manager.delayed_backtrack.get(request_id):
                out.tokens.insert(0, -1 * mod_manager.delayed_backtrack[request_id])
                if compute_log_probabilities:
                    out.log_probabilities.insert(0, LogProbabilities(token_log_probabilities=[], top_log_probabilities=[]))
                del mod_manager.delayed_backtrack[request_id]
            if rewind_cache_n.get(request_id):
                if context.needs_ce:
                    mod_manager.delayed_backtrack[request_id] = rewind_cache_n[request_id]
                else:
                    out.tokens.insert(0, -1 * rewind_cache_n[request_id])
                    if compute_log_probabilities:
                        out.log_probabilities.insert(0, LogProbabilities(token_log_probabilities=[], top_log_probabilities=[]))
            if request_state.terminal_force_output is not None:
                out.final_status = GenerationStatus.END_OF_SEQUENCE
                out.tokens.insert(0, -1 * new_start)
            if request_state.terminal_tool_call is not None:
                out.final_status = GenerationStatus.END_OF_SEQUENCE
                out.tokens.insert(0, -1 * new_start)
            if request_state.terminal_error is not None:
                logger.debug("Terminal error for request %s (was_prompt_prefill=%s)", request_id, was_prompt_prefill)
                context._start_idx += 1
                out.final_status = GenerationStatus.CANCELLED
                out.tokens = [_ERROR_TOKEN_MARKER]
                err_str = request_state.terminal_error or "Unknown error"
                out.tokens.extend(pipeline.tokenizer.encode(err_str, add_special_tokens=False))
        if accumulator is not None:
            request_completed = False
            try:
                status = getattr(out, "final_status", None)
                if status is not None and getattr(status, "is_done", False):
                    request_completed = True
            except Exception:
                pass
            try:
                if getattr(context, "is_done", False):
                    request_completed = True
            except Exception:
                pass
            if request_state.is_done:
                request_completed = True
            # Finalization handled at server layer to include full response context.
    try:
        pipeline._pipeline_model.kv_manager.step(context_batch)
    except Exception as e:
        logger.warning("Error stepping KV manager (possibly block.block_hash is None): %s", e)
    return res


def rewind_cache(pipeline: TextGenerationPipeline, ctx: TextContext, n: int):
    """Remove the last n tokens for this request from the KV mapping.

    This updates:
      - current_blocks_per_request[request_id] (freeing trailing blocks)
      - req_to_committed_idx[request_id] (clamped to new full-block boundary)
      - req_to_hashes[request_id] (truncated to new number of full blocks)
      - ctx token indices (end_idx/active_idx/start_idx clamped to new end)
    """

    mngr = pipeline._pipeline_model.kv_manager
    blk_mngr: BlockManager = getattr(mngr, "block_manager")
    if blk_mngr:
        if n <= 0:
            return
        request_id = ctx.request_id
        old_len = ctx.current_length
        n = min(n, old_len)
        new_len = old_len - n

        from max.support.math import ceildiv

        # Trim the per-request block list to the newly required number of blocks.
        needed_blocks = 0 if new_len == 0 else ceildiv(new_len, blk_mngr.block_size)
        req_blocks = blk_mngr.current_blocks_per_request[request_id]

        while len(req_blocks) > needed_blocks:
            block = req_blocks.pop()
            if block.block_hash is not None:
                blk_mngr.device_block_pool.uncommit_block(block)
            blk_mngr.device_block_pool.free_block(block)

        # Clamp the request's committed_idx to the nearest full block <= new_len.
        old_committed = blk_mngr.req_to_committed_idx[request_id]
        new_committed = min(
            old_committed, (new_len // blk_mngr.block_size) * blk_mngr.block_size
        )
        blk_mngr.req_to_committed_idx[request_id] = new_committed

        # Truncate per-request block hashes to the new number of full blocks.
        num_full_blocks = new_len // blk_mngr.block_size
        blk_mngr.req_to_hashes[request_id] = blk_mngr.req_to_hashes[request_id][
            :num_full_blocks
        ]

        # Update context indices so future fetch()/step() see the shorter sequence.
        new_end_idx = new_len
        new_start_idx = new_len - 1  # min(ctx.start_idx, new_end_idx)
        new_active_idx = new_len  # min(ctx.active_idx, new_end_idx)

        ctx.set_token_indices(
            start_idx=new_start_idx,
            active_idx=new_active_idx,
            end_idx=new_end_idx,
        )
        ctx._completion_start_idx = min(ctx._completion_start_idx, new_active_idx)
        ctx._completion_end_idx = new_active_idx
    else:
        return


def logsoftmax_topk(logits: np.ndarray, k: int):
    """
    logits: shape (B, V) — e.g. (1, 128000)
    returns:
      logprobs: (B, V)
      topk_logprobs: (B, k)
      topk_indices: (B, k)
    """
    # 1) log-softmax (stable)
    m = np.max(logits, axis=1, keepdims=True)
    y = logits - m
    lse = m + np.log(np.sum(np.exp(y), axis=1, keepdims=True))
    logprobs = logits - lse

    # 2) top-k along vocabulary axis
    idx_part = np.argpartition(logprobs, -k, axis=1)[:, -k:]
    vals_part = np.take_along_axis(logprobs, idx_part, axis=1)
    order = np.argsort(vals_part, axis=1)[:, ::-1]           # sort desc
    topk_indices = np.take_along_axis(idx_part, order, axis=1)
    topk_logprobs = np.take_along_axis(vals_part, order, axis=1)

    return logprobs, topk_logprobs, topk_indices
