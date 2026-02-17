# Quote Engine Architecture

This document describes the engine runtime, mod execution model, API surfaces, and the data contracts exported to backend/frontend.

## 1. Role in the System

The engine is the generation runtime and mod-execution plane.

It provides:

- token-by-token generation loop with event/action hooks
- runtime-loadable Python mods
- OpenAI-compatible chat API
- feature extraction/analysis services (inline and standalone)
- ingest payload emission to backend (`/v1/ingest` on backend)

Top-level packages:

- `engine/inference`: server/runtime/backends
- `engine/shared`: event/action types and validation
- `engine/sdk`: mod authoring API (`@mod`, `ActionBuilder`, flow engine)

## 2. Runtime Configuration

Default config factory lives in `engine/inference/src/quote/runtime/config.py`.

Key defaults:

- backend config: `default_backend_config()` (`engine/inference/src/quote/runtime/config.py:41`)
- generation config: `default_generation_config()` (`engine/inference/src/quote/runtime/config.py:57`)
- activation storage config: `default_activation_config()` (`engine/inference/src/quote/runtime/config.py:66`)
- SAE config: `default_sae_config()` (`engine/inference/src/quote/runtime/config.py:81`)

Important env variables:

- model/backend: `CONCORDANCE_MODEL`, `MODEL_ID`, `CONCORDANCE_BACKEND`
- sampling defaults: `CONCORDANCE_MAX_TOKENS`, `CONCORDANCE_TEMPERATURE`, `CONCORDANCE_TOP_P`, `CONCORDANCE_TOP_K`
- activations: `CONCORDANCE_ACTIVATIONS_ENABLED`, `CONCORDANCE_ACTIVATIONS_DB_PATH`, `CONCORDANCE_ACTIVATIONS_PARQUET_PATH`
- SAE: `CONCORDANCE_SAE_ENABLED`, `CONCORDANCE_SAE_MODE`, `CONCORDANCE_SAE_ID`, `CONCORDANCE_SAE_LAYER`, `CONCORDANCE_SAE_TOP_K`

## 3. Backend Abstraction and HF Implementation

Contract is defined in `engine/inference/src/quote/backends/interface.py:46` (`Backend` protocol).

Core methods:

- `prefill`
- `forward_pass`
- `sample`
- `add_tokens`
- `rewind_kv_cache`
- hidden state/attention accessors

Primary implementation: `HuggingFaceBackend` (`engine/inference/src/quote/backends/huggingface.py:110`).

Notable implementation points:

- request-local inference state stored in `_states` (`engine/inference/src/quote/backends/huggingface.py:118`)
- `prefill` seeds KV cache and pending logits (`engine/inference/src/quote/backends/huggingface.py:151`)
- `forward_pass` returns `ForwardPass` with logits + optional hidden/attention (`engine/inference/src/quote/backends/huggingface.py:205`)
- `sample` supports temperature/top-p/top-k (`engine/inference/src/quote/backends/huggingface.py:224`)
- `rewind_kv_cache` rebuilds state from truncated context (`engine/inference/src/quote/backends/huggingface.py:294`)

## 4. Generation Loop (Core Control Path)

The event/action loop is in `engine/inference/src/quote/runtime/generation.py:168` (`generate`).

High-level flow:

1. mark request start in ingest accumulator (`engine/inference/src/quote/runtime/generation.py:185`)
2. prefill and dispatch mod actions (`engine/inference/src/quote/runtime/generation.py:193-229`)
3. per step:
   - forward pass (`engine/inference/src/quote/runtime/generation.py:230`)
   - optional SAE extraction (`engine/inference/src/quote/runtime/generation.py:251-267`)
   - apply `AdjustedLogits`, `Backtrack`, `ForceTokens` (`engine/inference/src/quote/runtime/generation.py:275-303`)
   - sample unless forced queue has tokens (`engine/inference/src/quote/runtime/generation.py:307-321`)
   - apply sampled-event mod actions (`engine/inference/src/quote/runtime/generation.py:331-357`)
   - add token(s), then apply Added-event mod actions (`engine/inference/src/quote/runtime/generation.py:359-407`)
4. finalize output and ingest payload (`engine/inference/src/quote/runtime/generation.py:421`)

Terminal actions short-circuit generation (`ForceOutput`, `ToolCalls`, `EmitError`) via `_is_terminal` (`engine/inference/src/quote/runtime/generation.py:40`).

## 5. Mod Execution Pipeline

### 5.1 Dispatch Manager

`ModManager` (`engine/inference/src/quote/mods/manager.py:34`) dispatches every event to registered mods.

Behavior:

- captures per-mod stdout and stores it on action metadata (`engine/inference/src/quote/mods/manager.py:72-109`)
- appends trace/debug events via shared conversation helpers (`engine/inference/src/quote/mods/manager.py:79-153`)
- maintains per-request forced token queues (`engine/inference/src/quote/mods/manager.py:43-45`)

### 5.2 Payload-to-callable Bridge

`load_mod_from_payload` in `engine/inference/src/quote/mods/sdk_bridge.py:77` supports:

- single-source inline Python mods
- multi-file in-memory bundles
- path-based import mods

It validates returned actions via shared validator (`engine/inference/src/quote/mods/sdk_bridge.py:294-296`).

### 5.3 SDK Authoring API

- action builder: `engine/sdk/quote_mod_sdk/actions.py:24`
- decorator: `engine/sdk/quote_mod_sdk/mod.py:41`
- flow engine: `engine/sdk/quote_mod_sdk/flow.py:275`

Action/event compatibility matrix is enforced in `engine/shared/src/shared/utils.py:19`.

## 6. Ingest Logging and Backend Contract

`IngestAccumulator` is the runtime bridge from generation to backend ingest API:

- class: `engine/inference/src/quote/logs/logger.py:17`
- captures request metadata (`engine/inference/src/quote/logs/logger.py:45`)
- captures events/mod calls/logs/actions (`engine/inference/src/quote/logs/logger.py:103`, `:166`, `:202`, `:228`)
- finalizes by POSTing payload to `QUOTE_LOG_INGEST_URL` (`engine/inference/src/quote/logs/logger.py:423-427`)

Finalize payload shape mirrors backend `FullIngestPayload`.

## 7. API Surfaces

## 7.1 OpenAI-Compatible Local Server

Factory: `engine/inference/src/quote/api/openai/local.py:625`.

Important routes:

- `POST /add_user` (`engine/inference/src/quote/api/openai/local.py:687`)
- `POST /sdk` (`engine/inference/src/quote/api/openai/local.py:716`)
- `POST /v1/mods` (`engine/inference/src/quote/api/openai/local.py:844`)
- `GET /healthz` (`engine/inference/src/quote/api/openai/local.py:889`)
- `GET /v1/models` (`engine/inference/src/quote/api/openai/local.py:897`)
- `POST /v1/chat/completions` (`engine/inference/src/quote/api/openai/local.py:1136`)

Chat endpoint behavior:

- normalizes/augments messages for response format + tools (`engine/inference/src/quote/api/core.py:104`)
- supports streaming and non-streaming modes (`engine/inference/src/quote/api/openai/local.py:1292+`, `1414+`)
- merges worker trace snapshot into ingest accumulator before finalize (`engine/inference/src/quote/api/openai/local.py:1478-1517`)
- emits tool-call style response via helper (`engine/inference/src/quote/api/openai/local.py:1561`)

## 7.2 Standalone HF Inference Service

Factory: `engine/inference/src/quote/api/hf_inference.py:380`.

Routes:

- `GET /health` (`engine/inference/src/quote/api/hf_inference.py:391`)
- `POST /hf/generate` (`engine/inference/src/quote/api/hf_inference.py:401`)
- `POST /hf/extract` (`engine/inference/src/quote/api/hf_inference.py:410`)

Runtime singleton: `_HFRuntime` (`engine/inference/src/quote/api/hf_inference.py:82`).

`/hf/generate` calls the same runtime `generate()` loop with optional inline SAE extraction (`engine/inference/src/quote/api/hf_inference.py:162-222`).

## 7.3 Standalone SAE Service

Factory: `engine/inference/src/quote/api/sae_server.py:18`.

Routes:

- `GET /health` (`engine/inference/src/quote/api/sae_server.py:23`)
- `POST /extract_features` (`engine/inference/src/quote/api/sae_server.py:27`)
- `POST /analyze_features` (`engine/inference/src/quote/api/sae_server.py:103`)

## 8. Activation Storage and Query Layer

Schema and store:

- row schema: `FeatureActivationRow` (`engine/inference/src/quote/storage/activations/schema.py:12`)
- DuckDB table creation: `create_table_sql()` (`engine/inference/src/quote/storage/activations/schema.py:61`)
- store implementation: `ActivationStore` (`engine/inference/src/quote/storage/activations/store.py:18`)

Storage behavior:

- writes rows to DuckDB (`engine/inference/src/quote/storage/activations/store.py:41-84`)
- best-effort Parquet partition dataset write (`engine/inference/src/quote/storage/activations/store.py:133-145`)
- retention cleanup by date (`engine/inference/src/quote/storage/activations/store.py:86-103`)

Query helpers (`engine/inference/src/quote/storage/activations/queries.py:11`) support:

- rows-for-request filtering
- top features aggregation
- feature deltas over time
- threshold searches

## 9. Shared Cross-Package Contracts

`engine/shared/src/shared/types.py` defines canonical event and action classes.

Core event types:

- `Prefilled` (`engine/shared/src/shared/types.py:15`)
- `ForwardPass` (`engine/shared/src/shared/types.py:37`)
- `Sampled` (`engine/shared/src/shared/types.py:74`)
- `Added` (`engine/shared/src/shared/types.py:83`)

Core actions:

- `Noop`, `AdjustedPrefill`, `ForceTokens`, `AdjustedLogits`, `Backtrack`, `ForceOutput`, `ToolCalls`, `EmitError`

Validation rules for event->action legality are in `engine/shared/src/shared/utils.py:19-24`.

## 10. Conversation and Trace Persistence

`engine/shared/src/shared/conversation.py` persists request-scoped state to `/tmp`:

- conversation: `/tmp/{request_id}` (`engine/shared/src/shared/conversation.py:73-83`)
- schemas: `/tmp/{request_id}_schemas` (`engine/shared/src/shared/conversation.py:36-47`)
- debug logs: `/tmp/logs_{request_id}` (`engine/shared/src/shared/conversation.py:109-123`)
- structured trace: `/tmp/trace_{request_id}.json` (`engine/shared/src/shared/conversation.py:128-250`)

This is intentionally process-local and ephemeral.

## 11. Common End-to-End Flow

```text
Client /v1/chat/completions
  -> openai/local chat handler
  -> token generator + mod dispatch loop
  -> ingest accumulator finalized
  -> POST backend /v1/ingest
  -> backend stores + caches + broadcasts
  -> frontend list/detail/stream consume data
```

## 12. Local Usage

From repo root:

```bash
cd engine
uv sync --all-packages
uv pip install -e shared
uv pip install -e sdk
uv pip install -e inference
uv run -m quote.api.openai.local --host 0.0.0.0 --port 8000
```

Useful checks:

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/v1/models
```
