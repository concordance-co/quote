from __future__ import annotations

from typing import Iterable
import numpy as np


class TestTokenizer:
    def __init__(self, vocab_chars: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ,._-[]\"\n") -> None:
        self._vocab = {ch: ord(ch) for ch in vocab_chars}
        self.eos_token_id = None  # can be set externally if needed

    def get_vocab(self):
        return {ch: idx for ch, idx in self._vocab.items()}

    def encode(self, text: str, add_special_tokens: bool = False):
        return [self._vocab.get(ch, ord(ch)) for ch in text]

    def decode(self, tokens: Iterable[int], skip_special_tokens: bool = True) -> str:
        if isinstance(tokens, int):
            tokens = [tokens]
        return "".join(chr(int(t)) for t in tokens)


class DummyLogits:
    def __init__(self, vocab_size: int, fill: float = 0.0, device: str | None = None) -> None:
        self._arr = np.full((vocab_size,), float(fill), dtype=np.float32)
        self.device = device

    def to_numpy(self):
        return self._arr

    @classmethod
    def from_numpy(cls, arr):
        obj = cls(len(arr))
        obj._arr = np.array(arr, copy=True)
        return obj

    def to(self, device):  # pragma: no cover - minimal impl
        self.device = device
        return self

