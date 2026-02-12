from __future__ import annotations

import os

from .backends import ActivationConfig, Backend, BackendConfig, GenerationConfig, SAEConfig


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def default_backend_config() -> BackendConfig:
    model = (
        os.environ.get("CONCORDANCE_MODEL")
        or os.environ.get("MODEL_ID")
        or "meta-llama/Llama-3.1-8B-Instruct"
    )
    return BackendConfig(
        backend_type=os.environ.get("CONCORDANCE_BACKEND", "huggingface"),
        model_id=model,
        device=os.environ.get("CONCORDANCE_DEVICE", "auto"),
        hidden_state_layer=_env_int("CONCORDANCE_HIDDEN_LAYER", 16),
        dtype=os.environ.get("CONCORDANCE_DTYPE", "auto"),
        extract_attention=_env_bool("CONCORDANCE_EXTRACT_ATTENTION", True),
    )


def default_generation_config() -> GenerationConfig:
    return GenerationConfig(
        max_tokens=_env_int("CONCORDANCE_MAX_TOKENS", 2048),
        temperature=_env_float("CONCORDANCE_TEMPERATURE", 0.7),
        top_p=_env_float("CONCORDANCE_TOP_P", 0.9),
        top_k=_env_int("CONCORDANCE_TOP_K", 50),
    )


def default_activation_config() -> ActivationConfig:
    return ActivationConfig(
        enabled=_env_bool("CONCORDANCE_ACTIVATIONS_ENABLED", True),
        db_path=os.environ.get(
            "CONCORDANCE_ACTIVATIONS_DB_PATH",
            "./artifacts/activations/activations.duckdb",
        ),
        parquet_path=os.environ.get(
            "CONCORDANCE_ACTIVATIONS_PARQUET_PATH",
            "./artifacts/activations/parquet",
        ),
        retention_days=_env_int("CONCORDANCE_ACTIVATION_RETENTION_DAYS", 14),
    )


def default_sae_config() -> SAEConfig:
    return SAEConfig(
        enabled=_env_bool("CONCORDANCE_SAE_ENABLED", True),
        mode=os.environ.get("CONCORDANCE_SAE_MODE", "nearline"),
        sae_id=os.environ.get("CONCORDANCE_SAE_ID", "llama_scope_lxr_8x"),
        layer=_env_int("CONCORDANCE_SAE_LAYER", 16),
        top_k=_env_int("CONCORDANCE_SAE_TOP_K", 20),
        sae_local_path=os.environ.get("CONCORDANCE_SAE_LOCAL_PATH"),
    )


def create_backend(config: BackendConfig | None = None) -> Backend:
    cfg = config or default_backend_config()
    if cfg.backend_type != "huggingface":
        raise ValueError(f"Unsupported backend_type={cfg.backend_type!r}")
    from .backends.huggingface import HuggingFaceBackend

    return HuggingFaceBackend(cfg)
