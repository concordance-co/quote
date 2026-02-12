# Phase 0 Spec: Local-First HuggingFace Backend + Minimal Activation Infrastructure

## Repo Orientation — Read First

**Repo:** `https://github.com/concordance-co/quote` (monorepo)

Before writing any code, read these files/directories to understand the existing system. **This is not an exhaustive list — explore the codebase — but these are the most important starting points:**

| What | Where | Why |
|------|-------|-----|
| Shared types (events, actions, base classes) | `engine/shared/src/shared/types.py` | **The source of truth** for `Prefilled`, `ForwardPass`, `Sampled`, `Added`, all action types. |
| Action validation rules | `engine/shared/src/shared/utils.py` | `validate_action()` and the `ALLOWED_ACTIONS` mapping. |
| Mod SDK (decorator, ActionBuilder, tokenizer) | `engine/sdk/quote_mod_sdk/` | The public API mods are written against. `mod.py` has the `@mod` decorator, `actions.py` has `ActionBuilder`. |
| SDK public exports | `engine/sdk/quote_mod_sdk/__init__.py` | Full list of everything mods can import. |
| SelfPrompt + FlowEngine | `engine/sdk/quote_mod_sdk/self_prompt.py`, `engine/sdk/quote_mod_sdk/flow.py` | Higher-level mod frameworks. Production mods use these. Must keep working. |
| Strategy system | `engine/sdk/quote_mod_sdk/strategies/` | `ChoicesStrat`, `ListStrat`, `CharsStrat`, `PatternStrat` — constrained generation strategies. |
| Conversation API | `engine/shared/src/shared/conversation.py` | `get_conversation()`, `get_schemas()`, `tool_call_pairs()` — mods use these to read chat history. |
| Main generation loop | `engine/inference/src/quote/hot/execute_impl.py` | **The core file (1,864 lines).** The generation loop that emits events, dispatches mods, and applies actions. The new `generation.py` replaces this. |
| Mod dispatch (ModManager) | `engine/inference/src/quote/mods/manager.py` | How events flow from engine → mods → actions. `ModManager.dispatch()` calls each mod and collects actions. |
| Mod loading from payload | `engine/inference/src/quote/mods/sdk_bridge.py` | `load_mod_from_payload()` — dynamic mod loading from JSON payloads (inline source, directory, bundle). |
| Observability pipeline | `engine/inference/src/quote/logs/logger.py`, `engine/inference/src/quote/logs/emit.py` | `IngestAccumulator` collects events/mod_calls/mod_logs/actions per request, POSTs JSON to backend. |
| SAE sidecar (being eliminated) | `engine/inference/src/quote/sae_server.py`, `engine/inference/src/quote/interpretability/` | Post-hoc analysis service. Loads separate HF model + SAE. Being replaced by inline hidden state access. |
| Pipeline + server wiring | `engine/inference/src/quote/server/core.py`, `engine/inference/src/quote/server/openai/local.py` | How MAX Engine pipeline is created, how mods are wired, hot-reload execution. |
| Production mods | `engine/examples/json_schema/mod.py`, `engine/examples/tau2/mod.py` | Real mods using FlowEngine, ActionBuilder, strategies. These must keep working. |
| Test mods (24 files) | `engine/tests/mod_unit_tests/` | One test mod per event×action combination. The test harness for the mod system. |
| Backend (Rust/Axum) | `backend/` | **Don't modify.** Understand the ingest endpoint (`POST /v1/ingest`) and its payload schema. |
| Backend ingest handler | `backend/src/handlers/ingest/` | `ingest_payload()` — atomic persist of request, events, mod_calls, mod_logs, actions. |

**Key existing types — these are the ACTUAL names and fields:**

Events (all inherit from `ModEvent`):
- `Prefilled(request_id, step, max_steps, context_info)`
- `ForwardPass(request_id, step, logits)` — logits is `max.driver.Tensor`
- `Sampled(request_id, step, sampled_token)`
- `Added(request_id, step, added_tokens, forced)` — `added_tokens` is `List[int]`, not single token

Actions (all inherit from `ModAction`):
- `Noop()`
- `AdjustedPrefill(tokens, max_steps)`
- `ForceTokens(tokens)`
- `AdjustedLogits(logits, token_temp)` — `token_temp` is optional per-token temperature override
- `EmitError(err_str)`
- `ForceOutput(tokens)` — tokens field, not empty
- `ToolCalls(tool_calls)` — opaque payload
- `Backtrack(n, tokens)` — `tokens` not `replacement_tokens`

Mod signature (internal handler, before `@mod` wrapping):
```python
def my_mod(event: ModEvent, actions: ActionBuilder, tokenizer: Any | None) -> ModAction | None
```

Mod signature (after `@mod` wrapping, what ModManager calls):
```python
def my_mod(event: ModEvent, tokenizer: Any | None) -> ModAction
```

**The goal is NOT a rewrite from scratch.** It's: replace MAX Engine with HuggingFace transformers as the inference backend, get hidden state access inline, and keep every existing mod working with zero changes.

---

## Goal

Replace the current MAX Engine + post-hoc HuggingFace sidecar architecture with a single HuggingFace transformers backend that:
1. Exposes model internals (hidden states at any layer, attention patterns, logits) inline during generation
2. Runs on Mac (MPS), CPU, or CUDA — local dev first, Modal later
3. Runs existing mods with **zero mod code changes** (minor backend behavioral differences are acceptable)
4. Is designed to be portable to Rust later (clean types, no dynamic hacks)
5. Adds a minimal, queryable local activation data path that can scale into Phase 1

**Target model:** `meta-llama/Llama-3.1-8B-Instruct`
**Target devices:** `mps` (Mac Metal GPU), `cpu` (fallback), `cuda` (Modal prod)
**Timeline:** ~1-2 weeks

### Clarifications from Review

- **Local-first priority:** all Phase 0 acceptance criteria are judged on local runs; Modal is deferred.
- **No strict `execute_impl.py` parity requirement:** behavior can differ from MAX internals as long as mod semantics are coherent and observability is preserved.
- **Force-token intended behavior (preserved):** while forced queue has tokens, sampling is bypassed and `Added(..., forced=True)` is emitted for injected tokens.
- **Prompt templating boundary:** server layer is responsible for chat templating; `generation.py` consumes token IDs (`input_ids`) and backend abstractions.
- **Env var migration policy:** support both existing `MODEL_ID` and new `CONCORDANCE_*` names during transition.
- **Minimal SAE path is included in Phase 0:** default nearline extraction + optional inline SAE mode for experimentation.

---

## Module Overview

New files sit alongside existing code inside `engine/inference/src/quote/`. Existing files are untouched unless noted. New code imports from existing `mods/`, `logs/`, `shared/`, and `sdk/` packages directly.

```
engine/inference/src/quote/
├── hot/
│   └── execute_impl.py           # EXISTING — untouched, keep for MAX Engine path
├── mods/
│   ├── manager.py                # EXISTING — reused by new generation.py
│   └── sdk_bridge.py             # EXISTING — reused for mod loading
├── logs/
│   ├── logger.py                 # EXISTING — reused by new generation.py
│   └── emit.py                   # EXISTING — reused for step emission
├── server/                       # EXISTING — untouched
├── interpretability/             # EXISTING — SAE sidecar, untouched (deprecated after Phase 1)
├── sae_server.py                 # EXISTING — untouched (deprecated after Phase 1)
│
├── backends/
│   ├── __init__.py               # NEW
│   ├── interface.py              # NEW — Backend protocol + config types
│   └── huggingface.py            # NEW — HuggingFace transformers backend
├── generation.py                 # NEW — Engine-agnostic generation loop
├── config.py                     # NEW — Backend selection + config
├── activations/
│   ├── __init__.py               # NEW
│   ├── store.py                  # NEW — DuckDB/Parquet writer + retention
│   ├── queries.py                # NEW — local query helpers (feature deltas, thresholds)
│   └── schema.py                 # NEW — activation table schemas + versioning
└── features/
    ├── __init__.py               # NEW
    ├── sae_extract.py            # NEW — minimal SAE encoding (top-k only)
    └── neuronpedia.py            # NEW — optional feature metadata lookup hook

engine/shared/src/shared/
├── types.py                      # EXISTING — event + action types (additive changes only: new optional fields)
└── utils.py                      # EXISTING — validate_action() (no changes)

engine/sdk/quote_mod_sdk/         # EXISTING — no changes to any file

engine/tests/
├── mod_unit_tests/               # EXISTING — 24 test mods + harness
├── sdk/                          # EXISTING — FlowEngine, SelfPrompt, strategy tests
├── test_hf_backend.py            # NEW — HuggingFace backend tests
├── test_generation.py            # NEW — End-to-end generation tests
└── test_activation_store.py      # NEW — local activation schema/query tests
```

---

## Module 1: `engine/inference/src/quote/backends/interface.py`

**Purpose:** Define the Backend protocol. This is the contract between the generation loop and backend implementations. Event and action types already live in `shared/types.py` — do NOT duplicate them.

**Design constraint:** Types will be ported to Rust later. Keep them flat, serializable, no complex inheritance.

### Event Types — PRESERVED FROM `shared/types.py`

These are the existing types. They do NOT change. The HuggingFace backend must emit these exact types.

```
Prefilled (inherits ModEvent)
  - request_id: str
  - step: int
  - max_steps: int
  - context_info: Optional[dict]

ForwardPass (inherits ModEvent)
  - request_id: str
  - step: int
  - logits: Tensor
  - Method: top_k_logprob(k) -> (logprobs, indices)

Sampled (inherits ModEvent)
  - request_id: str
  - step: int
  - sampled_token: int

Added (inherits ModEvent)
  - request_id: str
  - step: int
  - added_tokens: List[int]
  - forced: bool
```

### NEW Event Fields — Added in This Phase

Hidden states and attention patterns are the key new capabilities. Add these as **optional fields** to the existing event classes in `shared/types.py` to preserve backward compatibility:

```
Prefilled — add:
  - hidden_states: Optional[Tensor]       # shape: (seq_len, hidden_dim) at configured layer
  - attention_patterns: Optional[Tensor]  # shape: (num_heads, seq_len, seq_len) at configured layer
  - layer: Optional[int]                  # which layer the hidden states/attention are from
  - input_ids: Optional[list[int]]        # tokenized prompt

ForwardPass — add:
  - hidden_states: Optional[Tensor]       # shape: (1, hidden_dim) at configured layer, current position only
  - attention_patterns: Optional[Tensor]  # shape: (num_heads, 1, seq_len) at configured layer — current token attending to all previous
  - layer: Optional[int]
  - input_ids: Optional[list[int]]        # full sequence so far
```

All new fields default to `None`. Existing mods that don't use them are unaffected. MAX Engine path continues to emit `None` for these fields.

**Attention pattern notes:**
- Llama-3.1-8B has 32 attention heads per layer (with GQA: 32 query heads, 8 KV heads)
- HuggingFace `output_attentions=True` returns attention weights AFTER softmax, shape `(batch, num_heads, seq_len, seq_len)` for prefill or `(batch, num_heads, 1, seq_len)` for decode
- These are the query-head attention patterns, not KV heads
- For decode steps, the pattern shows how the current token attends to all previous tokens — this is what we need for Phase 1 analysis (e.g., "does attention shift when jailbreak tokens are injected?")

### Tensor Type Change — TensorShim

Current `ForwardPass.logits` uses `max.driver.Tensor`. HuggingFace produces `torch.Tensor`. This is a breaking change for logit manipulation in mods.

Solution: implement a `TensorShim` class wrapping `torch.Tensor` that exposes the same interface as `max.driver.Tensor`:
- `.to_numpy() -> np.ndarray`
- `.from_numpy(arr) -> TensorShim` (classmethod)
- `.shape` property
- `.device` property
- `.to(device)` method
- Indexing support (`__getitem__`, `__setitem__`)

This shim lets existing mods (especially `SelfPrompt` which does numpy logit masking) work unchanged.

**Portability note:** the shim is Phase 0 compatibility scaffolding. Phase 1+ should move toward a backend-agnostic tensor protocol so `shared/types.py` no longer hard-depends on MAX tensor classes.

### Action Types — PRESERVED FROM `shared/types.py`

These do NOT change:

```
Noop()
AdjustedPrefill(tokens, max_steps)
ForceTokens(tokens)
AdjustedLogits(logits, token_temp)
ForceOutput(tokens)
ToolCalls(tool_calls)
EmitError(err_str)
Backtrack(n, tokens)
```

### Validation Rules — FROM `shared/utils.py` ALLOWED_ACTIONS

Preserve exactly:

| Event | Allowed Actions |
|-------|----------------|
| `Prefilled` | `Noop`, `ForceOutput`, `ToolCalls`, `AdjustedPrefill`, `EmitError` |
| `ForwardPass` | `Noop`, `ForceTokens`, `Backtrack`, `ForceOutput`, `ToolCalls`, `AdjustedLogits`, `EmitError` |
| `Sampled` | `Noop`, `ForceTokens`, `Backtrack`, `ForceOutput`, `ToolCalls`, `EmitError` |
| `Added` | `Noop`, `ForceTokens`, `Backtrack`, `ForceOutput`, `ToolCalls`, `EmitError` |

Additional rules:
- Terminal actions (`ForceOutput`, `ToolCalls`, `EmitError`) stop mod iteration immediately
- Multiple mods can return actions for same event — applied in registration order
- `None` return from a mod becomes `Noop()`
- Invalid action/event combination raises `InvalidActionError`

### Backend Protocol — NEW

```python
class Backend(Protocol):
    def load_model(self, model_id: str, config: BackendConfig) -> None: ...
    def tokenizer(self) -> Any: ...
    def prefill(self, input_ids: list[int], max_steps: int) -> Prefilled: ...
    def forward_pass(self, request_id: str) -> ForwardPass: ...
    def sample(self, logits: Tensor, temperature: float, top_p: float, top_k: int) -> Sampled: ...
    def add_token(self, request_id: str, tokens: list[int], forced: bool) -> Added: ...
    def rewind_kv_cache(self, n: int) -> None: ...
    def get_hidden_states(self, layer: int) -> Tensor: ...
    def get_attention_patterns(self, layer: int) -> Tensor | None: ...  # None if extract_attention=False
    def shutdown(self) -> None: ...
```

Note: The current `execute_impl.py` loop is procedural — there is no Backend protocol today. This protocol is extracted from what the loop _does_.

### Config Types — NEW

```python
@dataclass
class BackendConfig:
    backend_type: str = "huggingface"     # only option for now, extensible later
    model_id: str = "meta-llama/Llama-3.1-8B-Instruct"
    device: str = "auto"                  # "auto" detects: mps > cuda > cpu
    hidden_state_layer: int = 16          # which layer to extract, matches current SAE setup
    dtype: str = "auto"                   # float32 on cpu/mps, float16 on cuda
    extract_attention: bool = True        # extract attention patterns (can disable if perf bottleneck)

@dataclass
class GenerationConfig:
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 50
    stop_tokens: list[int] | None = None
```

**Device auto-detection logic:**
```python
if device == "auto":
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
```

**Output:** `interface.py` imports from `shared.types` for events/actions. It adds only the `Backend` protocol and config types. Zero backend dependencies (no torch, transformers).

---

## Module 2: `engine/inference/src/quote/backends/huggingface.py`

**Purpose:** Implement the Backend protocol using HuggingFace transformers. This is the only backend for Phase 0.

### Inputs
- `BackendConfig` with `backend_type="huggingface"`
- Model loads via `AutoModelForCausalLM.from_pretrained()` with `output_hidden_states=True`

### Key Implementation Details

**Model loading:**
- Load with `output_hidden_states=True` AND `output_attentions=True` so both are always available
- Device auto-detection: `mps` on Mac, `cuda` if available, `cpu` fallback
- Dtype: `torch.float32` on CPU/MPS, `torch.float16` on CUDA
- Tokenizer: `AutoTokenizer.from_pretrained()` with chat template support

**Tensor compatibility — TensorShim:**
- Current mods manipulate `max.driver.Tensor` (via `ForwardPass.logits` and `AdjustedLogits.logits`)
- HF backend produces `torch.Tensor`
- `TensorShim` wraps `torch.Tensor` to expose the `max.driver.Tensor` interface:
  - `.to_numpy()` — detach, move to cpu, convert to numpy
  - `.from_numpy(arr)` — classmethod, wraps as TensorShim on original device
  - `.shape` — returns tuple
  - `.device` — returns device info
  - `.to(device)` — returns new TensorShim
  - Indexing support for `SelfPrompt` logit masking
- The shim is a drop-in replacement so existing mods work unchanged

**Generation loop — preserve intended semantics, not strict bit-for-bit MAX parity:**
1. Encode prompt → forward pass → emit `Prefilled` with hidden states at configured layer
2. Per token:
   a. Forward pass → emit `ForwardPass` with logits (as TensorShim) + hidden states
   b. Dispatch to mods, process actions (AdjustedLogits, ForceTokens, Backtrack, terminals)
   c. Sample token → emit `Sampled`
   d. Dispatch to mods, process actions (ForceTokens, Backtrack, terminals)
   e. Add token(s) to sequence → emit `Added` with `forced` flag
   f. Dispatch to mods, process actions (ForceTokens, Backtrack, terminals)
3. Stop on EOS, max_tokens, or terminal action

**IMPORTANT: Manual token-by-token generation.** Do NOT use `model.generate()` — we need to intercept at each step. Implement a manual loop with `past_key_values` (KV cache) for efficiency.

**Critical behavior to preserve:**
- `ForceTokens` are queued per-request in `mod_manager.forced_queues[request_id]`, consumed FIFO
- When `Added` event dispatches and mod returns `ForceTokens`, the new tokens are combined with the already-added tokens
- `Backtrack` semantics remain coherent across event phases (no requirement to replicate MAX internals exactly)
- Terminal actions (`ForceOutput`, `ToolCalls`, `EmitError`) short-circuit remaining mod iteration
- Empty `Backtrack.tokens` (not None, but empty list) with `n > 0` sets `skip_progress` flag

**Hidden state extraction:**
- `output_hidden_states=True` returns hidden states for ALL 33 layers (embeddings + 32 transformer layers). This is intentional — Phase 1 needs layer sweeps for activation hunting. With 64GB+ RAM this is not a concern.
- `model_output.hidden_states[layer + 1]` gives hidden states at layer `layer` (+1 offset because index 0 is the embedding layer output, per existing `feature_extractor.py` pattern)
- For `ForwardPass`: slice to current position only: `hidden_states[layer + 1][:, -1, :]` → shape `(hidden_dim,)`
- For `Prefilled`: return full sequence: `hidden_states[layer + 1][0, :, :]` → shape `(seq_len, hidden_dim)`
- Squeeze batch dim (always 1 — single-request only this phase)
- Only the configured layer's hidden states are attached to event objects; the rest are discarded after forward pass

**Attention pattern extraction:**
- `model_output.attentions` is a tuple of tensors, one per layer
- `model_output.attentions[layer]` gives attention weights at that layer, shape `(batch, num_heads, seq_len, seq_len)` for prefill, `(batch, num_heads, 1, past_seq_len)` for decode
- Squeeze batch dim, same as hidden states
- For `Prefilled`: return full attention: `attentions[layer][0]` → shape `(num_heads, seq_len, seq_len)`
- For `ForwardPass`: return current token's attention: `attentions[layer][0]` → shape `(num_heads, 1, seq_len)`
- **Memory note:** Attention patterns are large (32 heads × seq_len × seq_len × float32). For long sequences this can be significant. Store only the configured layer's attention, not all layers.
- **MPS note:** `output_attentions=True` may be slower on MPS. If it's a bottleneck, make it toggleable via `BackendConfig.extract_attention: bool = True`

**KV cache management:**
- Use HuggingFace `DynamicCache` or `past_key_values` tuple
- `rewind_kv_cache(n)`: slice `past_key_values` to remove last n positions from each layer's key and value tensors
- After rewind, re-run forward pass from the new position to get correct logits

**MPS-specific notes:**
- Some operations may need to fall back to CPU on MPS (e.g., certain sampling ops)
- Test on both MPS and CPU to ensure correctness
- MPS doesn't support all dtypes — stick with float32 on MPS

### Batching — Deferred

The current `execute_impl.py` handles batched generation. **This phase implements single-request generation only.** The `request_id` field is still populated per-event for observability compatibility.

### Output
- A class implementing `Backend` protocol
- All tensors on the configured device, wrapped in `TensorShim` where exposed to mods
- Events use existing types from `shared.types`

### Test Criteria
- Model loads and generates coherent text on CPU, MPS, and CUDA
- Hidden states are non-zero and have correct shape `(seq_len, 4096)` for Llama-3.1-8B
- Hidden states at layer 16 match what the current SAE sidecar extracts (within tolerance)
- Attention patterns have correct shape: `(32, seq_len, seq_len)` for prefill, `(32, 1, seq_len)` for decode at each step
- Attention patterns sum to ~1.0 across the key dimension (post-softmax)
- Attention patterns change when tokens are injected (basic sanity check for Phase 1)
- `ForceTokens` action injects exact tokens
- `AdjustedLogits` modifies sampling distribution (verify with temperature=0 deterministic test)
- `Backtrack` rewinds and regenerates differently
- `Backtrack` phase behavior is explicit, tested, and documented (no MAX-internal parity requirement)
- Generation stops on EOS and max_tokens
- `TensorShim` passes existing mod unit tests (especially `test_forwardpass_adjust_logits`)
- Existing `SelfPrompt` numpy logit masking works with TensorShim

---

## Module 3: `engine/inference/src/quote/generation.py`

**Purpose:** Engine-agnostic generation loop. Consumes a `Backend`, runs mods via existing `ModManager`, orchestrates the full generation flow, and feeds the existing observability pipeline.

### Inputs
- `Backend` instance (HuggingFace for now, extensible later)
- `GenerationConfig`
- `ModManager` instance (existing class from `mods/manager.py` — reused as-is)

### Logic

This replaces `execute_impl.py`'s `execute()` function for the HF path. The structure mirrors the existing event lifecycle, but does not need MAX-internal parity.

```python
def generate(backend, config, mod_manager, request_id) -> GenerationResult:
    accumulator = IngestAccumulator(request_id)

    # 1. Prefill
    prefilled = backend.prefill(input_ids, config.max_tokens)
    for action in mod_manager.dispatch(prefilled):
        if isinstance(action, AdjustedPrefill):
            backend.prefill(action.tokens, action.max_steps or config.max_tokens)
            break
        elif isinstance(action, ForceTokens):
            mod_manager.forced_queues.setdefault(request_id, []).extend(action.tokens)
        elif isinstance(action, (ForceOutput, ToolCalls, EmitError)):
            return finalize(action, accumulator)

    # 2. Token loop
    while not done:
        # Forward pass
        fp = backend.forward_pass(request_id)
        for action in mod_manager.dispatch(fp):
            if isinstance(action, AdjustedLogits):
                logits = action.logits
                if action.token_temp:
                    temperature = action.token_temp
            elif isinstance(action, ForceTokens):
                mod_manager.forced_queues.setdefault(request_id, []).extend(action.tokens)
            elif isinstance(action, Backtrack):
                backend.rewind_kv_cache(action.n + 1)  # +1: sampled token not yet added
                if action.tokens:
                    mod_manager.forced_queues.setdefault(request_id, []).extend(action.tokens)
                break
            elif is_terminal(action):
                return finalize(action, accumulator)

        # Sample (skip if forced queue has tokens)
        forced_queue = mod_manager.forced_queues.get(request_id, [])
        if forced_queue:
            token = forced_queue.pop(0)
            forced = True
        else:
            sampled = backend.sample(logits, temperature, top_p, top_k)
            token = sampled.sampled_token
            forced = False
            for action in mod_manager.dispatch(sampled):
                # Handle ForceTokens, Backtrack, terminals
                ...

        # Add to sequence
        added_tokens = [token]
        added = Added(request_id, step, added_tokens, forced)
        for action in mod_manager.dispatch(added):
            if isinstance(action, ForceTokens):
                combined = list(added_tokens) + list(action.tokens)
                mod_manager.forced_queues[request_id] = combined
            elif isinstance(action, Backtrack):
                action.n = max(0, action.n - 1)  # -1: token already added
                backend.rewind_kv_cache(action.n)
                if action.tokens:
                    mod_manager.forced_queues.setdefault(request_id, []).extend(action.tokens)
                break
            elif is_terminal(action):
                return finalize(action, accumulator)

        accumulator.add_event(...)

        if eos or step >= max_tokens:
            break
        step += 1

    accumulator.finalize()
    return GenerationResult(...)
```

### Action Processing Rules — Intended Semantics

1. **ForceTokens queuing:** Tokens appended to `mod_manager.forced_queues[request_id]`. Consumed FIFO.
2. **Backtrack behavior:** consistent and explicit per event phase; implementation may differ from MAX internals.
3. **Terminal short-circuit:** First terminal action stops processing remaining mods for that event.
4. **Added + ForceTokens combination:** New tokens combined with already-added tokens.
5. **Empty Backtrack tokens:** Empty list (not None) with `n > 0` sets `skip_progress` flag.
6. **Forced queue consumption:** If forced queue has tokens, skip sampling — pop from queue.

### Observability Integration — CRITICAL

The existing observability pipeline must keep working:

1. Create `IngestAccumulator` per request
2. Log every mod dispatch: `accumulator.add_mod_call(mod_name, event_type, step)`
3. Log mod stdout: `accumulator.add_mod_log(mod_call_sequence, mod_name, log_message)`
4. Log non-Noop actions: `accumulator.add_action(mod_call_sequence, action_type, action_order, created_at, details)`
5. On complete: `accumulator.finalize()` POSTs to `QUOTE_LOG_INGEST_URL` (default: `http://localhost:6767/v1/ingest`)

### Ingest Payload Rule — IMPORTANT

**`hidden_states`, `attention_patterns`, `layer`, and `input_ids` fields are NEVER serialized to the ingest payload.** These fields exist on event objects in-memory for mods to read during generation, but must be stripped/ignored when `IngestAccumulator` logs events to the Rust backend. The Rust backend doesn't expect them and can't use them.

- Hidden states for Llama-3.1-8B are `(seq_len, 4096)` float32 — megabytes per event
- Attention patterns are `(32, seq_len, seq_len)` float32 — even larger
- Shipping these in every ingest payload would be hundreds of MB per generation request

Activation data is written to a dedicated local store in Phase 0 (see Module 6) and still not sent through Rust ingest payloads.

The Rust backend expects this JSON schema:
```json
{
  "request": { "request_id": "...", "created_at": "...", "model": "...", ... },
  "events": [ { "event_type": "Prefilled|ForwardPass|Sampled|Added", "step": 0, ... } ],
  "mod_calls": [ { "mod_name": "...", "event_type": "...", "step": 0, ... } ],
  "mod_logs": [ { "mod_call_sequence": 0, "mod_name": "...", "log_message": "..." } ],
  "actions": [ { "mod_call_sequence": 0, "action_type": "ForceTokens|...", "details": {...} } ]
}
```

### Output
```python
@dataclass
class GenerationResult:
    output_ids: list[int]
    output_text: str
    events: list[ModEvent]           # full event trace
    actions: list[ModAction]         # all mod actions taken
    metadata: dict                   # timing, backend used, request_id, steps executed
```

---

## Module 4: Mod System — PRESERVE, DON'T PORT

**The mod system does NOT need porting.** It already lives in `engine/sdk/` and `engine/shared/` as backend-agnostic code. The following are reused with zero modifications:

### Already Backend-Agnostic (no changes needed)
- `@mod` decorator (`sdk/quote_mod_sdk/mod.py`)
- `ActionBuilder` (`sdk/quote_mod_sdk/actions.py`)
- `validate_action()` (`shared/src/shared/utils.py`)
- `tokenize()` helper (`sdk/quote_mod_sdk/tokenizer.py`)
- `FlowEngine` (`sdk/quote_mod_sdk/flow.py`)
- `SelfPrompt` / `self_prompt_mod()` (`sdk/quote_mod_sdk/self_prompt.py`)
- All strategy constructors (`sdk/quote_mod_sdk/strategies/`)
- Conversation API (`shared/src/shared/conversation.py`)
- Mod serialization (`sdk/quote_mod_sdk/serialization.py`)
- `ModManager` dispatch (`inference/src/quote/mods/manager.py`)
- Mod loading from payload (`inference/src/quote/mods/sdk_bridge.py`)

### One Critical Dependency: Tensor Type

`SelfPrompt` (~line 280 in `self_prompt.py`) manipulates logits via numpy:
```python
logits_np = event.logits.to_numpy()
# ... mask disallowed tokens ...
return actions.adjust_logits(Tensor.from_numpy(logits_np))
```

This currently uses `max.driver.Tensor`. The `TensorShim` must support `.to_numpy()` and `.from_numpy()` with the same interface. If the shim works, SelfPrompt works unchanged.

Test mods in `engine/tests/mod_unit_tests/forward_pass/test_adjust_logits.py` also manipulate logits — the shim must pass these.

### Production Mods That Must Work

1. **`engine/examples/json_schema/mod.py`** — Uses: `FlowEngine`, `ActionBuilder`, `ChoicesStrat`, `ListStrat`, `CharsStrat`, `get_conversation()`, `get_schemas()`, `AdjustedLogits`
2. **`engine/examples/tau2/mod.py`** — Uses: `FlowEngine`, `ActionBuilder`, `get_conversation()`, `force_output()`

### Test Criteria
- All 24 existing test mods pass on HuggingFace backend
- `json_schema_mod` runs end-to-end
- `airline_helper_v3` runs end-to-end
- `SelfPrompt` constrained generation works with `TensorShim`
- `FlowEngine` multi-step flows work on new generation loop
- `ModManager.dispatch()` contract preserved for mod authors

---

## Module 5: `engine/inference/src/quote/config.py`

**Purpose:** Backend selection and configuration. Single entry point.

```python
def create_backend(config: BackendConfig = None) -> Backend:
    if config is None:
        config = default_config()
    from quote.backends.huggingface import HuggingFaceBackend
    return HuggingFaceBackend(config)

def default_config() -> BackendConfig:
    return BackendConfig(
        backend_type="huggingface",
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        device="auto",                   # mps > cuda > cpu
        hidden_state_layer=16,
        dtype="auto"                     # float32 on cpu/mps, float16 on cuda
    )
```

### Environment Variable Overrides
- `CONCORDANCE_DEVICE=mps|cuda|cpu` — override device auto-detection
- `CONCORDANCE_MODEL=meta-llama/Llama-3.1-8B-Instruct` — override model
- `MODEL_ID=...` — backward-compatible alias for `CONCORDANCE_MODEL` (legacy path support)
- `CONCORDANCE_HIDDEN_LAYER=16` — override hidden state layer
- `HF_TOKEN` — HuggingFace token (already exists in current setup)

### Activation + SAE Flags
- `CONCORDANCE_ACTIVATIONS_ENABLED=true|false` — write activation rows to local store
- `CONCORDANCE_ACTIVATIONS_DB_PATH=./artifacts/activations/activations.duckdb`
- `CONCORDANCE_ACTIVATIONS_PARQUET_PATH=./artifacts/activations/parquet/`
- `CONCORDANCE_ACTIVATION_RETENTION_DAYS=14` — default retention policy
- `CONCORDANCE_SAE_ENABLED=true|false` — enable SAE extraction path
- `CONCORDANCE_SAE_MODE=nearline|inline` — default `nearline`; `inline` is experimental
- `CONCORDANCE_SAE_ID=llama_scope_lxr_8x`
- `CONCORDANCE_SAE_LAYER=16`
- `CONCORDANCE_SAE_TOP_K=20`

---

## Module 6: Minimal Activation Store (Local Queryable Infra)

**Purpose:** Provide a lightweight local data path for rapid feature exploration without introducing full production infra.

### Storage Choice

Use **DuckDB + Parquet**:
- Local-first, no service ops burden
- Columnar compression for manageable disk growth
- Fast analytic queries for "feature ID deltas over time"

### Data Model (Phase 0 minimal)

Persist **top-k SAE feature activations only** per generation step (not full vectors by default):

```text
request_id, step, token_position, token_id, created_at,
sae_release, sae_layer, feature_id, activation_value, rank,
source_mode(nearline|inline), model_id
```

### Query Priorities

1. **Feature ID deltas over time** within a request.
2. **Cross-run threshold search** for feature IDs.
3. **Feature metadata enrichment hook** (Neuronpedia lookup, out of hot path).

### Retention

Default: keep last `14` days of activation rows, configurable by env var.

### Full Vector Migration Path

Schema and writer should be versioned so adding optional full hidden-state vector storage in the next phase is additive (no destructive migration required).

---

## Module 7: Minimal SAE Path (Phase 0)

**Purpose:** Produce real SAE feature IDs during Phase 0 while keeping token-loop latency manageable.

### Modes

1. **Nearline (default):**
   - Generation writes hidden states (or references) needed for post-step extraction.
   - SAE extraction runs asynchronously and writes top-k rows to activation store.
2. **Inline (experimental):**
   - SAE encode runs in token loop.
   - Useful for local experiments and validating real-time behavior.
   - Guarded behind `CONCORDANCE_SAE_MODE=inline`.

### Scope for Phase 0

- Single SAE release + single configured layer by default (`llama_scope_lxr_8x`, layer `16`)
- No full layer/resolution sweeps in hot path
- No feature-triggered action gating requirement in Phase 0 (that remains Phase 1)

---

## Tests

### `test_hf_backend.py`

1. **Model loads on available device** — auto-detects mps/cuda/cpu correctly
2. **Reproducibility smoke test** — fixed seed + temperature=0 is stable enough for debugging
3. **Hidden state shape** — `prefilled.hidden_states.shape == (seq_len, 4096)` for Llama-3.1-8B
4. **Hidden state layer correctness** — layer 16 hidden states differ from layer 0 (not just passed through)
5. **ForceTokens** — injected tokens appear in output exactly
6. **AdjustedLogits** — logit mask changes sampled token at temperature=0
7. **Backtrack** — rewind + regenerate produces different continuation
8. **Backtrack behavior contract** — per-event rewind semantics are explicit and tested
9. **TensorShim round-trip** — `TensorShim.from_numpy(shim.to_numpy())` preserves values
10. **SelfPrompt compatibility** — numpy logit masking works through TensorShim
11. **EOS stops generation** — doesn't run past end-of-sequence token
12. **Max tokens stops generation** — respects limit

### `test_generation.py`

1. **End-to-end with no mods** — generates coherent text
2. **End-to-end with ForceTokens mod** — mod injects tokens correctly
3. **End-to-end with FlowEngine mod** — multi-step mod completes
4. **Observability payload** — `IngestAccumulator` produces valid JSON matching Rust backend schema
5. **All 24 test mods pass** — run the existing mod unit test harness against HuggingFace backend
6. **Production mod smoke test** — `json_schema_mod` and `airline_helper_v3` produce reasonable output

### `test_activation_store.py`

1. **DuckDB writer works locally** — activation rows persist without external services
2. **Top-k schema integrity** — `(request_id, step, feature_id, activation_value, rank)` is valid
3. **Delta query correctness** — feature activation deltas over time are computed correctly
4. **Retention cleanup** — old rows are removed per policy
5. **Nearline SAE extraction path** — hidden states produce top-k feature rows
6. **Inline SAE flag path** — enabling inline mode writes equivalent top-k rows for the same step (tolerance allowed)

---

## Deliverables (Definition of Done)

- [ ] `interface.py` complete with Backend protocol and config types
- [ ] `TensorShim` wrapping `torch.Tensor` with `max.driver.Tensor`-compatible interface
- [ ] HuggingFace backend passes all tests on Mac (MPS or CPU)
- [ ] All 24 existing test mods pass with zero mod changes
- [ ] `json_schema_mod` and `airline_helper_v3` run end-to-end with zero mod changes
- [ ] `SelfPrompt` constrained generation works with `TensorShim`
- [ ] `generation.py` runs end-to-end: prompt in → tokens + hidden states + events out
- [ ] `generation.py` feeds `IngestAccumulator` correctly — log ingestion to Rust backend verified
- [ ] Hidden states at layer 16 accessible inline during generation (no separate forward pass)
- [ ] Attention patterns at configured layer accessible inline during generation
- [ ] Config auto-detects device (mps > cuda > cpu) and works with env var override
- [ ] Local activation store (DuckDB + Parquet) captures top-k SAE feature rows
- [ ] Query helper for "feature ID deltas over time" is available and tested
- [ ] Minimal SAE extraction works in nearline mode
- [ ] Optional inline SAE mode is available behind flag for experimentation
- [ ] Backward-compatible env handling (`MODEL_ID` + `CONCORDANCE_MODEL`)
- [ ] No existing mod code modified
- [ ] MAX Engine code left in place, untouched

## NOT in Scope

- vLLM or any other backend (later, when prod throughput needed for data pipeline)
- Full multi-layer/multi-resolution SAE sweeps in generation hot path
- Rust port of interface layer (deferred — but types designed to be portable)
- Multi-model support (Llama-3.1-8B-Instruct only this phase)
- Batched generation (single-request only; batching is perf optimization for later)
- Production-grade activation warehouse/search service (local analytics only in Phase 0)
- Performance optimization (correctness first, speed later)
- Deleting MAX Engine code
- Modifying any existing mod code — zero changes is a hard requirement
