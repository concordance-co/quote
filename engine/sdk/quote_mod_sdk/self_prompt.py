from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set
from enum import Enum

import numpy as np
from shared.types import Added, ForwardPass, ModEvent, Prefilled

from .actions import ActionBuilder
from .mod import ModCallable, mod
from .strategies.strategy_constructor import (
    StrategyConstructor,
    ListStrat,
    ChoicesStrat,
)
from shared.types import ForceTokens
from shared.types import Backtrack


class EraseMode(Enum):
    NONE = "none"
    PROMPT = "prompt"
    ALL = "all"


# Maximum number of strategy-requested backtracks per SelfPrompt instance.
_MAX_STRATEGY_BACKTRACK_ATTEMPTS = 3


@dataclass
class _State:
    compiled: Any | None = None
    strat_state: Any | None = None
    prompt_tokens: List[int] = field(default_factory=list)
    prompt_emitted: bool = False
    outstanding_forced: int = 0
    completed: bool = False
    # Answer accounting (includes strategy output and any forced completion suffix tokens)
    answer_tokens: List[int] = field(default_factory=list)
    # Completion suffix handling
    suffix_tokens: List[int] = field(default_factory=list)
    suffix_pending: bool = False
    # Backtrack scheduling
    backtrack_n: int = 0
    backtrack_reinject: Optional[List[int]] = None
    backtrack_scheduled: bool = False
    # Guard against unbounded strategy-driven backtracks
    strategy_backtrack_attempts: int = 0


def _tokenize_optional(text: Optional[str], tokenizer: Any) -> List[int]:
    if not text:
        return []
    ids = tokenizer.encode(text, add_special_tokens=False)
    if not isinstance(ids, list):
        ids = list(ids)
    return [int(t) for t in ids]


def _mask_disallowed_logits_like(logits, disallowed: Set[int], mask_value: float):
    if not disallowed:
        return logits
    to_numpy = getattr(logits, "to_numpy", None)
    if callable(to_numpy):
        try:
            arr = to_numpy()
        except Exception:
            arr = None
        if arr is not None:
            np_arr = np.asarray(arr)
            if np_arr.ndim >= 1:
                work = np.array(np_arr, copy=True)
                vocab = work.shape[-1]
                if vocab > 0:
                    mask = np.zeros(vocab, dtype=bool)
                    in_range = False
                    for tok in disallowed:
                        if 0 <= tok < vocab:
                            mask[int(tok)] = True
                            in_range = True
                    if not in_range:
                        return logits
                    work[..., mask] = float(mask_value)
                    tensor_cls = type(logits)
                    from_numpy = getattr(tensor_cls, "from_numpy", None)
                    if callable(from_numpy):
                        try:
                            new_tensor = from_numpy(np.asarray(work, dtype=work.dtype))
                            move = getattr(new_tensor, "to", None)
                            device = getattr(logits, "device", None)
                            if callable(move) and device is not None:
                                try:
                                    new_tensor = move(device)
                                except Exception:
                                    pass
                            return new_tensor
                        except Exception:
                            pass
                    copy_ = getattr(logits, "copy_", None)
                    if callable(copy_):
                        try:
                            copy_(np.asarray(work, dtype=work.dtype))
                            return logits
                        except Exception:
                            pass
    return logits


def _mask_logits_like(
    logits, allowed: Set[int], disallowed: Set[int], mask_value: float
):
    if not allowed:
        return logits
    to_numpy = getattr(logits, "to_numpy", None)
    if callable(to_numpy):
        try:
            arr = to_numpy()
        except Exception:
            arr = None
        if arr is not None:
            np_arr = np.asarray(arr)
            if np_arr.ndim >= 1:
                work = np.array(np_arr, copy=True)
                vocab = work.shape[-1]
                if vocab > 0:
                    mask = np.ones(vocab, dtype=bool)
                    in_range = False
                    for tok in allowed:
                        if 0 <= tok < vocab:
                            mask[int(tok)] = False
                            in_range = True
                    for tok in disallowed:
                        if 0 <= tok < vocab:
                            mask[int(tok)] = True
                            in_range = True
                    if not in_range:
                        return logits
                    work[..., mask] = float(mask_value)
                    tensor_cls = type(logits)
                    from_numpy = getattr(tensor_cls, "from_numpy", None)
                    if callable(from_numpy):
                        try:
                            new_tensor = from_numpy(np.asarray(work, dtype=work.dtype))
                            move = getattr(new_tensor, "to", None)
                            device = getattr(logits, "device", None)
                            if callable(move) and device is not None:
                                try:
                                    new_tensor = move(device)
                                except Exception:
                                    pass
                            return new_tensor
                        except Exception:
                            pass
                    copy_ = getattr(logits, "copy_", None)
                    if callable(copy_):
                        try:
                            copy_(np.asarray(work, dtype=work.dtype))
                            return logits
                        except Exception:
                            pass
    return logits


class SelfPrompt:
    """Self-prompt controller using the new strategy engine.

    Instantiate and call handle_prefilled/handle_forward_pass/handle_added from your mod.
    """

    def __init__(
        self,
        *,
        prompt: Optional[Dict[str, Any]] = None,
        strategy: StrategyConstructor,
        completion: Optional[str] = None,
        erase: EraseMode = EraseMode.NONE,
        argmax_sampling: bool = False,
        mask_value: float = -1e9,
    ) -> None:
        self._prompt_cfg = dict(prompt or {})
        self._strategy_spec = strategy
        self._completion_cfg = completion
        self._erase_cfg = erase
        self._mask_value = float(mask_value)
        self._argmax = argmax_sampling

        self._states: Dict[str, _State] = {}

        # Detect list.end_with to avoid double suffix
        self._strategy_has_end_with = isinstance(strategy, ListStrat) and bool(
            strategy.end_with
        )

    # ----------------------------- helpers -----------------------------
    def _resolve_prompt(self, tokenizer: Any | None, st: _State) -> List[int]:
        ptoks = (
            self._prompt_cfg.get("tokens")
            if isinstance(self._prompt_cfg, dict)
            else None
        )
        ptext = (
            self._prompt_cfg.get("text") if isinstance(self._prompt_cfg, dict) else None
        )
        if isinstance(ptoks, list):
            return [int(t) for t in ptoks]
        if isinstance(ptext, str) and ptext:
            if tokenizer is None:
                raise RuntimeError("SelfPrompt requires tokenizer for prompt.text")
            return _tokenize_optional(ptext, tokenizer)
        return []

    def _resolve_completion_suffix(self, tokenizer: Any | None) -> List[int]:
        suffix = self._completion_cfg
        if isinstance(suffix, str) and suffix:
            if tokenizer is None:
                raise RuntimeError("SelfPrompt requires tokenizer for completion.suffix")
            return _tokenize_optional(suffix, tokenizer)
        return []

    def _completion_force(self) -> bool:
        cfg = self._completion_cfg
        if isinstance(cfg, dict) and cfg:
            return bool(cfg.get("force", True))
        if cfg is None:
            return True
        return True

    def is_complete(self, request_id: str) -> bool:
        st = self._states.setdefault(request_id, _State())
        return st.completed

    def answer_tokens(self, request_id: str) -> Optional[list[int]]:
        st = self._states.setdefault(request_id, _State())
        if self.is_complete(request_id):
            return st.answer_tokens
        else:
            return None


    # ----------------------------- dynamic -----------------------------
    def refresh_responses(
        self,
        responses: Optional[Sequence[str]],
        request_id: Optional[str] = None,
        idx=None,
    ) -> None:
        """Update choices for this prompt when the strategy is a choices list (or list->element choices).

        If request_id is provided, clears compiled state for that request so it recompiles on next event.
        """
        values = list(responses) if responses is not None else []
        spec = self._strategy_spec

        if not isinstance(spec, (ListStrat, ChoicesStrat)):
            return

        updated = False
        if isinstance(spec, ChoicesStrat):
            spec.choices = [str(v) for v in values]
            updated = True
        if isinstance(spec, ListStrat):
            if isinstance(spec.elements[idx], ChoicesStrat):
                spec.elements[idx].choices = [str(v) for v in values]
                updated = True
        if updated and isinstance(request_id, str):
            self._states.pop(request_id, None)

    # ----------------------------- handlers ----------------------------
    def handle_prefilled(self, event: Prefilled, tokenizer: Any | None) -> None:
        rid = getattr(event, "request_id", None)
        if not isinstance(rid, str):
            return
        st = self._states.setdefault(rid, _State())
        if st.compiled is None and tokenizer is not None:
            st.compiled = self._strategy_spec.into_strategy(tokenizer)
            st.strat_state = st.compiled.start(tokenizer)
            st.prompt_tokens = self._resolve_prompt(tokenizer, st)
            st.prompt_emitted = False
            st.outstanding_forced = 0
            st.completed = False
            st.answer_tokens = []
            st.suffix_tokens = []
            st.suffix_pending = False
            st.backtrack_n = 0
            st.backtrack_reinject = None
            st.backtrack_scheduled = False
            st.strategy_backtrack_attempts = 0

    def handle_forward_pass(
        self, event: ForwardPass, actions: ActionBuilder, tokenizer: Any | None
    ):
        rid = getattr(event, "request_id", None)
        if not isinstance(rid, str):
            return actions.noop()
        st = self._states.setdefault(rid, _State())

        # Compile on demand
        if st.compiled is None:
            if tokenizer is None:
                return actions.noop()
            st.compiled = self._strategy_spec.into_strategy(tokenizer)
            st.strat_state = st.compiled.start(tokenizer)
            st.prompt_tokens = self._resolve_prompt(tokenizer, st)
            st.prompt_emitted = False
            st.outstanding_forced = 0
            st.completed = False
            st.answer_tokens = []
            st.suffix_tokens = []
            st.suffix_pending = False
            st.backtrack_n = 0
            st.backtrack_reinject = None
            st.backtrack_scheduled = False
            st.strategy_backtrack_attempts = 0

        # Backtrack emission
        if st.backtrack_scheduled and st.backtrack_n > 0:
            n = st.backtrack_n
            reinject = st.backtrack_reinject
            st.backtrack_n = 0
            st.backtrack_reinject = None
            st.backtrack_scheduled = False
            st.completed = True
            return actions.backtrack(n, reinject)

        # Force prompt
        if not st.prompt_emitted:
            st.prompt_emitted = True
            if st.prompt_tokens:
                st.outstanding_forced = len(st.prompt_tokens)
                return actions.force_tokens(st.prompt_tokens)

        if st.outstanding_forced > 0:
            return actions.noop()

        # Force completion suffix if pending
        if st.suffix_pending:
            st.suffix_pending = False
            if st.suffix_tokens:
                st.outstanding_forced = len(st.suffix_tokens)
                return actions.force_tokens(st.suffix_tokens)

        # Completed => schedule/emit erase backtrack if configured; otherwise no masking
        if st.strat_state is not None and st.compiled.is_complete(st.strat_state):
            if not st.completed:
                if self._erase_cfg != EraseMode.NONE:
                    total = (
                        len(st.prompt_tokens)
                        + len(st.answer_tokens)
                        + len(st.suffix_tokens)
                    )
                    reinject = (
                        list(st.answer_tokens)
                        if self._erase_cfg == EraseMode.PROMPT
                        else None
                    )
                    st.completed = True
                    st.answer_tokens = tokenizer.encode(st.compiled.trim_answer(tokenizer.decode(st.answer_tokens)), add_special_tokens=False)
                    return actions.backtrack(total, reinject)
                st.completed = True
            st.answer_tokens = tokenizer.encode(st.compiled.trim_answer(tokenizer.decode(st.answer_tokens)), add_special_tokens=False)
            return actions.noop()

        # Allowed set

        if tokenizer is None:
            return actions.noop()
        allowed = st.compiled.allowed_tokens(st.strat_state, tokenizer)
        disallowed = st.compiled.disallowed_tokens(st.strat_state, tokenizer)
        if not allowed and not disallowed:
            return actions.noop()

        if not allowed:
            adjusted = _mask_disallowed_logits_like(
                event.logits, set(disallowed), self._mask_value
            )
        else:
            adjusted = _mask_logits_like(
                event.logits, set(allowed), set(disallowed), self._mask_value
            )

        if self._argmax:
            return actions.adjust_logits(adjusted, token_temp=0.0)
        else:
            return actions.adjust_logits(adjusted)

    def handle_added(self, event: Added, actions: ActionBuilder, tokenizer: Any | None):
        rid = getattr(event, "request_id", None)
        if not isinstance(rid, str):
            return None
        st = self._states.setdefault(rid, _State())

        # Consume forced tokens
        if st.outstanding_forced > 0 and getattr(event, "forced", False):
            st.outstanding_forced = max(
                0, st.outstanding_forced - len(event.added_tokens or [])
            )
            return None

        if st.compiled is None or st.strat_state is None or tokenizer is None:
            return None


        to_add: List[int] = []
        num_to_backtrack = 0
        for t in event.added_tokens or []:
            tid = int(t)
            maybe_action = st.compiled.step(st.strat_state, tid, tokenizer)
            if maybe_action:
                if isinstance(maybe_action, ForceTokens):
                    to_add.extend(maybe_action.tokens)
                if isinstance(maybe_action, Backtrack):
                    num_to_backtrack += maybe_action.n
                    to_add.extend(maybe_action.tokens)
            if not getattr(event, "forced", False) and not st.completed:
                st.answer_tokens.append(tid)

        # Completion bookkeeping
        if st.compiled.is_complete(st.strat_state) and not st.completed:
            # Apply suffix if configured and not handled by strategy
            print("completion text check", not self._strategy_has_end_with, self._completion_force())
            if not self._strategy_has_end_with and self._completion_force() and self._erase_cfg != EraseMode.ALL:
                st.suffix_tokens = self._resolve_completion_suffix(tokenizer)
                print("suffix tokens", st.suffix_tokens)
                if st.suffix_tokens:
                    st.suffix_pending = True
                    return None

            # Schedule erase
            if self._erase_cfg != EraseMode.NONE:
                total = len(st.prompt_tokens) + len(st.answer_tokens)
                st.backtrack_n = total
                if self._erase_cfg == EraseMode.PROMPT:
                    st.backtrack_reinject = list(st.answer_tokens)
                else:
                    st.backtrack_reinject = None
                st.backtrack_scheduled = True
            else:
                st.completed = True
            st.answer_tokens = tokenizer.encode(st.compiled.trim_answer(tokenizer.decode(st.answer_tokens)), add_special_tokens=False)

        if num_to_backtrack > 0:
            # Enforce a simple cap on strategy-driven backtracks to avoid infinite loops.
            st.strategy_backtrack_attempts += 1
            if st.strategy_backtrack_attempts > _MAX_STRATEGY_BACKTRACK_ATTEMPTS:
                return None
            return Backtrack(num_to_backtrack, to_add)
        elif len(to_add) > 0:
            return ForceTokens(to_add)

        return None


def self_prompt_mod(
    *,
    prompt: Optional[Dict[str, Any]] = None,
    strategy: StrategyConstructor,
    completion: Optional[Dict[str, Any]] = None,
    erase: EraseMode = EraseMode.NONE,
    mask_value: float = -1e9,
) -> ModCallable:
    """Self-prompting mod backed by the new strategies engine.

    Args:
        prompt: { text?: str, tokens?: list[int] }
        strategy: StrategyConstructor
        completion: { suffix?: str|list[int], force?: bool=true }
        erase: { mode?: EraseMode.NONE|EraseMode.PROMPT|EraseMode.ALL }
        mask_value: Logit value to apply to disallowed tokens
    """

    erase_mode = SelfPrompt(
        prompt=prompt,
        strategy=strategy,
        completion=completion,
        erase=erase,
        mask_value=mask_value,
    )

    # Normalize completion config
    comp_suffix_text: Optional[str] = None
    comp_suffix_tokens: Optional[List[int]] = None
    comp_force: bool = True
    if isinstance(completion, dict) and completion:
        comp_force = bool(completion.get("force", True))
        suffix = completion.get("suffix")
        if isinstance(suffix, list):
            comp_suffix_tokens = [int(t) for t in suffix]
        elif isinstance(suffix, str):
            comp_suffix_text = suffix
    elif completion is None:
        comp_force = True
        comp_suffix_text = "\n"

    # Spec signal: if list has end_with, we will not apply completion suffix
    _strategy_has_end_with = False
    if isinstance(strategy, dict) and (strategy.get("type", "").lower() == "list"):
        _strategy_has_end_with = bool(strategy.get("end_with"))

    # Prompt normalize
    prompt_text: Optional[str] = None
    prompt_tokens: Optional[List[int]] = None
    if isinstance(prompt, dict) and prompt:
        prompt_text = prompt.get("text")
        pt = prompt.get("tokens")
        if isinstance(pt, list):
            prompt_tokens = [int(t) for t in pt]

    @mod
    def _handler(event, actions: ActionBuilder, tokenizer: Any | None):
        sp = erase_mode  # misnomer variable now holds the SelfPrompt instance
        if isinstance(event, Prefilled):
            sp.handle_prefilled(event, tokenizer)
            return actions.noop()
        if isinstance(event, ForwardPass):
            return sp.handle_forward_pass(event, actions, tokenizer)
        if isinstance(event, Added):
            act = sp.handle_added(event, actions, tokenizer)
            # Strategy may request Backtrack or ForceTokens during Added
            return act or actions.noop()
        return actions.noop()

    return _handler


__all__ = ["SelfPrompt", "self_prompt_mod"]
