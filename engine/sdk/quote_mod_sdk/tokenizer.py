"""Tokenizer utility helpers for Quote mods."""

from __future__ import annotations

from typing import Any, Iterable, List


def tokenize(
    text: str, tokenizer: Any, *, add_special_tokens: bool = False
) -> List[int]:
    """Tokenize *text* with the provided *tokenizer*.

    The tokenizer must expose ``encode(text, add_special_tokens=False)`` or be a callable
    returning either a list/tuple/array of token ids or a mapping with ``input_ids``.
    """

    if tokenizer is None:
        raise RuntimeError("Tokenizer is required when calling tokenize().")

    try:
        if hasattr(tokenizer, "encode"):
            ids = tokenizer.encode(text, add_special_tokens=add_special_tokens)  # type: ignore[attr-defined]
            return _normalize_ids(ids)
        if callable(tokenizer):
            encoded = tokenizer(text)
            if isinstance(encoded, dict) and "input_ids" in encoded:
                return _normalize_ids(encoded["input_ids"])
            return _normalize_ids(encoded)
    except Exception as exc:  # pragma: no cover - passthrough for clarity
        raise RuntimeError(f"Tokenizer failed to encode text: {exc}") from exc
    raise RuntimeError(
        "Tokenizer must provide encode(text, add_special_tokens=False) or return input_ids."
    )


def _normalize_ids(ids: Any) -> List[int]:
    if isinstance(ids, list):
        return [int(t) for t in ids]
    if isinstance(ids, tuple):
        return [int(t) for t in ids]
    if hasattr(ids, "tolist") and callable(getattr(ids, "tolist")):
        try:
            candidate = ids.tolist()
            if isinstance(candidate, (list, tuple)):
                return [int(t) for t in candidate]
        except Exception:
            pass
    if isinstance(ids, Iterable):
        return [int(t) for t in list(ids)]
    raise TypeError(f"Unsupported input_ids type: {type(ids)!r}")


__all__ = ["tokenize"]
