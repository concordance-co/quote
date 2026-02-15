"""
Standalone HF inference server for activations playground.

Lightweight FastAPI app that runs meta-llama/Llama-3.1-8B-Instruct
via HuggingFace transformers for text generation. Returns output_text
and full-sequence output_token_ids (prompt + completion) needed by
the SAE feature extraction pipeline.

This module intentionally avoids importing quote.backends, quote.runtime,
quote.storage, or quote.mods to prevent the dependency chain that caused
staging deploy crashes.
"""

from __future__ import annotations

import logging
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


class HFGenerateResponse(BaseModel):
    request_id: str
    model_id: str
    output_text: str
    output_token_ids: list[int]


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
        input_ids = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(self.model.device)

        # Build generation kwargs
        gen_kwargs: dict = {
            "max_new_tokens": req.max_tokens,
            "do_sample": req.temperature > 0,
        }
        if req.temperature > 0:
            gen_kwargs["temperature"] = req.temperature
            gen_kwargs["top_p"] = req.top_p

        output_ids = self.model.generate(input_ids, **gen_kwargs)

        # output_ids is the FULL sequence (prompt + completion)
        full_sequence_ids: list[int] = output_ids[0].tolist()

        # Decode only the new tokens for output_text
        new_token_ids = full_sequence_ids[input_ids.shape[1]:]
        output_text = self.tokenizer.decode(new_token_ids, skip_special_tokens=True)

        return HFGenerateResponse(
            request_id=str(uuid.uuid4()),
            model_id=self.model_id,
            output_text=output_text,
            output_token_ids=full_sequence_ids,
        )


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
