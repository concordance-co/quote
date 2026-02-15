"""Unified mechanistic interpretability package.

This package includes optional/heavy dependencies (e.g. torch). Keep imports lazy
so lightweight deployments can still import other Quote modules without failing
at import-time.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "FeatureExtractor",
    "get_feature_extractor",
    "NeuronpediaClient",
    "MinimalSAEExtractor",
    "SAELoader",
    "get_sae_loader",
]


def __getattr__(name: str) -> Any:  # pragma: no cover - exercised via import machinery
    if name == "FeatureExtractor":
        from .feature_extractor import FeatureExtractor

        return FeatureExtractor
    if name == "get_feature_extractor":
        from .feature_extractor import get_feature_extractor

        return get_feature_extractor
    if name == "NeuronpediaClient":
        from .neuronpedia import NeuronpediaClient

        return NeuronpediaClient
    if name == "MinimalSAEExtractor":
        from .sae_extract import MinimalSAEExtractor

        return MinimalSAEExtractor
    if name == "SAELoader":
        from .sae_loader import SAELoader

        return SAELoader
    if name == "get_sae_loader":
        from .sae_loader import get_sae_loader

        return get_sae_loader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover - debug helper
    return sorted(set(list(globals().keys()) + __all__))
