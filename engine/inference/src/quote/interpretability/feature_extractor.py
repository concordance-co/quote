"""
Feature Extractor for post-hoc SAE analysis of token sequences.

Runs a HuggingFace model forward pass on token sequences to extract
hidden states, then encodes them with an SAE to get feature activations.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import torch

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """
    Extract SAE feature activations from token sequences.

    This class performs post-hoc analysis by:
    1. Running a HuggingFace model forward pass on tokens
    2. Extracting hidden states at a specified layer
    3. Encoding hidden states with an SAE to get sparse features
    """

    def __init__(
        self,
        model_id: str = "meta-llama/Llama-3.1-8B-Instruct",
        sae_id: str = "llama_scope_lxr_8x",
        layer: int = 16,
        device: str | None = None,
    ):
        self.model_id = model_id
        self.sae_id = sae_id
        self.layer = layer
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        self._hf_model = None
        self._tokenizer = None
        self._sae_loader = None

    def _ensure_loaded(self) -> None:
        """Lazy load the HF model and SAE."""
        if self._hf_model is not None:
            return

        logger.info(f"Loading HuggingFace model: {self.model_id}")

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # Load tokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                trust_remote_code=True,
            )

            # Load model with output_hidden_states enabled
            self._hf_model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None,
                trust_remote_code=True,
            )

            if self.device != "cuda":
                self._hf_model = self._hf_model.to(self.device)

            self._hf_model.eval()
            logger.info(f"HF model loaded successfully on {self.device}")

        except Exception as e:
            logger.error(f"Failed to load HF model: {e}")
            raise

        # Load SAE
        try:
            from .sae_loader import get_sae_loader

            self._sae_loader = get_sae_loader(sae_id=self.sae_id, layer=self.layer)
            logger.info(f"SAE loader initialized for layer {self.layer}")
        except Exception as e:
            logger.error(f"Failed to initialize SAE loader: {e}")
            raise

    def extract_timeline(
        self,
        tokens: list[int],
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Extract feature timeline for a sequence of tokens.

        Args:
            tokens: List of token IDs
            top_k: Number of top features to return per position

        Returns:
            List of dicts with structure:
            [
                {
                    "position": 0,
                    "token": 123,
                    "token_str": "Hello",
                    "top_features": [(feature_id, activation), ...]
                },
                ...
            ]
        """
        self._ensure_loaded()

        if not tokens:
            return []

        # Convert to tensor
        input_ids = torch.tensor([tokens], device=self.device)

        # Forward pass to get hidden states
        with torch.no_grad():
            outputs = self._hf_model(
                input_ids=input_ids,
                output_hidden_states=True,
            )

        # Extract hidden states at the target layer
        # hidden_states is a tuple of (num_layers + 1) tensors, each (batch, seq, hidden)
        # Index 0 is embeddings, then layers 1..num_layers
        hidden_states = outputs.hidden_states[self.layer + 1]  # +1 because index 0 is embeddings
        hidden = hidden_states[0]  # Remove batch dimension: (seq_len, hidden_dim)

        # SAE encode to get features
        features = self._sae_loader.encode(hidden)  # (seq_len, n_features)

        # Get top-k features per position
        top_k_features = self._sae_loader.get_top_k_features(features, k=top_k)

        # Build timeline with token strings
        timeline = []
        for pos in range(len(tokens)):
            token_id = tokens[pos]

            # Decode token to string
            try:
                token_str = self._tokenizer.decode([token_id])
            except Exception:
                token_str = f"<{token_id}>"

            timeline.append({
                "position": pos,
                "token": token_id,
                "token_str": token_str,
                "top_features": [
                    {"id": feat_id, "activation": activation}
                    for feat_id, activation in top_k_features[pos]
                ],
            })

        return timeline

    def extract_comparison(
        self,
        tokens: list[int],
        injection_positions: list[int],
        context_window: int = 1,
        top_k: int = 20,
    ) -> dict[str, Any]:
        """
        Extract before/after feature comparison at injection points.

        Args:
            tokens: List of token IDs
            injection_positions: List of positions where injections occurred
            context_window: Number of positions before/after to include
            top_k: Number of top features per position

        Returns:
            Dict with injection comparisons:
            {
                "comparisons": [
                    {
                        "position": 5,
                        "before": {"position": 4, "token": ..., "top_features": [...]},
                        "injection": {"position": 5, "token": ..., "top_features": [...]},
                        "after": {"position": 6, "token": ..., "top_features": [...]}
                    },
                    ...
                ]
            }
        """
        # Get full timeline
        timeline = self.extract_timeline(tokens, top_k=top_k)

        comparisons = []
        for inj_pos in injection_positions:
            if inj_pos < 0 or inj_pos >= len(timeline):
                continue

            comparison = {
                "position": inj_pos,
                "injection": timeline[inj_pos],
            }

            # Add before context
            if inj_pos > 0:
                before_entries = []
                for offset in range(context_window, 0, -1):
                    before_pos = inj_pos - offset
                    if before_pos >= 0:
                        before_entries.append(timeline[before_pos])
                comparison["before"] = before_entries if len(before_entries) > 1 else (before_entries[0] if before_entries else None)

            # Add after context
            if inj_pos < len(timeline) - 1:
                after_entries = []
                for offset in range(1, context_window + 1):
                    after_pos = inj_pos + offset
                    if after_pos < len(timeline):
                        after_entries.append(timeline[after_pos])
                comparison["after"] = after_entries if len(after_entries) > 1 else (after_entries[0] if after_entries else None)

            comparisons.append(comparison)

        return {"comparisons": comparisons}


# Global singleton for reuse
_feature_extractor: FeatureExtractor | None = None


def get_feature_extractor(
    model_id: str = "meta-llama/Llama-3.1-8B-Instruct",
    sae_id: str = "llama_scope_lxr_8x",
    layer: int = 16,
) -> FeatureExtractor:
    """Get or create a singleton feature extractor."""
    global _feature_extractor

    if (
        _feature_extractor is None
        or _feature_extractor.model_id != model_id
        or _feature_extractor.sae_id != sae_id
        or _feature_extractor.layer != layer
    ):
        _feature_extractor = FeatureExtractor(
            model_id=model_id,
            sae_id=sae_id,
            layer=layer,
        )

    return _feature_extractor
