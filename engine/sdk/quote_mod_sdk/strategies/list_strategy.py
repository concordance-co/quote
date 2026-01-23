from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Set, List

from .base import RuntimeState, Strategy
from shared.types import Backtrack, ForceTokens

@dataclass
class _ListState(RuntimeState):
    # Phases: in_open, await_element, in_wrap_open, in_element, in_wrap_close, await_sep, in_separator, in_close, in_end_with
    phase: str = "await_element"
    open_pos: int = 0
    wrap_pos: int = 0
    sep_pos: int = 0
    close_pos: int = 0
    end_with_pos: int = 0
    elements_completed: int = 0
    element_state: Optional[RuntimeState] = None
    # cached booleans
    _complete: bool = False


class ListStrategy(Strategy):
    def __init__(
        self,
        *,
        open_ids: List[int],
        close_ids: List[int],
        wrap_ids: List[int],
        sep_ids: List[int],
        end_with_ids: List[int],
        min_elements: int,
        max_elements: Optional[int],
        elements: Strategy | list[Strategy],
    ) -> None:
        self._open = list(open_ids or [])
        self._close = list(close_ids or [])
        self._wrap = list(wrap_ids or [])
        self._sep = list(sep_ids or [])
        self._end_with = list(end_with_ids or [])
        self._min = int(min_elements) if isinstance(min_elements, (int, float)) else 0
        self._max = int(max_elements) if isinstance(max_elements, (int, float)) else None
        self._elements = elements


    def start(self, tokenizer: Any) -> RuntimeState:
        state = _ListState()
        if self._open:
            state.phase = "in_open"
        else:
            state.phase = "await_element"
        state.element_state = None
        state.elements_completed = 0
        state.open_pos = state.wrap_pos = state.sep_pos = state.close_pos = state.end_with_pos = 0
        state._complete = False
        return state

    def is_complete(self, state: _ListState) -> bool:
        return state._complete

    def disallowed_tokens(self, state: _ListState, tokenizer: Any) -> Set[int]:
        return set()

    def allowed_tokens(self, state: _ListState, tokenizer: Any) -> Set[int]:
        allowed: Set[int] = set()
        # Helpers
        def allow_single(tok_id: Optional[int]):
            if tok_id is not None:
                allowed.add(int(tok_id))

        if state._complete:
            return set()

        ph = state.phase
        if ph == "in_open":
            if state.open_pos < len(self._open):
                allow_single(self._open[state.open_pos])
            return allowed

        if ph == "await_element":
            # Open a new element if under max
            under_max = self._max is None or state.elements_completed < self._max
            if under_max:
                if self._wrap:
                    allow_single(self._wrap[0])
                else:
                    # Delegate to element strategy's initial allowed tokens
                    if isinstance(self._elements, list):
                        elem_state = self._elements[state.elements_completed].start(tokenizer)
                        state.element_state = elem_state
                        allowed.update(self._elements[state.elements_completed].allowed_tokens(elem_state, tokenizer))
                    else:
                        elem_state = self._elements.start(tokenizer)
                        state.element_state = elem_state
                        allowed.update(self._elements.allowed_tokens(elem_state, tokenizer))
            # Or close if min satisfied
            if state.elements_completed >= self._min and self._close:
                allow_single(self._close[0])
            return allowed

        if ph == "in_wrap_open":
            if state.wrap_pos < len(self._wrap):
                allow_single(self._wrap[state.wrap_pos])
            return allowed

        if ph == "in_element":
            if state.element_state is None:
                state.element_state = self.start_element(state, tokenizer)

            # If element is complete and wrap exists, allow closing wrap
            completed = self.element_completed(state)
            if self._wrap and completed:
                allow_single(self._wrap[0])
            else:
                if isinstance(self._elements, list):
                    allowed.update(self._elements[state.elements_completed].allowed_tokens(state.element_state, tokenizer))
                else:
                    allowed.update(self._elements.allowed_tokens(state.element_state, tokenizer))
            return allowed

        if ph == "in_wrap_close":
            if state.wrap_pos < len(self._wrap):
                allow_single(self._wrap[state.wrap_pos])
            return allowed

        if ph == "await_sep":
            # allow separator if we can still add more elements
            if self._sep and (self._max is None or state.elements_completed < self._max):
                allow_single(self._sep[0])
            # or allow close if min satisfied
            if self._close and state.elements_completed >= self._min:
                allow_single(self._close[0])
            return allowed

        if ph == "in_separator":
            if state.sep_pos < len(self._sep):
                allow_single(self._sep[state.sep_pos])
            return allowed

        if ph == "in_close":
            if state.close_pos < len(self._close):
                allow_single(self._close[state.close_pos])
            else:
                # Close consumed, optionally emit end_with
                if self._end_with:
                    if state.end_with_pos < len(self._end_with):
                        allow_single(self._end_with[state.end_with_pos])
                else:
                    # If no end_with, complete silently; no constraints
                    pass
            return allowed

        if ph == "in_end_with":
            if state.end_with_pos < len(self._end_with):
                allow_single(self._end_with[state.end_with_pos])
            return allowed

        return allowed

    def start_element(self, state, tokenizer: Any):
        if isinstance(self._elements, Strategy):
            return self._elements.start(tokenizer)
        else:
            return self._elements[state.elements_completed].start(tokenizer)

    def element_completed(self, state: Any):
        if isinstance(self._elements, Strategy):
            return self._elements.is_complete(state.element_state)
        else:
            return self._elements[state.elements_completed].is_complete(state.element_state)

    def step(self, state: _ListState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:
        if state._complete:
            return
        ph = state.phase

        if ph == "in_open":
            if state.open_pos < len(self._open) and token_id == self._open[state.open_pos]:
                state.open_pos += 1
                if state.open_pos >= len(self._open):
                    state.phase = "await_element"
            else:
                # invalid; leave state (the caller should have only allowed next token)
                return
            return

        if ph == "await_element":
            # wrap open
            if self._wrap and token_id == self._wrap[0]:
                state.wrap_pos = 1
                # If wrap is a single token, enter element immediately
                if state.wrap_pos >= len(self._wrap):
                    state.element_state = self.start_element(state, tokenizer)
                    state.phase = "in_element"
                else:
                    state.phase = "in_wrap_open"
                return
            # list close
            if self._close and token_id == self._close[0] and state.elements_completed >= self._min:
                state.phase = "in_close"
                state.close_pos = 1
                return
            # element token (no wrap)
            if not self._wrap:
                if state.element_state is None:
                    state.element_state = self.start_element(state, tokenizer)
                if isinstance(self._elements, list):
                    self._elements[state.elements_completed].step(state.element_state, int(token_id), tokenizer)
                else:
                    self._elements.step(state.element_state, int(token_id), tokenizer)
                state.phase = "in_element"
                return
            return

        if ph == "in_wrap_open":
            if state.wrap_pos < len(self._wrap) and token_id == self._wrap[state.wrap_pos]:
                state.wrap_pos += 1
                if state.wrap_pos >= len(self._wrap):
                    # Enter element
                    state.element_state = self.start_element(state, tokenizer)
                    state.phase = "in_element"
            return

        if ph == "in_element":
            if state.element_state is None:
                state.element_state = self.start_element(state, tokenizer)
            # closing wrap if element complete and wrap chosen
            if self._wrap and self.element_completed(state) and token_id == self._wrap[0]:
                state.wrap_pos = 1
                if state.wrap_pos >= len(self._wrap):
                    # single-token wrap close completes immediately
                    state.elements_completed += 1
                    state.wrap_pos = 0
                    state.phase = "await_sep"
                else:
                    state.phase = "in_wrap_close"
                return
            # otherwise consume element token
            if isinstance(self._elements, list):
                self._elements[state.elements_completed].step(state.element_state, int(token_id), tokenizer)
            else:
                self._elements.step(state.element_state, int(token_id), tokenizer)

            return

        if ph == "in_wrap_close":
            if state.wrap_pos < len(self._wrap) and token_id == self._wrap[state.wrap_pos]:
                state.wrap_pos += 1
                if state.wrap_pos >= len(self._wrap):
                    state.elements_completed += 1
                    state.phase = "await_sep"
                    state.wrap_pos = 0
            return

        if ph == "await_sep":
            if self._sep and token_id == self._sep[0] and (self._max is None or state.elements_completed < self._max):
                state.phase = "in_separator"
                state.sep_pos = 1
                return
            if self._close and token_id == self._close[0] and state.elements_completed >= self._min:
                state.phase = "in_close"
                state.close_pos = 1
                self.in_close(state, token_id)
                return
            return

        if ph == "in_separator":
            if state.sep_pos < len(self._sep) and token_id == self._sep[state.sep_pos]:
                state.sep_pos += 1
            if state.sep_pos >= len(self._sep):
                state.phase = "await_element"
                state.sep_pos = 0
            return

        if ph == "in_close":
            self.in_close(state, token_id)

        if ph == "in_end_with":
            if state.end_with_pos < len(self._end_with) and token_id == self._end_with[state.end_with_pos]:
                state.end_with_pos += 1
                if state.end_with_pos >= len(self._end_with):
                    state._complete = True
            return

    def in_close(self, state, token_id):
        if state.close_pos < len(self._close) and token_id == self._close[state.close_pos]:
            state.close_pos += 1
            if state.close_pos >= len(self._close):
                # close consumed
                if self._end_with:
                    state.phase = "in_end_with"
                    state.end_with_pos = 0
                else:
                    state._complete = True
        else:
            # after finishing close, consume end_with
            if self._end_with and state.close_pos >= len(self._close):
                if state.end_with_pos < len(self._end_with) and token_id == self._end_with[state.end_with_pos]:
                    state.end_with_pos += 1
                    if state.end_with_pos >= len(self._end_with):
                        state._complete = True
        return

    def trim_answer(self, ans: str) -> str:
        return ans
