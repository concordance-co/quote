"""Runtime orchestration for generation and config."""

from .config import default_activation_config, default_sae_config
from .generation import GenerationResult, generate

__all__ = ["GenerationResult", "generate", "default_activation_config", "default_sae_config"]
