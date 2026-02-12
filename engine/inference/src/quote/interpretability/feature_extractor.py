"""Compatibility shim for legacy quote.interpretability.feature_extractor imports."""

from quote.interp.feature_extractor import FeatureExtractor, get_feature_extractor

__all__ = ["FeatureExtractor", "get_feature_extractor"]
