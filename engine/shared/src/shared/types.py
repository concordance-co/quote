from __future__ import annotations

from typing import Any, List, Optional

from max.driver import Tensor


class ModEvent:
    """Base class for mod events."""


class Prefilled(ModEvent):
    def __init__(
        self,
        request_id: str,
        step: int,
        max_steps: int,
        context_info: Optional[dict] = None,
    ) -> None:
        self.request_id = request_id
        self.step = step
        self.max_steps = max_steps
        self.context_info = context_info or {}


class ForwardPass(ModEvent):
    def __init__(
        self,
        request_id: str,
        step: int,
        logits: Tensor,
    ) -> None:
        self.request_id = request_id
        self.step = step
        self.logits = logits

    def top_k_logprob(self, k):
        import numpy as np
        logits = self.logits.to_numpy()
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
        return topk_logprobs, topk_indices



class Sampled(ModEvent):
    def __init__(
        self, request_id: str, step: int, sampled_token: int
    ) -> None:
        self.request_id = request_id
        self.step = step
        self.sampled_token = sampled_token


class Added(ModEvent):
    def __init__(
        self,
        request_id: str,
        step: int,
        added_tokens: List[int],
        forced: bool,
    ) -> None:
        self.request_id = request_id
        self.step = step
        self.added_tokens = list(added_tokens)
        self.forced = forced


class ModAction:
    """Base class for mod actions."""


class Noop(ModAction):
    """Action representing no changes."""


class AdjustedPrefill(ModAction):
    def __init__(self, tokens: List[int], max_steps: int) -> None:
        self.tokens = list(tokens)
        self.max_steps = max_steps


class ForceTokens(ModAction):
    def __init__(self, tokens: List[int]) -> None:
        self.tokens = list(tokens)

class EmitError(ModAction):
    def __init__(self, err_str: str) -> None:
        self.err_str = err_str


class AdjustedLogits(ModAction):
    def __init__(self, logits: Tensor, token_temp: Optional[float] = None) -> None:
        self.logits = logits
        self.token_temp = token_temp

    def top_k_logprob(self, k):
        import numpy as np
        logits = self.logits.to_numpy()
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
        return topk_logprobs, topk_indices

class ForceOutput(ModAction):
    def __init__(self, tokens: List[int]) -> None:
        self.tokens = list(tokens)


class ToolCalls(ModAction):
    def __init__(self, tool_calls: Any) -> None:
        self.tool_calls = tool_calls


class Backtrack(ModAction):
    def __init__(self, n: int, tokens: Optional[List[int]] | None = None) -> None:
        self.n = int(n)
        self.tokens = list(tokens) if tokens is not None else None


__all__ = [
    "ModEvent",
    "Prefilled",
    "ForwardPass",
    "Sampled",
    "Added",
    "ModAction",
    "Noop",
    "AdjustedPrefill",
    "ForceTokens",
    "AdjustedLogits",
    "ForceOutput",
    "ToolCalls",
    "Backtrack",
]
