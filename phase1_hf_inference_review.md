# Phase 1 Deep Review: HF Inference Endpoint

**Reviewer:** Task #2 Agent
**Date:** 2026-02-15
**Spec:** `STAGING_ACTIVATIONS_SPEC.md`, Phase 1 section
**Status:** Research & analysis only — no code changes

---

## 1. Phase 1 Scope (From Spec)

Phase 1 calls for adding a **new lightweight HTTP endpoint** in the **existing staging engine Modal app** (`max-openai-compatible`):

- **Input:** `{prompt, model_id?, max_tokens?, temperature?, top_p?}`
- **Output:** `{request_id, model_id, output_text, output_token_ids}`
- Uses HF meta weights (`meta-llama/Llama-3.1-8B-Instruct`)
- Kept separate from the OpenAI-compatible server and MAX inference path
- Not OpenAI-compatible (simple JSON)

---

## 2. Existing Architecture Analysis

### 2.1 Engine Modal App (`engine/inference/src/quote/api/openai/remote.py`)

The current Modal app `max-openai-compatible` is defined at `remote.py:63`:
```python
app = modal.App(os.environ.get("APP_NAME"))
```

It deploys a **single function** `openai_http_app()` (line 146-167) that:
- Runs on `A100-80GB` with GPU snapshots enabled
- Mounts 5 volumes: `/models`, MEF cache, `/logic`, `/users`, `/mods`
- Returns a FastAPI app created by `create_app()` from `local.py`
- Has max 15 concurrent inputs
- Scales 0→1 containers

**Key concern:** The spec says "same staging app" but a **separate function/container** for HF inference. This means adding a second `@app.function` to `remote.py`.

### 2.2 Existing Fullpass Debug (`engine/inference/src/quote/api/openai/fullpass_debug.py`)

The `_FullpassRuntime` class already does exactly what Phase 1 needs:
- Loads `meta-llama/Llama-3.1-8B-Instruct` via `HuggingFaceBackend` (line 130-134)
- Runs generation and returns `output_text` + `output_ids` (line 290-300)
- Supports `model_id`, `max_tokens`, `temperature`, `top_p`, `top_k` parameters

**However**, it also does much more (inline SAE, activation storage via DuckDB, feature deltas), which the spec explicitly wants to avoid for the lightweight HF endpoint. The fullpass runtime imports `ActivationStore`, `ActivationQueries`, and `MinimalSAEExtractor`, which were the root cause of the staging crashes.

### 2.3 HuggingFace Backend (`engine/inference/src/quote/backends/huggingface.py`)

The `HuggingFaceBackend` class provides:
- Model loading via `AutoModelForCausalLM.from_pretrained()` with torch
- Tokenization via `AutoTokenizer.from_pretrained()`
- Prefill, forward pass, sampling, token addition, KV cache management
- Device resolution (auto: CUDA > MPS > CPU)
- Hidden state and attention pattern extraction

This is a **full-featured generation backend** with step-by-step control. For the new endpoint, we can either:
1. Reuse `HuggingFaceBackend` + the `generate()` function from `runtime/generation.py` (more code reuse, but pulls in dependencies)
2. Write a **minimal standalone** HF inference function that just does `model.generate()` (simpler, fewer deps)

### 2.4 Backend Activation Explorer (`backend/src/handlers/activation_explorer.rs`)

Currently:
- `run_activation()` (line 286) calls `POST {ENGINE_BASE_URL}/debug/fullpass/run`
- `get_activation_rows()` (line 776) calls `GET {ENGINE_BASE_URL}/debug/fullpass/activations`
- `get_top_features()` (line 919) calls `GET {ENGINE_BASE_URL}/debug/fullpass/top-features`
- `get_feature_deltas()` (line 848) calls `GET {ENGINE_BASE_URL}/debug/fullpass/feature-deltas`
- `activation_health()` (line 975) checks `{ENGINE_BASE_URL}/healthz`

The env var controlling this is `ENGINE_BASE_URL` (default: `http://127.0.0.1:8000`).

For Phase 1, the backend will need a **new** env var `PLAYGROUND_ACTIVATIONS_HF_URL` pointing to the HF inference endpoint. But the backend handler changes are Phase 0 scope (replacing engine proxy calls with direct HF + SAE calls), not Phase 1.

### 2.5 SAE Service (`engine/inference/src/quote/api/sae_remote.py`)

Already deployed as a separate Modal app `sae-analysis`:
- Uses `A10G` GPU (lighter than A100)
- Loads `meta-llama/Llama-3.1-8B-Instruct` + `llama_scope_lxr_8x` SAE
- Provides `/extract_features` (takes token IDs, returns feature timeline)
- Provides `/analyze_features` (Claude-powered analysis)
- Already the target of `PLAYGROUND_SAE_URL` in the backend

---

## 3. Gaps and Ambiguities in the Spec

### 3.1 Critical Gaps

#### G1: Separate Modal function vs. separate route

The spec says:
> "Add a new lightweight HTTP endpoint in the existing staging engine Modal app"

And in Risks:
> "Mitigation: keep HF inference endpoint as a separate function/container (still within same Modal app)."

**Ambiguity:** Is this a new FastAPI route on the existing `openai_http_app()` function, or a new `@app.function` with its own container/GPU?

**Recommendation:** A **separate `@app.function`** is the right call:
- The existing function runs MAX Engine which occupies the A100 GPU
- HF inference of Llama 3.1 8B needs ~16GB VRAM (float16) — can run on A10G or T4
- Separate containers prevent memory contention (called out in spec Risks)
- A separate function also means independent scaling/timeout behavior

**Impact:** This is the most important architectural decision and should be locked in before implementation begins.

#### G2: GPU Requirements Not Specified

The spec doesn't specify what GPU to use for the HF inference endpoint.

- Llama 3.1 8B Instruct at float16 requires ~16GB VRAM
- A10G has 24GB — sufficient and cheaper than A100
- The SAE service already uses A10G successfully for the same model
- T4 (16GB) is too tight for 8B float16 + overhead

**Recommendation:** Use `A10G` (same as SAE service), or `A10G:1` explicitly.

#### G3: Authentication / Rate Limiting Not Addressed

The spec doesn't mention auth for the new HF endpoint.

- The existing OpenAI endpoint uses `ADMIN_KEY` for admin routes and per-user API keys for mod/inference
- The SAE service uses Modal secrets but no per-request auth
- The backend calling the HF endpoint is a trusted server-to-server call

**Recommendation:** Either:
- No auth (internal endpoint only, accessed by backend) — simplest
- Admin key check (quick header validation) — minimal protection

The backend should be the only caller, so no auth may be acceptable for staging.

#### G4: Model Loading Strategy

The spec says the endpoint "uses HF meta weights" but doesn't address:
- **Cold start time:** Loading Llama 3.1 8B takes 30-60 seconds. Should we use Modal memory snapshots?
- **Model caching:** The `/models` volume is already shared — the model may already be cached there from SAE service or fullpass debug
- **Startup behavior:** Should the endpoint pre-load the model in `__enter__` (Modal class pattern) or lazy-load on first request?

**Recommendation:** Use `enable_memory_snapshot=True` (like the existing function) and load the model eagerly at container start. The models volume is already mounted and should have the model cached.

#### G5: HF_TOKEN for Gated Model Access

`meta-llama/Llama-3.1-8B-Instruct` is a **gated model** on HuggingFace — requires acceptance of Meta's license agreement and an HF token.

The spec mentions `HF_TOKEN` as needed but doesn't specify how it's provisioned:
- Currently set in `remote.py` env from `os.environ.get("HF_TOKEN", "")`
- The new function needs the same token

**Recommendation:** Share the same env var injection pattern. If deploying as a separate function in the same `remote.py`, `HF_TOKEN` is already available.

### 3.2 Minor Gaps

#### G6: Request/Response Schema Details

The spec gives:
- Input: `{prompt, model_id?, max_tokens?, temperature?, top_p?}`
- Output: `{request_id, model_id, output_text, output_token_ids}`

Missing details:
- Should `model_id` in the input be validated/ignored (since we only support one model)?
- Should there be a `top_k` parameter for sampling (the existing fullpass debug has it)?
- What's the max `max_tokens` allowed? (The existing handler caps at 2048)
- Should the response include `input_token_ids` (useful for SAE which needs the full token sequence)?
- Error response format? (Suggest matching existing engine error patterns)
- Should `output_token_ids` be the full sequence (prompt + completion) or just completion tokens?

**Recommendation:**
- Accept `model_id` but ignore it (or warn if not matching the loaded model) for now
- Include `top_k` for parity with fullpass debug
- Cap `max_tokens` at 2048 (matching existing validation)
- Return `output_token_ids` as **completion-only** token IDs (consistent with spec name "output")
- Also return `input_token_ids` (the tokenized prompt) since the SAE service needs the **full** token sequence
- Use standard HTTP error codes with JSON error body

#### G7: Chat Template Application

The existing `_encode_prompt` in `fullpass_debug.py` applies a chat template:
```python
messages = [
    {"role": "system", "content": "You are concise."},
    {"role": "user", "content": prompt},
]
tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
```

The spec doesn't mention whether the new endpoint should:
- Accept raw text prompts and apply a chat template
- Accept messages (OpenAI format)
- Let the caller handle tokenization

**Recommendation:** Accept a raw `prompt` string and apply the chat template internally (same as fullpass debug), since the backend sends a user prompt string. The system prompt ("You are concise.") should probably be made configurable or use the model's default.

#### G8: Endpoint Path

The spec says "a new lightweight HTTP endpoint" but doesn't specify the URL path.

**Recommendation:** `/hf/generate` or `/v1/hf/generate` — simple, non-conflicting with existing OpenAI-compatible paths.

#### G9: Scaling Configuration

Not specified:
- Min/max containers (0/1 is fine for staging)
- Scaledown window (how long to keep warm?)
- Timeout per request
- Max concurrent inputs

**Recommendation:** Match SAE service pattern:
- `min_containers=0, max_containers=1`
- `scaledown_window=30 * 60` (30 minutes — shorter than 2 hours since it's lightweight)
- `timeout=10 * 60` (10 minutes)
- `max_inputs=5` (conservative, generation is memory-intensive)

### 3.3 Dependency Questions

#### G10: Relationship to Phase 0

Phase 0 says:
> "Replace calls in `backend/src/handlers/activation_explorer.rs`: Remove `ENGINE_BASE_URL` usage for activations."

Phase 1 (this phase) just adds the HF endpoint. But who will call it?
- Phase 0 is supposed to update the backend to call HF + SAE instead of fullpass debug
- Phase 1 adds the HF endpoint that Phase 0 needs

**This creates a circular dependency.** Phase 0 needs Phase 1's endpoint, but Phase 1 is listed after Phase 0.

**Recommendation:** Phase 1 should be implemented **before or concurrently with** Phase 0. The endpoint should be deployed and testable independently (e.g., via curl) before the backend is updated.

#### G11: Interaction with SAE Service

The backend will call:
1. HF inference endpoint (Phase 1) → gets `output_text` + `output_token_ids`
2. SAE service (existing) → gets `feature_timeline`

The SAE service already has its **own** HF model loaded for tokenization. The token IDs from the Phase 1 endpoint must be compatible with the SAE service's tokenizer.

**This is guaranteed** since both use `meta-llama/Llama-3.1-8B-Instruct`, but it's worth adding a test.

---

## 4. Proposed Implementation Tasks

### Task 1: Create HF Inference FastAPI App

**Files to create:**
- `engine/inference/src/quote/api/hf_inference.py` (~80-120 lines)

**What it does:**
- Defines a `create_hf_inference_app()` function returning a FastAPI app
- Single `POST /generate` endpoint
- Loads model via `HuggingFaceBackend` or standalone `transformers` pipeline
- Applies chat template to prompt
- Runs generation
- Returns `{request_id, model_id, output_text, output_token_ids, input_token_ids}`
- Health check endpoint `GET /health`

**Key decisions:**
- Use standalone `transformers` `model.generate()` rather than the full `HuggingFaceBackend` + `generate()` pipeline. This avoids importing `quote.storage`, `quote.mods`, `duckdb`, etc.
- Keep imports minimal: `transformers`, `torch`, `fastapi`, `uuid`

**Estimated LOC:** ~100-120

### Task 2: Add Modal Function for HF Inference

**Files to modify:**
- `engine/inference/src/quote/api/openai/remote.py` (~40-60 lines added)

**What it does:**
- Adds a new `@app.function` decorator with:
  - `gpu="A10G"`
  - `volumes={"/models": models_vol}` (only models volume needed)
  - `enable_memory_snapshot=True`
  - `min_containers=0, max_containers=1`
  - `scaledown_window=30 * MINUTES`
  - `timeout=10 * MINUTES`
  - `@modal.concurrent(max_inputs=5)`
- Returns the FastAPI app from `create_hf_inference_app()`
- Shares `HF_TOKEN` and `HF_HOME`/`HF_HUB_CACHE` env vars

**Considerations:**
- Must use `@modal.asgi_app()` decorator
- Separate GPU class means no memory contention with MAX Engine
- The function name should be distinct (e.g., `hf_inference_app`)

**Estimated LOC:** ~40-60

### Task 3: Request/Response Pydantic Models

**Files:** Part of `hf_inference.py` or separate `hf_inference_models.py`

**What it does:**
- Define `HFGenerateRequest` with:
  - `prompt: str` (required)
  - `model_id: str | None` (optional, ignored for now)
  - `max_tokens: int = 128` (default, max 2048)
  - `temperature: float = 0.7`
  - `top_p: float = 0.95`
  - `top_k: int = 0` (0 = disabled)
- Define `HFGenerateResponse` with:
  - `request_id: str`
  - `model_id: str`
  - `output_text: str`
  - `output_token_ids: list[int]`
  - `input_token_ids: list[int]` (bonus, useful for SAE)

**Estimated LOC:** ~30-40 (included in Task 1 count)

### Task 4: Input Validation

**Files:** Part of `hf_inference.py`

**What it does:**
- Validate prompt non-empty and < 12000 chars
- Validate max_tokens in [1, 2048]
- Validate temperature in [0.0, 2.0]
- Validate top_p in [0.0, 1.0]
- Return 400 errors with descriptive messages

**Estimated LOC:** ~25 (included in Task 1 count)

### Task 5: Deployment Configuration

**Files to modify or document:**
- Modal secrets / env vars configuration (documentation)
- Backend `.env.example` (add `PLAYGROUND_ACTIVATIONS_HF_URL`)

**What it does:**
- Document that after deploying `remote.py`, Modal will assign a URL to `hf_inference_app`
- This URL becomes `PLAYGROUND_ACTIVATIONS_HF_URL` in the backend's Modal secret
- Ensure `HF_TOKEN` is available in the engine Modal secret

**Estimated LOC:** ~5-10 (config documentation)

### Task 6: Testing

**Files to create:**
- `engine/tests/test_hf_inference.py` (~60-100 lines)

**What it does:**
- Unit test for request validation
- Unit test for chat template application
- Integration test stub (requires GPU, may need to be run manually)
- Verify response schema

**Estimated LOC:** ~60-100

---

## 5. Total Estimated Effort

| Task | Files | Est. LOC |
|------|-------|----------|
| 1. HF Inference FastAPI App | `api/hf_inference.py` (new) | 100-120 |
| 2. Modal Function | `api/openai/remote.py` (modify) | 40-60 |
| 3. Request/Response Models | (included in Task 1) | — |
| 4. Input Validation | (included in Task 1) | — |
| 5. Deployment Config | `.env.example`, docs | 5-10 |
| 6. Testing | `tests/test_hf_inference.py` (new) | 60-100 |
| **Total** | **2 new files, 1 modified** | **~205-290** |

---

## 6. Recommended Approach

### Option A: Minimal Standalone (Recommended)

Create `hf_inference.py` that uses `transformers` directly without importing anything from `quote.backends`, `quote.runtime`, `quote.storage`, or `quote.mods`. This means:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

class HFInferenceService:
    def __init__(self, model_id="meta-llama/Llama-3.1-8B-Instruct"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=torch.float16)
        self.model.to("cuda").eval()

    def generate(self, prompt, max_tokens=128, temperature=0.7, top_p=0.95):
        # Apply chat template, generate, decode, return
        ...
```

**Pros:**
- Zero risk of pulling in broken deps (duckdb, quote.storage, etc.)
- Simple to understand and maintain
- Fewer imports = faster cold start
- Clear separation from MAX Engine path

**Cons:**
- Some code duplication with `HuggingFaceBackend`
- Doesn't reuse the generation loop / mod system (but that's intentional)

### Option B: Reuse HuggingFaceBackend

Import `HuggingFaceBackend` and `generate()` from existing code, but skip activation storage and SAE.

**Pros:** More code reuse
**Cons:** Imports `quote.runtime`, `quote.mods`, and transitively other modules. Risk of pulling in heavy deps or triggering import-time side effects.

**Verdict:** Option A is safer and aligns with the spec's intent ("lightweight").

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Model download on cold start | Medium | 30-60s first request | Use Modal memory snapshot; pre-cache via volume |
| GPU memory contention with MAX Engine | Low (separate container) | High | Separate `@app.function` with own GPU |
| HF_TOKEN not set / model access denied | Low | Blocks deployment | Document requirement; validate at startup |
| Token ID mismatch with SAE service | Very Low | Wrong features | Both use same model/tokenizer |
| Chat template changes model behavior | Low | Unexpected output | Use same template as fullpass debug |

---

## 8. Open Questions for Stakeholder

1. **Separate function confirmed?** Should the HF endpoint be a separate `@app.function` (recommended) or a route on the existing `openai_http_app`?

2. **GPU type?** A10G (24GB, $1.10/hr on Modal) recommended. Is cost acceptable for staging?

3. **Auth requirement?** Should the endpoint require an admin key or be unprotected (internal only)?

4. **Should `output_token_ids` include prompt tokens?** The SAE service needs the full sequence. Suggest returning both `input_token_ids` and `output_token_ids` separately.

5. **System prompt in chat template?** Currently "You are concise." — should this match the fullpass debug or be different for activations use case?

6. **Phase ordering:** Should Phase 1 be renumbered to come before Phase 0 in execution order, since Phase 0 depends on the HF endpoint existing?
