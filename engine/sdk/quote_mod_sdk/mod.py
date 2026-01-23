from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Tuple, Type


from shared.types import (  # type: ignore[attr-defined]
    Added,
    AdjustedLogits,
    AdjustedPrefill,
    Backtrack,
    ForceOutput,
    ForceTokens,
    ForwardPass,
    EmitError,
    ModAction,
    ModEvent,
    Noop,
    Prefilled,
    Sampled,
    ToolCalls,
)

from shared.utils import InvalidActionError, validate_action

from .actions import ActionBuilder, for_event

ModCallable = Callable[[ModEvent, Any | None], ModAction]
_Handler = Callable[[ModEvent, ActionBuilder, Any | None], ModAction | None]


def create_mod(handler: _Handler) -> ModCallable:
    def _mod(event: ModEvent, tokenizer: Any | None = None) -> ModAction:
        builder = for_event(event)
        result = handler(event, builder, tokenizer)
        return validate_action(event, result)

    return _mod


def mod(handler: _Handler) -> ModCallable:
    @wraps(handler)
    def _wrapped(event: ModEvent, tokenizer: Any | None = None) -> ModAction:
        builder = for_event(event)
        try:
            result = handler(event, builder, tokenizer)
        except TypeError:
            result = handler(event, builder)
        return validate_action(event, result)

    return _wrapped


__all__ = ["ModCallable", "create_mod", "mod", "validate_action", "InvalidActionError"]
