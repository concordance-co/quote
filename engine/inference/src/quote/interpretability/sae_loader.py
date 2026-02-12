"""Compatibility shim for legacy quote.interpretability.sae_loader imports."""

from quote.interp.sae_loader import SAELoader, get_sae_loader

__all__ = ["SAELoader", "get_sae_loader"]
