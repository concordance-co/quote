from typing import Any, Callable, Dict, List, Optional

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
    Noop,
    Prefilled,
    Sampled,
    ToolCalls,
)
from shared.conversation import (
    push_request_context,
    pop_request_context,
    append_debug_logs,
    append_trace_mod_call,
    append_trace_mod_log,
    append_trace_action,
)

# --- In-process Mod System (Phase 1) ---


import io
import contextlib

class ModManager:
    def __init__(
        self,
        mods: Optional[List[Callable[[ModEvent, Any | None], ModAction]]] = None,
        *,
        tokenizer: Any | None = None,
    ) -> None:
        self.mods: List[Callable[[ModEvent, Any | None], ModAction]] = mods or []
        # Per-request forced tokens queue
        self.forced_queues: Dict[str, List[int]] = {}
        # Parallel reasons for forced tokens (same length alignment per request)
        self.forced_reason_queues: Dict[str, List[str]] = {}
        self._tokenizer: Any | None = tokenizer
        self.delayed_backtrack: Dict[str, int] = {}
        self.delayed_panic: Dict[str, List[int]] = {}

    def register(self, mod: Callable[[ModEvent, Any | None], ModAction]) -> None:
        self.mods.append(mod)

    def set_tokenizer(self, tokenizer: Any | None) -> None:
        self._tokenizer = tokenizer

    def dispatch(self, event: ModEvent) -> List[ModAction]:
        actions: List[ModAction] = []
        tokenizer = self._tokenizer
        request_id = getattr(event, "request_id", None)
        event_type = type(event).__name__
        step = getattr(event, "step", 0)

        all_logs = io.StringIO()

        for mod in self.mods:
            mod_name = type(mod).__name__
            if hasattr(mod, "__name__"):
                mod_name = mod.__name__
            elif hasattr(mod, "__class__"):
                mod_name = mod.__class__.__name__

            # Capture stdout for this specific mod
            mod_buffer = io.StringIO()

            with contextlib.redirect_stdout(mod_buffer):
                try:
                    token = None
                    if isinstance(request_id, str):
                        token = push_request_context(request_id)
                        # Record mod call in trace
                        append_trace_mod_call(request_id, mod_name, event_type, step)
                    try:
                        action = mod(event, tokenizer)
                    finally:
                        if token is not None:
                            pop_request_context(token)
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    print(f"[mods] Mod raised exception on {type(event).__name__}: {e}")
                    action = Noop()

            # Capture mod logs
            mod_logs = mod_buffer.getvalue()
            if mod_logs and isinstance(request_id, str):
                # Keep raw logs without escaping - formatting will handle display
                append_trace_mod_log(request_id, mod_name, mod_logs)
            all_logs.write(mod_logs)

            if action is None:
                action = Noop()
            # Best-effort source attribution for logging
            try:
                setattr(action, "_source", mod_name)
                # Attach captured logs to action for accumulator ingest
                if mod_logs:
                    setattr(action, "_mod_logs", mod_logs)
            except Exception:
                pass

            # Record action in trace
            if isinstance(request_id, str) and action.__class__.__name__ != "Noop":
                action_details = {}
                if isinstance(action, AdjustedPrefill):
                    tokens = getattr(action, "tokens", [])
                    if tokens:
                        action_details["new_length"] = len(tokens)
                    max_steps = getattr(action, "max_steps", None)
                    if max_steps:
                        action_details["max_steps"] = max_steps
                elif isinstance(action, ForceTokens):
                    tokens = getattr(action, "tokens", [])
                    if tokens:
                        action_details["tokens_preview"] = str(tokens[:10])
                        action_details["token_count"] = len(tokens)
                elif isinstance(action, ForceOutput):
                    tokens = getattr(action, "tokens", [])
                    if tokens:
                        action_details["tokens_preview"] = str(tokens[:10])
                        action_details["token_count"] = len(tokens)
                elif isinstance(action, Backtrack):
                    action_details["n"] = getattr(action, "n", 0)
                    tokens = getattr(action, "tokens", None)
                    if tokens:
                        action_details["tokens_preview"] = str(tokens[:10])
                        action_details["token_count"] = len(tokens)
                elif isinstance(action, ToolCalls):
                    # Indicate tool calls are present
                    action_details["has_tool_calls"] = True
                elif isinstance(action, EmitError):
                    err_str = getattr(action, "err_str", "")
                    action_details["error"] = err_str[:100]  # Truncate long errors
                elif isinstance(action, AdjustedLogits):
                    logits = getattr(action, "logits", None)
                    if logits is not None and hasattr(logits, "shape"):
                        action_details["logits_shape"] = str(list(logits.shape))
                    token_temp = getattr(action, "token_temp", None)
                    if token_temp is not None:
                        action_details["temperature"] = token_temp

                append_trace_action(request_id, action.__class__.__name__, action_details)

            actions.append(action)

        all_logs_str = all_logs.getvalue()
        if isinstance(request_id, str):
            append_debug_logs(request_id, all_logs_str)
        return actions


__all__ = [
    "ModManager",
]
