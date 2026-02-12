from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from quote.activations.schema import FeatureActivationRow
from quote.backends.interface import SAEConfig
from quote.backends.huggingface import TensorShim

logger = logging.getLogger(__name__)


class MinimalSAEExtractor:
    """Minimal SAE encoder for top-k feature extraction."""

    def __init__(self, config: SAEConfig) -> None:
        self._config = config
        self._sae = None
        self._torch = None
        self._device = None

    @property
    def enabled(self) -> bool:
        return bool(self._config.enabled)

    @property
    def mode(self) -> str:
        return str(self._config.mode)

    def extract_top_k(
        self,
        *,
        hidden_states: Any,
        request_id: str,
        step: int,
        token_position: int,
        token_id: int | None,
        model_id: str,
        source_mode: str | None = None,
    ) -> list[FeatureActivationRow]:
        if not self.enabled:
            return []
        try:
            sae = self._ensure_loaded()
            if sae is None:
                return []
            assert self._torch is not None
            vec = self._coerce_hidden_vector(hidden_states)
            if vec is None:
                return []
            vec = self._align_vec_to_sae_device(vec, sae)
            with self._torch.no_grad():
                encoded = sae.encode(vec.unsqueeze(0))
            top_k = min(max(1, int(self._config.top_k)), int(encoded.shape[-1]))
            vals, idx = self._torch.topk(encoded[0], k=top_k)
            rows: list[FeatureActivationRow] = []
            for rank, (feat_idx, feat_val) in enumerate(zip(idx.tolist(), vals.tolist()), start=1):
                if float(feat_val) <= 0:
                    continue
                rows.append(
                    FeatureActivationRow.new(
                        request_id=request_id,
                        step=step,
                        token_position=token_position,
                        token_id=token_id,
                        sae_release=self._config.sae_id,
                        sae_layer=self._config.layer,
                        feature_id=int(feat_idx),
                        activation_value=float(feat_val),
                        rank=rank,
                        source_mode=source_mode or self.mode,
                        model_id=model_id,
                    )
                )
            return rows
        except Exception:
            logger.exception("SAE extraction failed; continuing without feature rows")
            return []

    def _ensure_loaded(self):
        if self._sae is not None:
            return self._sae
        try:
            import torch
        except Exception:
            logger.warning("torch unavailable; SAE extractor disabled")
            return None
        self._torch = torch
        self._device = self._select_default_device(torch)
        try:
            from sae_lens import SAE
        except Exception:
            logger.warning("sae_lens unavailable; SAE extractor disabled")
            return None
        hook_name = self._resolve_hook_name(self._config.sae_id, self._config.layer)
        local_path = self._resolve_local_sae_path(hook_name)
        if local_path is not None:
            logger.info("Loading SAE from local path: %s", local_path)
            self._sae = SAE.load_from_disk(str(local_path), device=str(self._device))
            return self._sae

        loaded = SAE.from_pretrained(
            release=self._config.sae_id,
            sae_id=hook_name,
            device=str(self._device),
        )
        # Newer sae-lens returns only SAE; older variants may return tuples.
        self._sae = loaded[0] if isinstance(loaded, tuple) else loaded
        return self._sae

    @staticmethod
    def _select_default_device(torch: Any) -> Any:
        if torch.cuda.is_available():
            return torch.device("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    def _align_vec_to_sae_device(self, vec: Any, sae: Any) -> Any:
        if self._torch is None:
            return vec
        target = None
        try:
            target = next(sae.parameters()).device
        except Exception:
            target = self._device
        if target is None:
            return vec
        try:
            return vec.to(target)
        except Exception:
            return vec

    def _resolve_local_sae_path(self, hook_name: str) -> Path | None:
        raw = getattr(self._config, "sae_local_path", None)
        if raw is None:
            return None
        base = Path(str(raw)).expanduser()
        candidates = [base, base / hook_name]
        for candidate in candidates:
            if self._is_sae_dir(candidate):
                return candidate
        logger.warning(
            "CONCORDANCE_SAE_LOCAL_PATH set but no SAE files found under %s (checked direct and %s subdir)",
            base,
            hook_name,
        )
        return None

    @staticmethod
    def _is_sae_dir(path: Path) -> bool:
        return (
            path.exists()
            and path.is_dir()
            and (path / "cfg.json").is_file()
            and (path / "sae_weights.safetensors").is_file()
        )

    @staticmethod
    def _resolve_hook_name(sae_release: str, layer: int) -> str:
        # LlamaScope convention: l{layer}r_8x (residual stream).
        if "_8x" in sae_release:
            return f"l{int(layer)}r_8x"
        if "_16x" in sae_release:
            return f"l{int(layer)}r_16x"
        if "_32x" in sae_release:
            return f"l{int(layer)}r_32x"
        return f"l{int(layer)}r_8x"

    def _coerce_hidden_vector(self, hidden_states: Any) -> Any | None:
        if hidden_states is None:
            return None
        if isinstance(hidden_states, TensorShim):
            hidden_states = hidden_states._tensor

        if self._torch is None:
            try:
                import torch
            except Exception:
                return None
            self._torch = torch

        torch = self._torch
        if isinstance(hidden_states, np.ndarray):
            tensor = torch.from_numpy(hidden_states)
        elif hasattr(hidden_states, "detach"):
            tensor = hidden_states.detach()
        else:
            tensor = torch.as_tensor(hidden_states)

        if tensor.ndim == 3:
            # (batch, seq, hidden)
            tensor = tensor[0, -1, :]
        elif tensor.ndim == 2:
            # (seq, hidden) or (1, hidden)
            tensor = tensor[-1, :]
        elif tensor.ndim != 1:
            return None

        if self._device is not None:
            tensor = tensor.to(self._device)
        return tensor
