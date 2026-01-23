from __future__ import annotations

from typing import Any, Dict, Set

from .primitives import (
    TokensStrategy,
)


def _compile_tokens_strategy(spec: Dict[str, Any], tokenizer: Any) -> TokensStrategy:
    items = list(spec.get("items") or [])
    if not items:
        raise ValueError("tokens.items must be a non-empty list of strings")
    token_ids: Set[int] = set()
    for text in items:
        ids = tokenizer.encode(text, add_special_tokens=False)
        seq = [int(t) for t in (list(ids) if not isinstance(ids, list) else ids)]
        if len(seq) != 1:
            raise ValueError(f"tokens.items entry {text!r} must map to exactly one token")
        token_ids.add(int(seq[0]))
    return TokensStrategy(token_ids)
