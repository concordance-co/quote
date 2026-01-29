"""
SAE (Sparse Autoencoder) loader for feature extraction.

Loads pre-trained SAEs from EleutherAI for Llama models.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import torch

logger = logging.getLogger(__name__)


class SAELoader:
    """Lazy loader for Sparse Autoencoders."""

    def __init__(
        self,
        sae_id: str = "llama_scope_lxr_8x",
        layer: int = 16,
        device: str | None = None,
    ):
        self.sae_id = sae_id
        self.layer = layer
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._sae = None
        self._cfg = None

    def _ensure_loaded(self) -> None:
        """Lazy load the SAE model."""
        if self._sae is not None:
            return

        logger.info(f"Loading SAE from {self.sae_id} (layer {self.layer})")

        try:
            from sae_lens import SAE

            # Load the SAE for the specified layer
            # LlamaScope 8x SAEs use format like "l{layer}r_8x" for residual stream
            # Using 8x (32K features) instead of 32x (128K) because 8x is on Neuronpedia
            hook_name = f"l{self.layer}r_8x"

            self._sae, self._cfg, _ = SAE.from_pretrained(
                release=self.sae_id,
                sae_id=hook_name,
                device=self.device,
            )
            logger.info(f"SAE loaded successfully: {self._sae}")

        except ImportError:
            logger.warning(
                "sae_lens not installed. Install with: pip install sae-lens"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to load SAE: {e}")
            raise

    @property
    def sae(self) -> Any:
        """Get the loaded SAE model."""
        self._ensure_loaded()
        return self._sae

    @property
    def cfg(self) -> Any:
        """Get the SAE configuration."""
        self._ensure_loaded()
        return self._cfg

    def encode(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Encode hidden states to SAE feature activations.

        Args:
            hidden_states: Tensor of shape (batch, seq_len, hidden_dim) or (seq_len, hidden_dim)

        Returns:
            Tensor of feature activations with shape (batch, seq_len, n_features) or (seq_len, n_features)
        """
        self._ensure_loaded()

        # Ensure input is on the correct device
        hidden_states = hidden_states.to(self.device)

        with torch.no_grad():
            # SAE encode expects (batch, hidden_dim) so we may need to reshape
            original_shape = hidden_states.shape

            if len(original_shape) == 3:
                # (batch, seq, hidden) -> (batch * seq, hidden)
                batch, seq_len, hidden_dim = original_shape
                hidden_flat = hidden_states.reshape(-1, hidden_dim)
                features = self._sae.encode(hidden_flat)
                # Reshape back to (batch, seq, n_features)
                features = features.reshape(batch, seq_len, -1)
            elif len(original_shape) == 2:
                # (seq, hidden) -> process directly
                features = self._sae.encode(hidden_states)
            else:
                raise ValueError(f"Unexpected hidden_states shape: {original_shape}")

        return features

    def get_top_k_features(
        self,
        features: torch.Tensor,
        k: int = 20,
    ) -> list[list[tuple[int, float]]]:
        """
        Get top-k activated features for each position.

        Args:
            features: Tensor of shape (seq_len, n_features)
            k: Number of top features to return per position

        Returns:
            List of lists, where each inner list contains (feature_id, activation) tuples
        """
        top_k_per_position = []

        for pos in range(features.shape[0]):
            pos_features = features[pos]

            # Get top k values and indices
            top_values, top_indices = torch.topk(pos_features, min(k, pos_features.shape[0]))

            top_k = [
                (int(idx.item()), float(val.item()))
                for idx, val in zip(top_indices, top_values)
                if val.item() > 0  # Only include non-zero activations
            ]

            top_k_per_position.append(top_k)

        return top_k_per_position


# Global singleton for reuse
_sae_loader: SAELoader | None = None


def get_sae_loader(
    sae_id: str = "llama_scope_lxr_8x",
    layer: int = 16,
) -> SAELoader:
    """Get or create a singleton SAE loader."""
    global _sae_loader

    if _sae_loader is None or _sae_loader.sae_id != sae_id or _sae_loader.layer != layer:
        _sae_loader = SAELoader(sae_id=sae_id, layer=layer)

    return _sae_loader
