from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Set, runtime_checkable
from shared.types import ModAction
from shared.types import ForceTokens
from shared.types import Backtrack


class RuntimeState(Protocol):
    """Opaque runtime state for a Strategy.

    Each concrete Strategy defines its own attributes; callers should not
    depend on specific fields.
    """

    pass

@runtime_checkable
class Strategy(Protocol):
    """Strategy protocol for token-level constraints.

    A Strategy is initialized via compile_strategy(spec, tokenizer). At runtime:
    - start() creates a new state instance for a generation.
    - allowed_tokens(state) returns a set of permitted token IDs for the next step.
    - step(state, token_id) advances the state given an emitted token.
    - is_complete(state) indicates that the strategy has finished and should no
      longer constrain logits.
    - trim_answer(answer) is a function to trim the answer
    """

    def start(self, tokenizer: Any) -> RuntimeState:  # pragma: no cover - Protocol
        ...

    def allowed_tokens(self, state: RuntimeState, tokenizer: Any) -> Set[int]:  # pragma: no cover - Protocol
        ...

    def disallowed_tokens(self, state: RuntimeState, tokenizer: Any) -> Set[int]:  # pragma: no cover - Protocol
        ...

    def step(self, state: RuntimeState, token_id: int, tokenizer: Any) -> Optional[Backtrack] | Optional[ForceTokens]:  # pragma: no cover - Protocol
        ...

    def is_complete(self, state: RuntimeState) -> bool:  # pragma: no cover - Protocol
        ...

    def trim_answer(self, answer: str) -> str:
        ...

def require_token_ids(tokenizer: Any) -> Set[int]:
    """Return the set of all token IDs for a tokenizer.

    Tries get_vocab() first; falls back to range(len(tokenizer)).
    """
    try:
        vocab = getattr(tokenizer, "get_vocab", None)
        if callable(vocab):
            mapping = vocab()
            if isinstance(mapping, dict) and mapping:
                return set(int(v) for v in mapping.values())
    except Exception:
        pass
    try:
        n = int(len(tokenizer))
        return set(range(n))
    except Exception as exc:
        raise RuntimeError(
            "Tokenizer must expose get_vocab() or __len__()"
        ) from exc


def tokenize_str(text: Optional[str], tokenizer: Any) -> list[int]:
    """Tokenize a string into token IDs (empty string -> empty list)."""
    if not text:
        return []
    enc = tokenizer.encode(text, add_special_tokens=False)
    if not isinstance(enc, list):
        enc = list(enc)
    return [int(t) for t in enc]


def decode_token(tokenizer: Any, token_id: int) -> str:
    try:
        return tokenizer.decode([int(token_id)], skip_special_tokens=True)
    except Exception:
        convert = getattr(tokenizer, "convert_ids_to_tokens", None)
        if callable(convert):
            tok = convert(int(token_id))
            return str(tok) if tok is not None else ""
    return ""


@dataclass
class TrieNode:
    children: Dict[int, "TrieNode"]
    terminal: bool = False

    def __init__(self) -> None:
        self.children = {}
        self.terminal = False

    def insert(self, sequence: list[int]) -> None:
        node = self
        for t in sequence:
            node = node.children.setdefault(int(t), TrieNode())
        node.terminal = True
