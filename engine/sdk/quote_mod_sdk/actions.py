from __future__ import annotations

from typing import Any, Iterable, Optional

from shared.types import (  # type: ignore[attr-defined]
    Added,
    AdjustedLogits,
    AdjustedPrefill,
    Backtrack,
    ForceOutput,
    ForceTokens,
    ForwardPass,
    ModAction,
    ModEvent,
    Noop,
    Prefilled,
    Sampled,
    ToolCalls,
    EmitError
)

from shared.utils import InvalidActionError

class ActionBuilder:
    """Factory surfaced to mod authors with event-scoped helpers."""

    def __init__(self, event: ModEvent) -> None:
        self._event = event

    # --- Common helpers -------------------------------------------------
    def noop(self) -> ModAction:
        return Noop()

    def force_output(self, tokens: Iterable[int]) -> ModAction:
        self._require_event({Prefilled, ForwardPass, Sampled, Added}, "force_output")
        return ForceOutput([int(t) for t in tokens])

    def tool_calls(self, payload: Any) -> ModAction:
        self._require_event({Prefilled, ForwardPass, Sampled, Added}, "tool_calls")
        return ToolCalls(payload)

    def emit_error(self, err_str: str) -> ModAction:
        return EmitError(err_str)

    # --- Prefilled-only -------------------------------------------------
    def adjust_prefill(
        self, tokens: Iterable[int], *, max_steps: Optional[int] = None
    ) -> ModAction:
        self._require_event({Prefilled}, "adjust_prefill")
        resolved = [int(t) for t in tokens]
        ms = int(max_steps) if max_steps is not None else 0
        return AdjustedPrefill(resolved, ms)

    # --- ForwardPass ----------------------------------------------------
    def adjust_logits(
        self, logits: Optional[Any] = None, token_temp: Optional[float] = None
    ) -> ModAction:

        self._require_event({ForwardPass}, "adjust_logits")
        if logits is None:
            logits = getattr(self._event, "logits", None)
        if logits is None:
            raise InvalidActionError(
                "adjust_logits requires logits when event has none"
            )
        return AdjustedLogits(logits, token_temp)

    def force_tokens(self, tokens: Iterable[int]) -> ModAction:
        self._require_event({ForwardPass, Sampled, Added}, "force_tokens")
        return ForceTokens([int(t) for t in tokens])

    def backtrack(
        self, steps: int, tokens: Optional[Iterable[int]] = None
    ) -> ModAction:
        self._require_event({ForwardPass, Sampled, Added}, "backtrack")
        queue = [int(t) for t in tokens] if tokens is not None else None
        return Backtrack(int(steps), queue)

    # --- Internal -------------------------------------------------------
    def _require_event(self, allowed: set[type[ModEvent]], method: str) -> None:
        if not any(isinstance(self._event, ev) for ev in allowed):
            raise InvalidActionError(
                f"Action '{method}' not permitted for event type {type(self._event).__name__}"
            )


def for_event(event: ModEvent) -> ActionBuilder:
    """Return an action builder bound to the given event."""
    return ActionBuilder(event)


__all__ = ["ActionBuilder", "InvalidActionError", "for_event"]
