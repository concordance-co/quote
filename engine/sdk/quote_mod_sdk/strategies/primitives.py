from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, cast
from enum import Enum, auto
from shared.types import Backtrack, ForceTokens

from .base import RuntimeState, Strategy, TrieNode, decode_token, require_token_ids


# --------------------------- choices (responses) ---------------------------


@dataclass
class _ChoicesState(RuntimeState):
    active: List[TrieNode] = field(default_factory=list)
    has_terminal: bool = False
    started: bool = False
    done: bool = False


class ChoicesStrategy(Strategy):
    def __init__(self, root: TrieNode) -> None:
        self._root = root

    def start(self, tokenizer: Any) -> RuntimeState:
        rts = _ChoicesState(active=[self._root], has_terminal=False, started=False)
        return rts

    def allowed_tokens(self, state: _ChoicesState, tokenizer: Any) -> Set[int]:
        nodes = state.active or [self._root]
        allowed: Set[int] = set()
        has_terminal = False
        for node in nodes:
            if node.terminal:
                has_terminal = True
            allowed.update(node.children.keys())
        state.has_terminal = has_terminal
        return allowed

    def disallowed_tokens(self, state: _UntilState, tokenizer: Any) -> Set[int]:
        return set()

    def step(self, state: RuntimeState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:
        state = cast(_ChoicesState, state)
        state.started = True
        nodes = state.active or [self._root]
        next_nodes: List[TrieNode] = []
        for node in nodes:
            child = node.children.get(int(token_id))
            if child is not None and child not in next_nodes:
                next_nodes.append(child)
        state.active = list(next_nodes)
        if all(n.terminal for n in next_nodes):
            state.active = []
        state.has_terminal = any(n.terminal for n in next_nodes)

    def is_complete(self, state: RuntimeState) -> bool:
        state = cast(_ChoicesState, state)
        if state.done:
            return state.done
        # Completing a choices element means we matched exactly one of the choices
        # and no longer have outgoing edges; the enclosing ListStrategy will wrap/close.
        state.done = state.started and not state.active and state.has_terminal
        return state.done

    def trim_answer(self, answer: str) -> str:
        return answer

# ---------------------------- until (stop char) ----------------------------

class UntilEndType(Enum):
    TAG = auto()
    ANYCHAR = auto()

@dataclass
class _UntilState(RuntimeState):
    done: bool = False
    accum_toks = []
    accum: str = ""
    max_len: Optional[int] = None
    disallow_eos: bool = True


class UntilStrategy(Strategy):
    def __init__(self, start_tag, end_type: UntilEndType, stop: str, ) -> None:
        self.end_type = end_type
        self._start_tag = start_tag
        self.stop = stop
        if end_type == UntilEndType.ANYCHAR:
            self._stop_chars = set(stop)
        else:
            self._stop_chars = set("")
        self._all_tokens: Optional[Set[int]] = None

    def start(self, tokenizer: Any) -> RuntimeState:
        return _UntilState(done=False)

    def allowed_tokens(self, state: _UntilState, tokenizer: Any) -> Set[int]:
        if self._start_tag and len(state.accum) < len(self._start_tag):
            toks = tokenizer.encode(self._start_tag, add_special_tokens=False)
            accum_toks = tokenizer.encode(state.accum, add_special_tokens=False)
            return set([toks[len(accum_toks)]])
        if self._all_tokens is None:
            self._all_tokens = require_token_ids(tokenizer)
        return set(self._all_tokens)

    def disallowed_tokens(self, state: _UntilState, tokenizer: Any) -> Set[int]:
        if state.disallow_eos:
            id = getattr(tokenizer, "eos_token_id", None)
            if id:
                return set([int(id)])
            else:
                return set()
        else:
            return set()

    def step(self, state: _UntilState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:
        if state.done:
            return
        state.accum_toks.append(token_id)
        text = decode_token(tokenizer, token_id)
        state.accum += text
        if self.end_type == UntilEndType.TAG:
            if self.stop in state.accum:
                state.done = True
        else:
            if any(ch in state.accum for ch in self._stop_chars):
                state.done = True

    def is_complete(self, state: _UntilState) -> bool:
        return state.done

    def trim_answer(self, answer: str) -> str:
        return answer


# ---------------------------- chars (char class) ---------------------------


class CharsMode(Enum):
    ALPHA = auto()
    ALPHANUMERIC = auto()
    STRING = auto()
    NUMERIC = auto()
    JS_FLOAT = auto()


@dataclass
class _CharsState(RuntimeState):
    char_count: int = 0
    stop_token: Optional[int] = None
    done: bool = False
    # JS_FLOAT bookkeeping
    seen_decimal: bool = False
    seen_exponent: bool = False
    after_exponent: bool = False
    started: bool = False

import re
unescaped_double = re.compile(r'(?<!\\)"')


class CharsStrategy(Strategy):
    def __init__(
        self,
        kind: CharsMode,
        stop: int | str,
        min_chars: int = 0,
        include_stop_in_answer: bool = False,
    ) -> None:
        self._kind = kind
        self._min = int(min_chars) if isinstance(min_chars, (int, float)) else 0
        if isinstance(stop, int):
            self._max = int(stop) if isinstance(stop, (int, float)) else None
            self._stop = None
        else:
            self._max = None
            self._stop = stop
        self._allowed_ids: Optional[Set[int]] = None
        self._allowed_ids_with_stop: Optional[Set[int]] = None
        self._length_cache: Dict[int, int] = {}
        # JS_FLOAT caches
        self._js_digit_ids: Optional[Set[int]] = None
        self._js_period_ids: Optional[Set[int]] = None
        self._js_minus_ids: Optional[Set[int]] = None
        self._js_e_ids: Optional[Set[int]] = None
        self._include_stop_in_answer = include_stop_in_answer

    def _matches(self, text: str, ends_with_stop: bool) -> bool:
        if self._kind == CharsMode.ALPHA:
            if text.isalpha():
                return True
            if ends_with_stop and self._stop:
                # check if stop is at end of text
                end_len = len(self._stop)
                return text[-end_len:] == self._stop and text[:end_len].isalpha()
            return False
        if self._kind == CharsMode.ALPHANUMERIC:
            if text.isalnum():
                return True
            if ends_with_stop and self._stop:
                # check if stop is at end of text
                end_len = len(self._stop)
                return text[-end_len:] == self._stop and text[:end_len].isalnum()
            return False
        if self._kind == CharsMode.STRING:
            # prevents unescaped double quotes and multiple stops
            if not bool(re.search(unescaped_double, text)):
                return True
            if ends_with_stop and self._stop:
                # check if stop is at end of text
                if not self._include_stop_in_answer:
                    try:
                        idx = text.index(self._stop)
                        no_end_is_str = not bool(re.search(unescaped_double, text[:idx]))
                        return no_end_is_str
                    except:
                        end_len = len(self._stop)
                        no_end_is_str = not bool(re.search(unescaped_double, text[:end_len]))
                        return text[-end_len:] == self._stop and no_end_is_str
                else:
                    end_len = len(self._stop)
                    no_end_is_str = not bool(re.search(unescaped_double, text[:end_len]))
                    return text[-end_len:] == self._stop and no_end_is_str
            return False
        return text.isdigit()

    def _ensure_allowed_ids(self, tokenizer: Any) -> None:
        if self._allowed_ids is not None:
            return
        all_ids = require_token_ids(tokenizer)
        allowed: Set[int] = set()
        allowed_with_stop: Set[int] = set()
        for tid in all_ids:
            s = decode_token(tokenizer, tid)
            allowed_wo_stop = self._matches(s, False)
            if s and allowed_wo_stop:
                allowed.add(int(tid))
                self._length_cache[int(tid)] = len(s)
            elif self._stop and self._matches(s, True):
                allowed_with_stop.add(int(tid))
                self._length_cache[int(tid)] = len(s)
        self._allowed_ids = allowed
        self._allowed_ids_with_stop = allowed_with_stop


    def start(self, tokenizer: Any) -> RuntimeState:
        if self._stop:
            return _CharsState(
                char_count=0,
                done=False,
                stop_token=tokenizer.encode(self._stop, add_special_tokens=False)[0],
                seen_decimal=False,
                seen_exponent=False,
                after_exponent=False,
                started=False,
            )
        else:
            return _CharsState(
                char_count=0,
                done=False,
                seen_decimal=False,
                seen_exponent=False,
                after_exponent=False,
                started=False,
            )

    def _ensure_js_float_ids(self, tokenizer: Any) -> None:
        if (
            self._js_digit_ids is not None
            and self._js_period_ids is not None
            and self._js_minus_ids is not None
            and self._js_e_ids is not None
        ):
            return
        all_ids = require_token_ids(tokenizer)
        digit_ids: Set[int] = set()
        period_ids: Set[int] = set()
        minus_ids: Set[int] = set()
        e_ids: Set[int] = set()
        for tid in all_ids:
            s = decode_token(tokenizer, tid)
            if not s:
                continue
            if s.isdigit():
                digit_ids.add(int(tid))
                self._length_cache[int(tid)] = len(s)
            elif s == ".":
                period_ids.add(int(tid))
                self._length_cache[int(tid)] = 1
            elif s == "-":
                minus_ids.add(int(tid))
                self._length_cache[int(tid)] = 1
            elif s == "e" or s == "E":
                e_ids.add(int(tid))
                self._length_cache[int(tid)] = 1
        self._js_digit_ids = digit_ids
        self._js_period_ids = period_ids
        self._js_minus_ids = minus_ids
        self._js_e_ids = e_ids

    def allowed_tokens(self, state: _CharsState, tokenizer: Any) -> Set[int]:
        if self._kind == CharsMode.JS_FLOAT:
            self._ensure_js_float_ids(tokenizer)
            assert self._js_digit_ids is not None
            assert self._js_period_ids is not None
            assert self._js_minus_ids is not None
            assert self._js_e_ids is not None

            allowed: Set[int] = set()
            # digits always allowed
            allowed.update(self._js_digit_ids)
            # decimal point allowed only if not seen yet and have at least one digit
            if not state.seen_decimal and state.started:
                allowed.update(self._js_period_ids)
            # exponent allowed only after we've started (and not seen exponent)
            if not state.seen_exponent and state.started:
                allowed.update(self._js_e_ids)
            # minus allowed at start (leading sign) or immediately after exponent
            if not state.started or state.after_exponent:
                allowed.update(self._js_minus_ids)
            # allow stop token when minimum satisfied
            if state.stop_token and state.char_count >= self._min:
                allowed.add(state.stop_token)
            return allowed
        # Default ALPHA/ALPHANUMERIC/NUMERIC/STRING behavior
        self._ensure_allowed_ids(tokenizer)

        assert self._allowed_ids is not None
        if self._max is None:
            allowed = set(self._allowed_ids)
            if state.stop_token and state.char_count >= self._min:
                allowed.update(self._allowed_ids_with_stop)
                allowed.add(state.stop_token)
            return allowed
        remaining = self._max - state.char_count
        allowed: Set[int] = set()
        for tid in self._allowed_ids:
            length = self._length_cache.get(tid)
            if length is None:
                s = decode_token(tokenizer, tid)
                length = len(s)
                self._length_cache[tid] = length
            if length <= remaining:
                allowed.add(tid)

        if state.stop_token and state.char_count >= self._min:
            allowed.update(self._allowed_ids_with_stop)
            allowed.add(state.stop_token)
        return allowed

    def disallowed_tokens(self, state: _UntilState, tokenizer: Any) -> Set[int]:
        id = getattr(tokenizer, "eos_token_id", None)
        if id:
            return set([int(id)])
        else:
            return set()

    def step(self, state: _CharsState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:
        if state.stop_token and state.stop_token == token_id or decode_token(tokenizer, token_id).count(self._stop) > 0:
            state.done = True
            return
        if self._kind == CharsMode.JS_FLOAT:
            s = decode_token(tokenizer, token_id)
            # Update flags
            if s and s.isdigit():
                state.started = True
                state.after_exponent = False
            elif s == ".":
                state.seen_decimal = True
                # starting with "." without prior digit does not count as started
            elif s == "e" or s == "E":
                state.seen_exponent = True
                state.after_exponent = True
            elif s == "-":
                # minus allowed at start or after exponent
                state.after_exponent = False
            # Count characters as length of decoded piece
            state.char_count += len(s)
        else:
            s = decode_token(tokenizer, token_id)
            state.char_count += len(s)
        if self._max is not None and state.char_count >= self._max:
            state.done = True
        if len(self.allowed_tokens(state, tokenizer)) == 0:
            state.done = True

    def is_complete(self, state: _CharsState) -> bool:
        if state.done:
            return True
        if self._max:
            remaining = self._max - state.char_count
            if remaining <= 0:
                state.done = True
                return True
        return state.done and state.char_count >= self._min

    def trim_answer(self, answer: str) -> str:
        if not self._include_stop_in_answer and self._stop:
            try:
                return answer[:answer.index(self._stop)]
            except:
                return answer.replace(self._stop, "")
        return answer

# --------------------------- tokens (single-token) -------------------------


@dataclass
class _TokensState(RuntimeState):
    done: bool = False


class TokensStrategy(Strategy):
    def __init__(self, token_ids: Set[int]) -> None:
        self._token_ids = set(int(t) for t in token_ids)

    def start(self, tokenizer: Any) -> RuntimeState:
        return _TokensState(done=False)

    def allowed_tokens(self, state: _TokensState, tokenizer: Any) -> Set[int]:
        return set(self._token_ids)

    def disallowed_tokens(self, state: _UntilState, tokenizer: Any) -> Set[int]:
        return set()

    def step(self, state: _TokensState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:
        # Completes after first token
        state.done = True

    def is_complete(self, state: _TokensState) -> bool:
        return state.done

    def trim_answer(self, answer: str) -> str:
        return answer
