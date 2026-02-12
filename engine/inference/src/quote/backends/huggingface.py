from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

import numpy as np

from shared.types import Added, ForwardPass, Prefilled, Sampled

from .interface import Backend, BackendConfig

logger = logging.getLogger(__name__)


class TensorShim:
    """A minimal max.driver.Tensor-compatible wrapper for torch.Tensor."""

    _default_device: Any = None

    def __init__(self, tensor: Any) -> None:
        self._tensor = tensor

    @classmethod
    def from_numpy(cls, arr: np.ndarray) -> "TensorShim":
        try:
            import torch
        except Exception as e:  # pragma: no cover - dependency/runtime specific
            raise RuntimeError("torch is required to build TensorShim from numpy") from e

        t = torch.from_numpy(np.asarray(arr))
        device = cls._default_device
        if device is not None:
            t = t.to(device)
        return cls(t)

    def to_numpy(self) -> np.ndarray:
        if hasattr(self._tensor, "detach"):
            return self._tensor.detach().cpu().numpy()
        return np.asarray(self._tensor)

    @property
    def shape(self) -> tuple[int, ...]:
        try:
            return tuple(self._tensor.shape)
        except Exception:
            return tuple(np.asarray(self._tensor).shape)

    @property
    def device(self) -> Any:
        return getattr(self._tensor, "device", None)

    def to(self, device: Any) -> "TensorShim":
        if hasattr(self._tensor, "to"):
            return TensorShim(self._tensor.to(device))
        return self

    def copy_(self, arr: np.ndarray) -> "TensorShim":
        try:
            import torch
        except Exception as e:  # pragma: no cover - dependency/runtime specific
            raise RuntimeError("torch is required to mutate TensorShim contents") from e

        src = torch.from_numpy(np.asarray(arr)).to(self._tensor.device)
        self._tensor.copy_(src)
        return self

    def inplace_copy_from(self, other: Any) -> "TensorShim":
        if isinstance(other, TensorShim):
            other = other._tensor
        self._tensor.copy_(other)
        return self

    def item(self) -> Any:
        if hasattr(self._tensor, "item"):
            return self._tensor.item()
        return self._tensor

    def __getitem__(self, idx: Any) -> Any:
        out = self._tensor[idx]
        if hasattr(out, "shape"):
            return TensorShim(out)
        return out

    def __setitem__(self, idx: Any, value: Any) -> None:
        if isinstance(value, TensorShim):
            value = value._tensor
        self._tensor[idx] = value


@dataclass
class _RequestState:
    request_id: str
    input_ids: list[int]
    prompt_len: int
    max_steps: int
    step: int = 0
    past_key_values: Any = None
    pending_logits: Any | None = None
    pending_hidden_states: Any | None = None
    pending_attention_patterns: Any | None = None


def _coerce_tensor(logits: Any) -> Any:
    if isinstance(logits, TensorShim):
        return logits._tensor
    return logits


class HuggingFaceBackend(Backend):
    def __init__(self, config: BackendConfig | None = None) -> None:
        self._config = config or BackendConfig()
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._torch: Any | None = None
        self._device: Any | None = None
        self._dtype: Any | None = None
        self._states: dict[str, _RequestState] = {}
        self._model_id: str = self._config.model_id

    def load_model(self, model_id: str, config: BackendConfig) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._config = config
        self._model_id = model_id
        self._torch = torch
        self._device = self._resolve_device(torch, config.device)
        self._dtype = self._resolve_dtype(torch, config.dtype, self._device)

        logger.info("Loading HF model %s on %s", model_id, self._device)
        tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        if tokenizer.pad_token is None and tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=self._dtype,
            trust_remote_code=True,
        )
        model = model.to(self._device)
        model.eval()

        self._tokenizer = tokenizer
        self._model = model
        TensorShim._default_device = self._device

    def tokenizer(self) -> Any:
        self._ensure_loaded()
        return self._tokenizer

    def prefill(self, request_id: str, input_ids: list[int], max_steps: int) -> Prefilled:
        self._ensure_loaded()
        assert self._torch is not None

        ids = list(input_ids)
        if not ids:
            bos = getattr(self._tokenizer, "bos_token_id", None)
            if isinstance(bos, int):
                ids = [bos]
        inp = self._torch.tensor([ids], dtype=self._torch.long, device=self._device)
        with self._torch.no_grad():
            out = self._model(
                input_ids=inp,
                use_cache=True,
                output_hidden_states=True,
                output_attentions=bool(self._config.extract_attention),
            )

        layer_h = self._hidden_layer_index(out.hidden_states, self._config.hidden_state_layer)
        layer_a = self._attention_layer_index(out.attentions, self._config.hidden_state_layer)

        pre_h = out.hidden_states[layer_h][0].detach()
        pre_a = None
        if out.attentions is not None and layer_a is not None:
            pre_a = out.attentions[layer_a][0].detach()

        pending_a = None
        if out.attentions is not None and layer_a is not None:
            pending_a = out.attentions[layer_a][:, :, -1:, :].detach()

        state = _RequestState(
            request_id=request_id,
            input_ids=ids,
            prompt_len=len(ids),
            max_steps=max_steps,
            step=0,
            past_key_values=out.past_key_values,
            pending_logits=out.logits[:, -1, :].detach(),
            pending_hidden_states=out.hidden_states[layer_h][:, -1, :].detach(),
            pending_attention_patterns=pending_a,
        )
        self._states[request_id] = state

        return Prefilled(
            request_id=request_id,
            step=0,
            max_steps=max_steps,
            context_info={"prompt_length": len(ids)},
            hidden_states=TensorShim(pre_h),
            attention_patterns=TensorShim(pre_a) if pre_a is not None else None,
            layer=self._config.hidden_state_layer,
            input_ids=ids,
        )

    def forward_pass(self, request_id: str) -> ForwardPass:
        self._ensure_loaded()
        state = self._require_state(request_id)
        if state.pending_logits is None:
            self._refresh_state_from_full_context(state)
        return ForwardPass(
            request_id=request_id,
            step=state.step,
            logits=TensorShim(state.pending_logits),
            hidden_states=TensorShim(state.pending_hidden_states)
            if state.pending_hidden_states is not None
            else None,
            attention_patterns=TensorShim(state.pending_attention_patterns[0])
            if state.pending_attention_patterns is not None
            else None,
            layer=self._config.hidden_state_layer,
            input_ids=list(state.input_ids),
        )

    def sample(
        self,
        request_id: str,
        logits: Any,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> Sampled:
        self._ensure_loaded()
        assert self._torch is not None

        state = self._require_state(request_id)
        tensor = _coerce_tensor(logits)
        if isinstance(tensor, np.ndarray):
            tensor = self._torch.from_numpy(tensor).to(self._device)
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)

        if temperature <= 0:
            tok = int(self._torch.argmax(tensor, dim=-1).item())
            return Sampled(request_id=request_id, step=state.step, sampled_token=tok)

        logits_adj = tensor / max(temperature, 1e-5)
        logits_adj = self._top_k_filter(logits_adj, top_k)
        logits_adj = self._top_p_filter(logits_adj, top_p)
        probs = self._torch.softmax(logits_adj, dim=-1)
        sampled = self._torch.multinomial(probs, num_samples=1)
        tok = int(sampled.item())
        return Sampled(request_id=request_id, step=state.step, sampled_token=tok)

    def add_tokens(self, request_id: str, tokens: list[int], forced: bool) -> Added:
        self._ensure_loaded()
        state = self._require_state(request_id)
        assert self._torch is not None

        added = [int(t) for t in tokens]
        event = Added(
            request_id=request_id,
            step=state.step,
            added_tokens=added,
            forced=bool(forced),
        )
        if not added:
            state.step += 1
            return event

        inp = self._torch.tensor([added], dtype=self._torch.long, device=self._device)
        with self._torch.no_grad():
            out = self._model(
                input_ids=inp,
                past_key_values=state.past_key_values,
                use_cache=True,
                output_hidden_states=True,
                output_attentions=bool(self._config.extract_attention),
            )

        layer_h = self._hidden_layer_index(out.hidden_states, self._config.hidden_state_layer)
        layer_a = self._attention_layer_index(out.attentions, self._config.hidden_state_layer)

        state.input_ids.extend(added)
        state.past_key_values = out.past_key_values
        state.pending_logits = out.logits[:, -1, :].detach()
        state.pending_hidden_states = out.hidden_states[layer_h][:, -1, :].detach()
        if out.attentions is not None and layer_a is not None:
            state.pending_attention_patterns = out.attentions[layer_a][:, :, -1:, :].detach()
        else:
            state.pending_attention_patterns = None
        state.step += max(1, len(added))
        return event

    def rewind_kv_cache(self, request_id: str, n: int) -> None:
        self._ensure_loaded()
        state = self._require_state(request_id)
        if n <= 0:
            return
        completion_len = max(0, len(state.input_ids) - state.prompt_len)
        remove_n = min(int(n), completion_len)
        if remove_n <= 0:
            return
        state.input_ids = state.input_ids[: len(state.input_ids) - remove_n]
        state.step = max(0, len(state.input_ids) - state.prompt_len)
        self._refresh_state_from_full_context(state)

    def get_hidden_states(self, request_id: str, layer: int) -> Any:
        state = self._require_state(request_id)
        if layer != self._config.hidden_state_layer:
            self._refresh_state_from_full_context(state, layer_override=layer)
        return TensorShim(state.pending_hidden_states) if state.pending_hidden_states is not None else None

    def get_attention_patterns(self, request_id: str, layer: int) -> Any | None:
        if not self._config.extract_attention:
            return None
        state = self._require_state(request_id)
        if layer != self._config.hidden_state_layer:
            self._refresh_state_from_full_context(state, layer_override=layer)
        if state.pending_attention_patterns is None:
            return None
        return TensorShim(state.pending_attention_patterns[0])

    def get_input_ids(self, request_id: str) -> list[int]:
        return list(self._require_state(request_id).input_ids)

    def get_completion_ids(self, request_id: str) -> list[int]:
        state = self._require_state(request_id)
        return list(state.input_ids[state.prompt_len :])

    def decode(self, token_ids: list[int]) -> str:
        self._ensure_loaded()
        try:
            return str(self._tokenizer.decode(token_ids, skip_special_tokens=True))
        except Exception:
            return ""

    def eos_token_id(self) -> int | None:
        self._ensure_loaded()
        eid = getattr(self._tokenizer, "eos_token_id", None)
        return int(eid) if isinstance(eid, int) else None

    def shutdown(self) -> None:
        self._states.clear()
        self._model = None
        self._tokenizer = None
        if self._torch is not None and self._device is not None:
            try:
                if str(self._device).startswith("cuda"):
                    self._torch.cuda.empty_cache()
            except Exception:
                pass

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._tokenizer is not None:
            return
        self.load_model(self._model_id, self._config)

    def _require_state(self, request_id: str) -> _RequestState:
        state = self._states.get(request_id)
        if state is None:
            raise KeyError(f"Request state not found for request_id={request_id!r}")
        return state

    def _refresh_state_from_full_context(
        self,
        state: _RequestState,
        *,
        layer_override: int | None = None,
    ) -> None:
        assert self._torch is not None
        layer = self._config.hidden_state_layer if layer_override is None else int(layer_override)
        inp = self._torch.tensor([state.input_ids], dtype=self._torch.long, device=self._device)
        with self._torch.no_grad():
            out = self._model(
                input_ids=inp,
                use_cache=True,
                output_hidden_states=True,
                output_attentions=bool(self._config.extract_attention),
            )
        layer_h = self._hidden_layer_index(out.hidden_states, layer)
        layer_a = self._attention_layer_index(out.attentions, layer)
        state.past_key_values = out.past_key_values
        state.pending_logits = out.logits[:, -1, :].detach()
        state.pending_hidden_states = out.hidden_states[layer_h][:, -1, :].detach()
        if out.attentions is not None and layer_a is not None:
            state.pending_attention_patterns = out.attentions[layer_a][:, :, -1:, :].detach()
        else:
            state.pending_attention_patterns = None

    @staticmethod
    def _resolve_device(torch: Any, device: str) -> Any:
        if device == "auto":
            if torch.backends.mps.is_available():
                return torch.device("mps")
            if torch.cuda.is_available():
                return torch.device("cuda")
            return torch.device("cpu")
        return torch.device(device)

    @staticmethod
    def _resolve_dtype(torch: Any, dtype: str, device: Any) -> Any:
        if dtype != "auto":
            return getattr(torch, dtype, torch.float32)
        d = str(device)
        if d.startswith("cuda"):
            return torch.float16
        return torch.float32

    @staticmethod
    def _hidden_layer_index(hidden_states: Any, layer: int) -> int:
        if hidden_states is None:
            return 0
        # hidden_states[0] is embedding output; transformer layer N is index N+1
        idx = int(layer) + 1
        return max(0, min(idx, len(hidden_states) - 1))

    @staticmethod
    def _attention_layer_index(attentions: Any, layer: int) -> int | None:
        if attentions is None:
            return None
        idx = int(layer)
        return max(0, min(idx, len(attentions) - 1))

    def _top_k_filter(self, logits: Any, top_k: int) -> Any:
        assert self._torch is not None
        if top_k <= 0:
            return logits
        k = min(int(top_k), int(logits.shape[-1]))
        if k <= 0:
            return logits
        vals, _ = self._torch.topk(logits, k, dim=-1)
        threshold = vals[..., -1, None]
        return self._torch.where(
            logits < threshold,
            self._torch.full_like(logits, float("-inf")),
            logits,
        )

    def _top_p_filter(self, logits: Any, top_p: float) -> Any:
        assert self._torch is not None
        if top_p >= 1.0 or top_p <= 0.0:
            return logits

        sorted_logits, sorted_idx = self._torch.sort(logits, descending=True, dim=-1)
        sorted_probs = self._torch.softmax(sorted_logits, dim=-1)
        cumulative = sorted_probs.cumsum(dim=-1)
        cutoff = cumulative > float(top_p)
        cutoff[..., 0] = False
        filtered_sorted_logits = sorted_logits.masked_fill(cutoff, float("-inf"))
        filtered = self._torch.full_like(logits, float("-inf"))
        filtered.scatter_(dim=-1, index=sorted_idx, src=filtered_sorted_logits)
        return filtered

