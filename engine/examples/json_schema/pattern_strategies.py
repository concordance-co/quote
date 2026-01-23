from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Set, List

from quote_mod_sdk.strategies.base import Strategy, RuntimeState, decode_token, require_token_ids
from quote_mod_sdk.strategies.strategy_constructor import StrategyConstructor
from quote_mod_sdk.strategies.primitives import CharsStrategy, CharsMode
from shared.types import Backtrack, ForceTokens


@dataclass
class _PatternState(RuntimeState):
    inner_state: Any
    text: str = ""
    done: bool = False


class PatternStrategy(Strategy):
    """Generic pattern strategy: wraps STRING strategy and tracks decoded text.

    For complex patterns (beyond our fixed-length subset), we rely on:
    - Strong prompts mentioning the pattern.
    - Assignment-time regex checks for validation (and optional field-level retry).
    """

    def __init__(self, pattern: Optional[str], stop: str = "\n", min_chars: int = 0):
        self._pattern = pattern
        self._inner = CharsStrategy(CharsMode.STRING, stop=stop, min_chars=min_chars)

    def start(self, tokenizer: Any) -> RuntimeState:
        inner = self._inner.start(tokenizer)
        return _PatternState(inner_state=inner, text="", done=False)

    def allowed_tokens(self, state: _PatternState, tokenizer: Any) -> Set[int]:
        return self._inner.allowed_tokens(state.inner_state, tokenizer)

    def disallowed_tokens(self, state: _PatternState, tokenizer: Any) -> Set[int]:
        return self._inner.disallowed_tokens(state.inner_state, tokenizer)

    def step(
        self, state: RuntimeState, token_id: int, tokenizer: Any
    ) -> Optional[Backtrack] | Optional[ForceTokens]:
        st = state  # type: ignore[assignment]
        self._inner.step(st.inner_state, token_id, tokenizer)
        st.text += decode_token(tokenizer, token_id)
        return None

    def is_complete(self, state: RuntimeState) -> bool:
        st = state  # type: ignore[assignment]
        return self._inner.is_complete(st.inner_state)

    def trim_answer(self, answer: str) -> str:
        return self._inner.trim_answer(answer)


@dataclass
class _FixedPatternState(RuntimeState):
    pos: int = 0
    done: bool = False


class FixedPatternStrategy(Strategy):
    """Strategy for fixed-length concatenations of literals/char-classes.

    This covers patterns like:
    - [0-9]{4}-[0-9]{2}-[0-9]{2}
    - [A-Z]{3}[0-9]{3}
    - foo[0-9]{2}bar

    We only support patterns that:
    - Are anchored (or effectively treated as ^...$).
    - Have no alternation (|), groups, or variable-length quantifiers (*, +, ?, {m,}, {m,n}).
    - Use only positive character classes and literals.
    """

    def __init__(self, positions: List[Optional[Set[str]]]) -> None:
        self._positions = positions
        self._max_len = len(positions)

    def start(self, tokenizer: Any) -> RuntimeState:
        return _FixedPatternState(pos=0, done=False)

    def allowed_tokens(self, state: _FixedPatternState, tokenizer: Any) -> Set[int]:
        if state.done or state.pos >= self._max_len:
            return set()
        allowed: Set[int] = set()
        all_ids = require_token_ids(tokenizer)
        for tid in all_ids:
            s = decode_token(tokenizer, tid)
            if not s:
                continue
            if state.pos + len(s) > self._max_len:
                continue
            ok = True
            for offset, ch in enumerate(s):
                pos = state.pos + offset
                allowed_chars = self._positions[pos]
                if allowed_chars is not None and ch not in allowed_chars:
                    ok = False
                    break
                # For None (wildcard), we accept any non-newline char.
                if allowed_chars is None and ch == "\n":
                    ok = False
                    break
            if ok:
                allowed.add(int(tid))
        return allowed

    def disallowed_tokens(self, state: _FixedPatternState, tokenizer: Any) -> Set[int]:
        return set()

    def step(
        self, state: RuntimeState, token_id: int, tokenizer: Any
    ) -> Optional[Backtrack] | Optional[ForceTokens]:
        st = state  # type: ignore[assignment]
        s = decode_token(tokenizer, int(token_id))
        st.pos += len(s)
        if st.pos >= self._max_len:
            st.done = True
        return None

    def is_complete(self, state: RuntimeState) -> bool:
        st = state  # type: ignore[assignment]
        return st.done or st.pos >= self._max_len

    def trim_answer(self, answer: str) -> str:
        return answer[: self._max_len]


def _parse_char_class(body: str) -> Optional[Set[str]]:
    """Parse a simple positive character class body (no leading ^).

    Supports:
    - Single chars: [abc]
    - Ranges: [a-z]
    - Mixed: [a-zA-Z0-9]

    Returns None if unsupported (e.g., empty, malformed).
    """
    chars: Set[str] = set()
    i = 0
    n = len(body)
    if n == 0:
        return None
    while i < n:
        # Support \d inside classes as [0-9]
        if body[i] == "\\" and i + 1 < n and body[i + 1] == "d":
            for code in range(ord("0"), ord("9") + 1):
                chars.add(chr(code))
            i += 2
            continue
        # Range: a-z
        if i + 2 < n and body[i + 1] == "-":
            start = body[i]
            end = body[i + 2]
            if ord(start) > ord(end):
                return None
            for code in range(ord(start), ord(end) + 1):
                chars.add(chr(code))
            i += 3
        else:
            chars.add(body[i])
            i += 1
    return chars


def _build_fixed_positions(pattern: str) -> Optional[List[Optional[Set[str]]]]:
    """Attempt to build a fixed-length positional pattern from a regex.

    Supported subset:
    - Concatenation only (no '|' or groups).
    - Literals, '.', positive character classes [...].
    - Fixed quantifiers {n} or implicit {1}.

    Returns:
    - List of length-N where each element is:
      - a set of allowed characters for that position, or
      - None meaning 'any non-newline character'.
    - None if pattern is not in this subset.
    """
    p = pattern.strip()
    # Strip anchors if present.
    if p.startswith("^"):
        p = p[1:]
    if p.endswith("$"):
        p = p[:-1]

    positions: List[Optional[Set[str]]] = []
    i = 0
    L = len(p)

    while i < L:
        ch = p[i]
        atom_allowed: Optional[Set[str]] = None

        # Group: ( ... ) with no alternation. We treat this as a concatenation
        # of its inner pattern, optionally followed by a fixed quantifier.
        if ch == "(":
            j = i + 1
            depth = 1
            inner_chars: List[str] = []
            while j < L and depth > 0:
                if p[j] == "\\" and j + 1 < L:
                    # Preserve escaped chars verbatim inside inner pattern.
                    inner_chars.append(p[j])
                    inner_chars.append(p[j + 1])
                    j += 2
                    continue
                if p[j] == "(":
                    # Nested groups not supported in this fixed subset.
                    return None
                if p[j] == ")":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                if depth > 0 and p[j] != ")":
                    inner_chars.append(p[j])
                j += 1
            if depth != 0:
                # Unmatched parenthesis.
                return None
            inner = "".join(inner_chars)
            inner_positions = _build_fixed_positions(inner)
            if inner_positions is None:
                return None
            i = j
            # Parse optional quantifier for the whole group.
            repeat = 1
            if i < L and p[i] in "*+?{":
                q = p[i]
                if q in "*+?":
                    # Variable-length quantifiers not yet supported for fixed positions.
                    return None
                if q == "{":
                    k = i + 1
                    num_str = ""
                    while k < L and p[k].isdigit():
                        num_str += p[k]
                        k += 1
                    if not num_str or k >= L or p[k] not in [",", "}"]:
                        return None
                    if p[k] == ",":
                        # {m,} or {m,n} -> variable length; not supported.
                        return None
                    if p[k] != "}":
                        return None
                    repeat = int(num_str)
                    i = k + 1
            for _ in range(repeat):
                positions.extend(inner_positions)
            continue

        # Reject alternation in the fixed-concat subset.
        if ch == "|":
            return None

        if ch == "[":
            # Parse character class
            j = i + 1
            if j < L and p[j] == "^":
                # Negative classes not supported yet.
                return None
            body_chars = []
            while j < L and p[j] != "]":
                body_chars.append(p[j])
                j += 1
            if j >= L or p[j] != "]":
                return None
            body = "".join(body_chars)
            atom_allowed = _parse_char_class(body)
            if atom_allowed is None:
                return None
            i = j + 1
        elif ch == ".":
            # Any non-newline char.
            atom_allowed = None
            i += 1
        elif ch == "\\":
            # Simple escapes: \n, \r, \t, \d, or literal char.
            if i + 1 >= L:
                return None
            esc = p[i + 1]
            if esc == "n":
                atom_allowed = {"\n"}
            elif esc == "r":
                atom_allowed = {"\r"}
            elif esc == "t":
                atom_allowed = {"\t"}
            elif esc == "d":
                atom_allowed = set("0123456789")
            else:
                atom_allowed = {esc}
            i += 2
        else:
            # Literal char (including ')' if it appears outside of a group,
            # which we treat as unsupported).
            if ch == ")":
                # Unmatched closing parenthesis.
                return None
            atom_allowed = {ch}
            i += 1

        # Parse optional quantifier
        repeat = 1
        if i < L and p[i] in "*+?{":
            q = p[i]
            if q in "*+?":
                # Variable-length quantifiers not yet supported for fixed positions.
                return None
            # {n} only
            if q == "{":
                k = i + 1
                num_str = ""
                while k < L and p[k].isdigit():
                    num_str += p[k]
                    k += 1
                if not num_str or k >= L or p[k] not in [",", "}"]:
                    return None
                if p[k] == ",":
                    # {m,} or {m,n} -> variable length; not supported in this stage.
                    return None
                # Expect closing '}'
                if p[k] != "}":
                    return None
                repeat = int(num_str)
                i = k + 1

        for _ in range(repeat):
            positions.append(atom_allowed)

    return positions if positions else None


class PatternStrat(StrategyConstructor):
    """StrategyConstructor for pattern-aware strategies with staged support.

    - First try to compile a fixed-length positional pattern (FixedPatternStrategy).
    - Otherwise fall back to PatternStrategy (STRING + tracking).
    """

    def __init__(self, pattern: Optional[str], stop: str = "\n", min_chars: int = 0):
        self.pattern = pattern
        self.stop = stop
        self.min_chars = min_chars

    def into_strategy(self, tokenizer: Any) -> Strategy:
        if isinstance(self.pattern, str):
            positions = _build_fixed_positions(self.pattern)
            if positions is not None:
                return FixedPatternStrategy(positions)
        return PatternStrategy(self.pattern, stop=self.stop, min_chars=self.min_chars)
