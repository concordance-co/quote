"""
Standalone HF inference server for activations playground.

FastAPI app that runs meta-llama/Llama-3.1-8B-Instruct via the
quote.backends.huggingface.HuggingFaceBackend for text generation, with
true inline SAE feature extraction via quote.runtime.generation.generate()
and MinimalSAEExtractor.

Endpoints:
  POST /hf/generate — generation with optional inline SAE (inline_sae toggle)
  POST /hf/extract  — post-hoc SAE on token IDs (forward pass + SAE, no generation)
  GET  /health      — health check with SAE status
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL_ID = os.environ.get("CONCORDANCE_MODEL") or "meta-llama/Llama-3.1-8B-Instruct"
MAX_TOKENS_LIMIT = 2048
MAX_PROMPT_CHARS = 12000


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class HFGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_PROMPT_CHARS)
    max_tokens: int = Field(default=512, ge=1, le=MAX_TOKENS_LIMIT)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int = Field(default=1, ge=0)

    # Inline SAE extraction options
    inline_sae: bool = Field(default=True, description="Run SAE feature extraction during generation")
    sae_id: str = Field(default="llama_scope_lxr_8x", description="SAE release ID on HuggingFace")
    sae_layer: int = Field(default=16, ge=0, description="Transformer layer for hidden state extraction")
    sae_top_k: int = Field(default=20, ge=1, description="Number of top SAE features per position")
    sae_local_path: str | None = Field(
        default=None,
        description="Local path to pre-downloaded SAE weights (overrides sae_id download)",
    )


class HFGenerateResponse(BaseModel):
    request_id: str
    model_id: str
    output_text: str
    output_token_ids: list[int]
    feature_timeline: list[dict] = Field(default_factory=list)


class HFExtractRequest(BaseModel):
    token_ids: list[int] = Field(..., min_length=1)
    sae_id: str = Field(default="llama_scope_lxr_8x")
    sae_layer: int = Field(default=16, ge=0)
    sae_top_k: int = Field(default=20, ge=1)
    sae_local_path: str | None = Field(default=None)


class HFExtractResponse(BaseModel):
    feature_timeline: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Lazy runtime singleton (mirrors fullpass_debug.py's _FullpassRuntime)
# ---------------------------------------------------------------------------


class _HFRuntime:
    """Loads model + SAE once per container and serves generation / extraction."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._backend: Any = None
        self._backend_cfg: Any = None
        self._tokenizer: Any = None
        self._sae_extractor: Any = None
        self._sae_key: tuple[str, int, str | None] = ("", -1, None)

    def _ensure_backend(self, model_id: str | None = None) -> None:
        from quote.backends.huggingface import HuggingFaceBackend
        from quote.backends.interface import BackendConfig
        from quote.runtime.config import default_backend_config

        with self._lock:
            cfg = default_backend_config()
            if model_id:
                cfg = BackendConfig(
                    backend_type=cfg.backend_type,
                    model_id=model_id,
                    device=cfg.device,
                    hidden_state_layer=cfg.hidden_state_layer,
                    dtype=cfg.dtype,
                    extract_attention=cfg.extract_attention,
                )

            if (
                self._backend is not None
                and self._backend_cfg is not None
                and self._backend_cfg.model_id == cfg.model_id
            ):
                return

            if self._backend is not None:
                try:
                    self._backend.shutdown()
                except Exception:
                    pass

            logger.info(
                "HF runtime loading model=%s device=%s layer=%s dtype=%s",
                cfg.model_id, cfg.device, cfg.hidden_state_layer, cfg.dtype,
            )
            backend = HuggingFaceBackend(cfg)
            backend.load_model(cfg.model_id, cfg)
            self._backend = backend
            self._backend_cfg = cfg
            self._tokenizer = backend.tokenizer()

    def _ensure_sae(
        self,
        sae_id: str,
        sae_layer: int,
        sae_top_k: int,
        sae_local_path: str | None = None,
    ) -> Any:
        from quote.backends.interface import SAEConfig
        from quote.interp.sae_extract import MinimalSAEExtractor

        effective_path = sae_local_path or os.environ.get("CONCORDANCE_SAE_LOCAL_PATH")
        key = (sae_id, sae_layer, effective_path)
        if self._sae_extractor is not None and self._sae_key == key:
            # Update top_k if changed (lightweight)
            self._sae_extractor._config.top_k = sae_top_k
            return self._sae_extractor

        sae_cfg = SAEConfig(
            enabled=True,
            mode="inline",
            sae_id=sae_id,
            layer=sae_layer,
            top_k=sae_top_k,
            sae_local_path=effective_path,
        )
        self._sae_extractor = MinimalSAEExtractor(sae_cfg)
        self._sae_key = key
        return self._sae_extractor

    def generate(self, req: HFGenerateRequest) -> HFGenerateResponse:
        from quote.backends.interface import GenerationConfig
        from quote.runtime.generation import generate as runtime_generate
        from quote.mods.manager import ModManager

        self._ensure_backend()
        assert self._backend is not None
        assert self._tokenizer is not None

        request_id = f"hf-{uuid.uuid4().hex[:12]}"

        # Encode prompt using chat template
        input_ids = _encode_prompt(self._tokenizer, req.prompt)

        gen_cfg = GenerationConfig(
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            top_k=req.top_k,
        )

        sae_extractor = None
        if req.inline_sae:
            sae_extractor = self._ensure_sae(
                sae_id=req.sae_id,
                sae_layer=req.sae_layer,
                sae_top_k=req.sae_top_k,
                sae_local_path=req.sae_local_path,
            )

        mod_manager = ModManager([], tokenizer=self._tokenizer)
        result = runtime_generate(
            backend=self._backend,
            input_ids=input_ids,
            request_id=request_id,
            mod_manager=mod_manager,
            config=gen_cfg,
            activation_store=None,
            sae_extractor=sae_extractor,
        )

        # Build feature_timeline from the generation events
        feature_timeline: list[dict] = []
        if req.inline_sae and sae_extractor is not None:
            feature_timeline = self._build_timeline_from_generation(
                input_ids=input_ids,
                result=result,
                sae_extractor=sae_extractor,
                request_id=request_id,
            )

        # output_token_ids = full sequence (prompt + completion)
        full_ids = input_ids + result.output_ids

        return HFGenerateResponse(
            request_id=request_id,
            model_id=self._backend_cfg.model_id if self._backend_cfg else MODEL_ID,
            output_text=result.output_text,
            output_token_ids=full_ids,
            feature_timeline=feature_timeline,
        )

    def _build_timeline_from_generation(
        self,
        *,
        input_ids: list[int],
        result: Any,
        sae_extractor: Any,
        request_id: str,
    ) -> list[dict]:
        """Build feature_timeline by doing a post-generation forward pass for prefill tokens
        and collecting inline SAE results from generation steps.

        The runtime.generate() loop only extracts SAE for *generation* steps (ForwardPass events),
        not the prefill. For a complete timeline covering all positions, we do a full
        forward pass on the complete sequence through _extract_full_timeline.
        """
        full_ids = input_ids + result.output_ids
        return self._extract_full_timeline(
            token_ids=full_ids,
            sae_extractor=sae_extractor,
            request_id=request_id,
        )

    def _extract_full_timeline(
        self,
        *,
        token_ids: list[int],
        sae_extractor: Any,
        request_id: str,
    ) -> list[dict]:
        """Run a single forward pass over all tokens and extract SAE features at each position."""
        assert self._backend is not None
        assert self._tokenizer is not None

        import torch
        model = self._backend._model
        device = self._backend._device
        layer = sae_extractor._config.layer

        input_tensor = torch.tensor([token_ids], dtype=torch.long, device=device)
        with torch.no_grad():
            outputs = model(
                input_ids=input_tensor,
                output_hidden_states=True,
            )

        # hidden_states[0] is embedding output; layer N is at index N+1
        layer_idx = min(layer + 1, len(outputs.hidden_states) - 1)
        hidden = outputs.hidden_states[layer_idx]  # (1, seq_len, hidden_dim)

        timeline: list[dict] = []
        for pos in range(len(token_ids)):
            vec = hidden[0, pos, :]  # (hidden_dim,)
            rows = sae_extractor.extract_top_k(
                hidden_states=vec,
                request_id=request_id,
                step=pos,
                token_position=pos,
                token_id=token_ids[pos],
                model_id=self._backend_cfg.model_id if self._backend_cfg else MODEL_ID,
                source_mode="inline",
            )

            top_features = [
                {"id": int(r.feature_id), "activation": round(float(r.activation_value), 4)}
                for r in rows
            ]

            token_id = token_ids[pos]
            try:
                token_str = self._tokenizer.decode([token_id])
            except Exception:
                token_str = f"<{token_id}>"

            timeline.append({
                "position": pos,
                "token": token_id,
                "token_str": token_str,
                "top_features": top_features,
            })

        return timeline

    def extract(self, req: HFExtractRequest) -> HFExtractResponse:
        """Post-hoc SAE extraction: forward pass on token IDs, no generation."""
        self._ensure_backend()

        sae_extractor = self._ensure_sae(
            sae_id=req.sae_id,
            sae_layer=req.sae_layer,
            sae_top_k=req.sae_top_k,
            sae_local_path=req.sae_local_path,
        )

        request_id = f"hf-extract-{uuid.uuid4().hex[:12]}"
        timeline = self._extract_full_timeline(
            token_ids=req.token_ids,
            sae_extractor=sae_extractor,
            request_id=request_id,
        )

        return HFExtractResponse(feature_timeline=timeline)

    @property
    def is_loaded(self) -> bool:
        return self._backend is not None

    @property
    def sae_loaded(self) -> bool:
        return self._sae_extractor is not None


# ---------------------------------------------------------------------------
# Helper: encode prompt with chat template
# ---------------------------------------------------------------------------


def _encode_prompt(tokenizer: Any, prompt: str) -> list[int]:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            maybe_ids = tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            if hasattr(maybe_ids, "tolist"):
                maybe_ids = maybe_ids.tolist()
            if isinstance(maybe_ids, list) and maybe_ids:
                return [int(t) for t in maybe_ids]
        except Exception:
            pass
    return [int(t) for t in tokenizer.encode(prompt, add_special_tokens=True)]


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_runtime: _HFRuntime | None = None


def _get_runtime() -> _HFRuntime:
    global _runtime
    if _runtime is None:
        _runtime = _HFRuntime()
    return _runtime


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_hf_inference_app() -> FastAPI:
    """Create and return a standalone FastAPI app for HF inference."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        rt = _get_runtime()
        rt._ensure_backend()  # eagerly load model at container start
        yield

    app = FastAPI(title="HF Inference Server", lifespan=lifespan)

    @app.get("/health")
    async def health():
        rt = _get_runtime()
        return {
            "status": "ok" if rt.is_loaded else "loading",
            "service": "hf-inference",
            "model_id": MODEL_ID,
            "sae_loaded": rt.sae_loaded,
        }

    @app.post("/hf/generate", response_model=HFGenerateResponse)
    async def hf_generate(req: HFGenerateRequest):
        rt = _get_runtime()
        try:
            return rt.generate(req)
        except Exception as e:
            logger.exception("Generation failed")
            raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    @app.post("/hf/extract", response_model=HFExtractResponse)
    async def hf_extract(req: HFExtractRequest):
        rt = _get_runtime()
        try:
            return rt.extract(req)
        except Exception as e:
            logger.exception("Extraction failed")
            raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    return app
