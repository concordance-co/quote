from .types import (
    ModAction,
    ModEvent,
    Noop,
    Prefilled,
    ForceOutput,
    ToolCalls,
    AdjustedPrefill,
    AdjustedLogits,
    ForwardPass,
    Sampled,
    ForceTokens,
    Backtrack,
    EmitError,
    Added,
)


_ALLOWED_ACTIONS: dict[type[ModEvent], tuple[type[ModAction], ...]] = {
    Prefilled: (Noop, ForceOutput, ToolCalls, AdjustedPrefill, EmitError),
    ForwardPass: (Noop, ForceTokens, Backtrack, ForceOutput, ToolCalls, AdjustedLogits, EmitError),
    Sampled: (Noop, ForceTokens, Backtrack, ForceOutput, ToolCalls, EmitError),
    Added: (Noop, ForceTokens, Backtrack, ForceOutput, ToolCalls, EmitError),
}


class InvalidActionError(ValueError):
    """Raised when an action is not permitted for the current event."""


def validate_action(event: ModEvent, action: ModAction | None) -> ModAction:
    if action is None:
        return Noop()
    allowed = _ALLOWED_ACTIONS.get(type(event))
    if allowed is None:
        raise InvalidActionError(f"Unsupported event type {type(event).__name__}")
    if not isinstance(action, tuple(allowed)):
        raise InvalidActionError(
            f"Action {type(action).__name__} not permitted for event {type(event).__name__}"
        )
    return action
