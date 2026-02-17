"""
Standalone HF inference server for activations playground.

Lightweight FastAPI app that runs meta-llama/Llama-3.1-8B-Instruct
via HuggingFace transformers for text generation. Optionally performs
inline SAE feature extraction via sae-lens, returning a feature_timeline
alongside generation output.

This module intentionally avoids importing quote.backends, quote.runtime,
quote.storage, or quote.mods to prevent the dependency chain that caused
staging deploy crashes.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
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

    # Inline SAE extraction options
    inline_sae: bool = Field(default=True, description="Run SAE feature extraction after generation")
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


# ---------------------------------------------------------------------------
# Lazy SAE singleton (self-contained, uses sae-lens directly)
# ---------------------------------------------------------------------------

_sae_instance = None
_sae_key: tuple[str, int, str | None] = ("", -1, None)


def _ensure_sae(
    sae_id: str,
    sae_layer: int,
    device: torch.device | str,
    sae_local_path: str | None = None,
):
    """Load SAE once and cache globally. Returns the sae_lens SAE object."""
    global _sae_instance, _sae_key

    # Check env var fallback for local path
    if sae_local_path is None:
        sae_local_path = os.environ.get("CONCORDANCE_SAE_LOCAL_PATH")

    key = (sae_id, sae_layer, sae_local_path)
    if _sae_instance is not None and _sae_key == key:
        return _sae_instance

    from sae_lens import SAE

    hook_name = f"l{sae_layer}r_8x"  # LlamaScope convention
    if sae_local_path:
        logger.info("Loading SAE from local path: %s", sae_local_path)
        _sae_instance = SAE.load_from_disk(sae_local_path, device=str(device))
    else:
        logger.info("Loading SAE release=%s sae_id=%s ...", sae_id, hook_name)
        loaded = SAE.from_pretrained(
            release=sae_id, sae_id=hook_name, device=str(device)
        )
        _sae_instance = loaded[0] if isinstance(loaded, tuple) else loaded

    _sae_key = key
    logger.info("SAE loaded successfully.")
    return _sae_instance


# ---------------------------------------------------------------------------
# Inference service (loaded once per container)
# ---------------------------------------------------------------------------

_service: _HFInferenceService | None = None


class _HFInferenceService:
    """Loads the HF model + tokenizer once and serves generation requests."""

    def __init__(self, model_id: str = MODEL_ID) -> None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("Loading tokenizer for %s ...", model_id)
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        logger.info("Loading model %s (float16) ...", model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        self.model.eval()
        self.model_id = model_id
        logger.info("Model %s ready.", model_id)

    @torch.inference_mode()
    def generate(self, req: HFGenerateRequest) -> HFGenerateResponse:
        # Wrap the raw prompt in a chat template
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": req.prompt},
        ]
        tokenized = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        )
        # apply_chat_template may return a BatchEncoding dict instead of a raw tensor
        # depending on the transformers version. Extract input_ids if needed.
        if hasattr(tokenized, "input_ids"):
            input_ids = tokenized.input_ids.to(self.model.device)
        else:
            input_ids = tokenized.to(self.model.device)

        # Build generation kwargs
        gen_kwargs: dict = {
            "max_new_tokens": req.max_tokens,
            "do_sample": req.temperature > 0,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if req.temperature > 0:
            gen_kwargs["temperature"] = req.temperature
            gen_kwargs["top_p"] = req.top_p

        attention_mask = (input_ids != self.tokenizer.pad_token_id).long()
        output_ids = self.model.generate(input_ids, attention_mask=attention_mask, **gen_kwargs)

        # output_ids is the FULL sequence (prompt + completion)
        full_sequence_ids: list[int] = output_ids[0].tolist()

        # Decode only the new tokens for output_text
        new_token_ids = full_sequence_ids[input_ids.shape[1]:]
        output_text = self.tokenizer.decode(new_token_ids, skip_special_tokens=True)

        # --- Inline SAE feature extraction ---
        feature_timeline: list[dict] = []
        if req.inline_sae:
            try:
                feature_timeline = self._extract_sae_timeline(
                    full_sequence_ids,
                    sae_id=req.sae_id,
                    sae_layer=req.sae_layer,
                    sae_top_k=req.sae_top_k,
                    sae_local_path=req.sae_local_path,
                )
            except Exception:
                logger.exception("Inline SAE extraction failed; returning empty timeline")

        return HFGenerateResponse(
            request_id=str(uuid.uuid4()),
            model_id=self.model_id,
            output_text=output_text,
            output_token_ids=full_sequence_ids,
            feature_timeline=feature_timeline,
        )

    @torch.inference_mode()
    def _extract_sae_timeline(
        self,
        token_ids: list[int],
        *,
        sae_id: str,
        sae_layer: int,
        sae_top_k: int,
        sae_local_path: str | None,
    ) -> list[dict]:
        """Run a forward pass to get hidden states, then SAE-encode each position."""
        device = self.model.device

        # Forward pass with hidden states
        input_tensor = torch.tensor([token_ids], device=device)
        outputs = self.model(
            input_ids=input_tensor,
            output_hidden_states=True,
        )

        # hidden_states is a tuple of (num_layers + 1) tensors
        # Index 0 is embeddings, layers 1..N correspond to transformer layers
        hidden = outputs.hidden_states[sae_layer + 1]  # (1, seq_len, hidden_dim)

        # Load SAE
        sae = _ensure_sae(sae_id, sae_layer, device, sae_local_path)

        seq_len = hidden.shape[1]
        timeline: list[dict] = []

        for pos in range(seq_len):
            vec = hidden[0, pos, :]  # (hidden_dim,)
            encoded = sae.encode(vec.unsqueeze(0))  # (1, n_features)
            top_vals, top_idxs = torch.topk(encoded[0], k=min(sae_top_k, encoded.shape[1]))

            top_features = [
                {"id": int(idx), "activation": round(float(val), 4)}
                for idx, val in zip(top_idxs, top_vals)
                if float(val) > 0
            ]

            token_id = token_ids[pos]
            try:
                token_str = self.tokenizer.decode([token_id])
            except Exception:
                token_str = f"<{token_id}>"

            timeline.append({
                "position": pos,
                "token": token_id,
                "token_str": token_str,
                "top_features": top_features,
            })

        return timeline


def _get_service() -> _HFInferenceService:
    global _service
    if _service is None:
        _service = _HFInferenceService()
    return _service


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_hf_inference_app() -> FastAPI:
    """Create and return a standalone FastAPI app for HF inference."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _get_service()  # eagerly load model at container start
        yield

    app = FastAPI(title="HF Inference Server", lifespan=lifespan)

    @app.get("/health")
    async def health():
        svc = _service
        return {
            "status": "ok" if svc is not None else "loading",
            "service": "hf-inference",
            "model_id": MODEL_ID,
        }

    @app.post("/hf/generate", response_model=HFGenerateResponse)
    async def generate(req: HFGenerateRequest):
        svc = _get_service()
        try:
            return svc.generate(req)
        except Exception as e:
            logger.exception("Generation failed")
            raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    return app
