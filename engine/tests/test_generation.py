from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

pytestmark = [pytest.mark.contract]


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INFERENCE_SRC = PROJECT_ROOT / "inference" / "src"
SDK_SRC = PROJECT_ROOT / "sdk"
SHARED_SRC = PROJECT_ROOT / "shared" / "src"
for p in (INFERENCE_SRC, SDK_SRC, SHARED_SRC):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


from quote.backends.interface import GenerationConfig
from quote.generation import generate
from quote.mods.manager import ModManager
from shared.types import ForceOutput, ForceTokens, ForwardPass, Noop, Prefilled


class _Tok:
    eos_token_id = 0

    def decode(self, tokens, skip_special_tokens: bool = True):
        if isinstance(tokens, int):
            tokens = [tokens]
        return "".join(chr(65 + int(t) % 26) for t in tokens)


class _ArrayTensor:
    def __init__(self, arr):
        self._arr = np.asarray(arr, dtype=np.float32)

    def to_numpy(self):
        return self._arr

    @property
    def shape(self):
        return self._arr.shape


class FakeBackend:
    def __init__(self):
        self._tok = _Tok()
        self._states = {}
        self._model_id = "fake-model"

    def load_model(self, model_id, config):
        return None

    def tokenizer(self):
        return self._tok

    def prefill(self, request_id, input_ids, max_steps):
        self._states[request_id] = {
            "prompt": list(input_ids),
            "completion": [],
            "step": 0,
            "pending": _ArrayTensor([[0.1, 0.2, 0.9]]),
        }
        return Prefilled(request_id=request_id, step=0, max_steps=max_steps, input_ids=list(input_ids))

    def forward_pass(self, request_id):
        s = self._states[request_id]
        return ForwardPass(request_id=request_id, step=s["step"], logits=s["pending"], input_ids=self.get_input_ids(request_id))

    def sample(self, request_id, logits, temperature, top_p, top_k):
        arr = logits.to_numpy() if hasattr(logits, "to_numpy") else np.asarray(logits)
        tok = int(np.argmax(arr.reshape(-1)))
        from shared.types import Sampled

        return Sampled(request_id=request_id, step=self._states[request_id]["step"], sampled_token=tok)

    def add_tokens(self, request_id, tokens, forced):
        from shared.types import Added

        s = self._states[request_id]
        s["completion"].extend([int(t) for t in tokens])
        s["step"] += 1
        # Keep deterministic logits (argmax token id = 2) unless completion contains high token.
        next_peak = 2 if not s["completion"] else int(s["completion"][-1] % 3)
        base = np.full((1, 3), 0.1, dtype=np.float32)
        base[0, next_peak] = 1.0
        s["pending"] = _ArrayTensor(base)
        return Added(request_id=request_id, step=s["step"] - 1, added_tokens=list(tokens), forced=bool(forced))

    def rewind_kv_cache(self, request_id, n):
        s = self._states[request_id]
        if n <= 0:
            return
        s["completion"] = s["completion"][: max(0, len(s["completion"]) - n)]
        s["step"] = len(s["completion"])

    def get_hidden_states(self, request_id, layer):
        return None

    def get_attention_patterns(self, request_id, layer):
        return None

    def get_input_ids(self, request_id):
        s = self._states[request_id]
        return list(s["prompt"]) + list(s["completion"])

    def get_completion_ids(self, request_id):
        return list(self._states[request_id]["completion"])

    def decode(self, token_ids):
        return self._tok.decode(token_ids)

    def eos_token_id(self):
        return self._tok.eos_token_id

    def shutdown(self):
        self._states.clear()


def test_generation_force_tokens(monkeypatch):
    monkeypatch.setenv("QUOTE_LOG_INGEST_URL", "http://127.0.0.1:9/v1/ingest")

    def mod(event, _tok):
        if isinstance(event, ForwardPass) and event.step == 0:
            return ForceTokens([1, 2])
        return Noop()

    backend = FakeBackend()
    mm = ModManager([mod], tokenizer=backend.tokenizer())
    result = generate(
        backend=backend,
        input_ids=[10, 11],
        request_id="r-force",
        mod_manager=mm,
        config=GenerationConfig(max_tokens=3, temperature=0.0, top_p=1.0, top_k=1),
    )
    assert result.output_ids[:2] == [1, 2]
    assert len(result.output_ids) == 3


def test_generation_terminal_force_output(monkeypatch):
    monkeypatch.setenv("QUOTE_LOG_INGEST_URL", "http://127.0.0.1:9/v1/ingest")

    def mod(event, _tok):
        if isinstance(event, Prefilled):
            return ForceOutput([7, 7, 7])
        return Noop()

    backend = FakeBackend()
    mm = ModManager([mod], tokenizer=backend.tokenizer())
    result = generate(
        backend=backend,
        input_ids=[3, 4],
        request_id="r-terminal",
        mod_manager=mm,
        config=GenerationConfig(max_tokens=8, temperature=0.0),
    )
    assert result.output_ids == [7, 7, 7]
    assert result.metadata.get("terminal_action") == "ForceOutput"
