from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from shared.types import Added, ForwardPass, Prefilled, Sampled


@dataclass
class BackendConfig:
    backend_type: str = "huggingface"
    model_id: str = "meta-llama/Llama-3.1-8B-Instruct"
    device: str = "auto"
    hidden_state_layer: int = 16
    dtype: str = "auto"
    extract_attention: bool = True


@dataclass
class GenerationConfig:
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    stop_tokens: list[int] | None = None


@dataclass
class ActivationConfig:
    enabled: bool = True
    db_path: str = "./artifacts/activations/activations.duckdb"
    parquet_path: str = "./artifacts/activations/parquet"
    retention_days: int = 14


@dataclass
class SAEConfig:
    enabled: bool = True
    mode: str = "nearline"  # nearline|inline
    sae_id: str = "llama_scope_lxr_8x"
    layer: int = 16
    top_k: int = 20
    sae_local_path: str | None = None


class Backend(Protocol):
    def load_model(self, model_id: str, config: BackendConfig) -> None: ...

    def tokenizer(self) -> Any: ...

    def prefill(self, request_id: str, input_ids: list[int], max_steps: int) -> Prefilled: ...

    def forward_pass(self, request_id: str) -> ForwardPass: ...

    def sample(
        self,
        request_id: str,
        logits: Any,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> Sampled: ...

    def add_tokens(self, request_id: str, tokens: list[int], forced: bool) -> Added: ...

    def rewind_kv_cache(self, request_id: str, n: int) -> None: ...

    def get_hidden_states(self, request_id: str, layer: int) -> Any: ...

    def get_attention_patterns(self, request_id: str, layer: int) -> Any | None: ...

    def get_input_ids(self, request_id: str) -> list[int]: ...

    def get_completion_ids(self, request_id: str) -> list[int]: ...

    def decode(self, token_ids: list[int]) -> str: ...

    def eos_token_id(self) -> int | None: ...

    def shutdown(self) -> None: ...
