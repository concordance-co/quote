# Staging Activations Playground: Spec + Plan (2026-02-15)

## Goal
Make `/playground/activations` feel “real” in staging:
- The frontend page stays at `/playground/activations`.
- It uses robust backend infrastructure (Postgres persistence) and the existing SAE service.
- It runs on **HF meta weights** for activations work (target: `meta-llama/Llama-3.1-8B-Instruct`).
- It preserves backward compatibility with the existing token-injection/mod playground (which uses the MAX OpenAI-compatible server).

## Current State (What’s Happening Today)

### Frontend
- `frontend/src/components/ActivationExplorer.tsx` calls backend endpoints under `/playground/activations/*`.
- It currently expects:
  - `POST /playground/activations/run` to return `output.text`, `output.token_ids`, and a preview payload.
  - `GET /playground/activations/:request_id/rows` to return tabular “activation rows”.
  - `GET /playground/activations/:request_id/top-features` to return top features.
  - `GET /playground/activations/:request_id/feature-deltas` to return a delta timeline (can be deferred).

### Backend
- `backend/src/handlers/activation_explorer.rs` is “local-first” but is currently **hard-wired to proxy** engine debug endpoints:
  - `POST {ENGINE_BASE_URL}/debug/fullpass/run`
  - `GET  {ENGINE_BASE_URL}/debug/fullpass/activations`
  - `GET  {ENGINE_BASE_URL}/debug/fullpass/top-features`
  - `GET  {ENGINE_BASE_URL}/debug/fullpass/feature-deltas`
- It also maintains a lightweight Postgres index table:
  - `backend/migrations/0013_add_activation_run_index.sql` creates `activation_run_index`.
  - This was intended only for listing/metadata; the “real data” was assumed to live engine-local (duckdb/parquet).

### Engine (Modal)
- A debug-only “fullpass” runtime existed behind `/debug/fullpass/*`.
- Staging crashes occurred because debug initialization pulled in engine-local storage modules and optional deps:
  - `ModuleNotFoundError: No module named 'quote.storage'` (packaging/source-in-image issue).
  - `ModuleNotFoundError: No module named 'duckdb'` (and later `RuntimeError: duckdb is required...`) due to activation storage initialization.

## Changes Already Applied (To Stop Crashing)
These are already in the repo (no further action needed, but keep them as constraints).

1. Engine Modal packaging fix
- File: `engine/inference/src/quote/api/openai/remote.py`
- Change: ship the entire `quote` package via `Image.add_local_python_source("quote", ...)` so new imports don’t crash deploy.

2. Disable debug-only fullpass routes by default
- File: `engine/inference/src/quote/api/openai/local.py`
- Change: fullpass debug routes are now opt-in behind:
  - `CONCORDANCE_ENABLE_FULLPASS_DEBUG=1`
- File: `engine/inference/src/quote/api/openai/remote.py`
- Change: bake `CONCORDANCE_ENABLE_FULLPASS_DEBUG=0` into the image env for staging/prod.

Net effect:
- Staging deploys stop crashing.
- `/debug/fullpass/*` should be considered **disabled** for staging by default.

## Key Product/Infra Decisions (Locked In)
- Activations Playground should start **preview-only** (not full fidelity storage).
- Persist previews in **Postgres** (staging) so it’s safe/robust and supports iterative dev.
- Keep `activation_run_index` as the run listing/index table.
- Add a **new table** for preview payloads (don’t shove big payloads into the index table).
- Feature deltas are **not required now** (endpoint can be `501 Not Implemented`; UI panel should be disabled/hidden).
- Top-features should be supported and easy.
- No token-level interventions/mod infra needs to be enabled for activations yet (it can be “wired” but unused).
- Activations must run on **HF meta weights** (`meta-llama/Llama-3.1-8B-Instruct`).
- The existing injection playground must keep using the MAX OpenAI-compatible service + GGUF routing:
  - Backend currently maps `"llama-3.1-8b"` to `"modularai/Llama-3.1-8B-Instruct-GGUF"` for injection playground.

## Proposed Target Architecture (Staging)

### Components
1. Frontend (existing)
- `/playground/activations` remains the UI.

2. Backend (existing Rust service)
- Owns persistence and “product API” for activations.
- Calls:
  - A **HF inference endpoint** that returns `output_text` + `output_token_ids`.
  - The existing **SAE service** (`PLAYGROUND_SAE_URL`) to compute `feature_timeline`.

3. HF inference service (new endpoint, same staging Modal app)
- Not OpenAI compatible (simple JSON).
- Uses HF meta weights (Llama 3.1 8B Instruct) to produce:
  - `output_text`
  - `output_token_ids` (token IDs are required to call SAE feature extraction)

4. SAE analysis service (already exists)
- Backend already has:
  - `POST /playground/features/extract` which calls `{PLAYGROUND_SAE_URL}/extract_features`
  - `POST /playground/features/analyze` which calls `{PLAYGROUND_SAE_URL}/analyze_features`
- SAE service itself uses `meta-llama/Llama-3.1-8B-Instruct` internally for tokenization/feature mapping.

### Why This Architecture
- Removes any dependency on engine-local duckdb/parquet storage (which is debug-only and brittle for staging).
- Keeps “realness” by persisting runs in PG and using the existing SAE infra.
- Preserves the injection playground unchanged (MAX OpenAI server remains the injection path).

## API Contract (Backend: `/playground/activations/*`)

### `POST /playground/activations/run`
Input (already exists):
```json
{
  "prompt": "string",
  "model_id": "optional string",
  "max_tokens": 128,
  "temperature": 0.7,
  "top_p": 0.95,
  "top_k": 0,
  "collect_activations": true,
  "inline_sae": true,
  "sae_id": "llama_scope_lxr_8x",
  "sae_layer": 16,
  "sae_top_k": 20,
  "request_id": "optional"
}
```

Behavior (new):
1. Pick request_id (stable key; if not provided, generate).
2. Call **HF inference endpoint** (staging engine) with prompt + generation params.
3. Call SAE extract via backend’s existing `/playground/features/extract` logic:
   - Provide token IDs from HF inference.
4. Persist:
   - upsert `activation_run_index` (fast listing)
   - upsert `activation_run_previews` (the actual preview payload)
5. Return:
   - `ActivationRunResponse` shape already expected by frontend.

Notes:
- `events` and `actions` can be empty for now.
- `activation_rows` are derived from `feature_timeline` (preview rows), not from engine-local activation DB.

### `GET /playground/activations/:request_id/rows`
Behavior (new):
- Read preview payload from Postgres, derive a rows table that matches what UI expects:
  - `step`, `token_position`, `feature_id`, `activation_value`, `rank`, optional `token_id`.
- Support query filters (feature_id, token range, rank_max, limit) against the derived set.

### `GET /playground/activations/:request_id/top-features`
Behavior (new):
- Read `feature_timeline` from Postgres and aggregate:
  - `max_activation` per feature id
  - `hits` count per feature id (#positions where it appears in top_k)
- Sort by `max_activation` desc (or `hits` as tie-break).

### `GET /playground/activations/:request_id/feature-deltas`
Behavior (now):
- Return `501 Not Implemented` (or a structured error) until we build it properly.
- Frontend should hide/disable “Feature Delta Timeline” panel to avoid confusion.

### `GET /playground/activations/*` listing and summary
- `runs` and `summary` stay backed by `activation_run_index`.
- `health` should stop checking engine debug endpoints; instead check:
  - PG reachable
  - HF inference service reachable (new)
  - SAE service reachable (optional but recommended)

## Data Model (Postgres)

### Existing table: `activation_run_index`
- Already exists (migration `0013_add_activation_run_index.sql`).
- Keep it small; it’s for listing/metadata.

### New table: `activation_run_previews` (preview-only)
Purpose:
- Store the “source of truth” for the preview experience (tokens + feature timeline).

Proposed schema (high level):
- `request_id TEXT PRIMARY KEY`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `model_id TEXT NOT NULL` (store the HF model id or stable key)
- `prompt TEXT NOT NULL`
- `output_text TEXT NOT NULL`
- `output_token_ids BIGINT[] NOT NULL`
- `sae_id TEXT NULL`
- `sae_layer INT NULL`
- `sae_top_k INT NULL`
- `feature_timeline JSONB NOT NULL`

Indexes:
- `created_at DESC` for recency queries
- Potential GIN on `feature_timeline` can wait; don’t over-index early.

Storage policy (staging):
- Preview-only means we can prune old rows later without breaking product flows.

## Model Routing / “Meta Weights” Guarantee

### Activation explorer model (HF)
- Use HF meta weights:
  - `meta-llama/Llama-3.1-8B-Instruct`
- The activations UI currently has a freeform “Model ID” input defaulting to this value.
- Backend should treat any unknown/empty as “use the staging HF default” for now.

### Injection playground model (MAX + GGUF)
- Keep existing behavior in `backend/src/handlers/playground.rs`:
  - `"llama-3.1-8b"` -> `"modularai/Llama-3.1-8B-Instruct-GGUF"`
- Do not change this as part of the activations work.

## Environment Variables (Staging)

### Backend (Modal)
Required:
- `DATABASE_URL` (staging DB; stored in `MODAL_SECRET_NAME`)

Existing playground infra (keep):
- `PLAYGROUND_LLAMA_8B_URL` (MAX OpenAI server base URL for injection playground)
- `PLAYGROUND_QWEN_14B_URL`
- `PLAYGROUND_SAE_URL` (SAE analysis service base URL)
- `PLAYGROUND_ADMIN_KEY` (register API keys with model servers)

New for activations:
- `PLAYGROUND_ACTIVATIONS_HF_URL`
  - Base URL for the HF inference endpoint (same staging engine app, different route).

Optional but recommended:
- `PUBLIC_BASE_URL` (for generating links/OG)
- `RUST_LOG` / `RUST_LOG_STYLE`

### Engine (Modal)
Keep (already set in image):
- `CONCORDANCE_ENABLE_FULLPASS_DEBUG=0`

HF inference endpoint will also need:
- HF cache volumes (already present in engine image config: `/models`)
- `HF_TOKEN` if the model requires gated access

## Deployment / Rollout Plan (Make Progress Fast)

### Phase 0: Stop relying on `/debug/fullpass/*` (backend)
- Replace calls in `backend/src/handlers/activation_explorer.rs`:
  - Remove `ENGINE_BASE_URL` usage for activations.
  - Use HF inference endpoint + SAE service + Postgres.

### Phase 1: Add HF inference endpoint (engine, same staging app)
- Add a new lightweight HTTP endpoint in the existing staging engine Modal app:
  - Input: `{prompt, model_id?, max_tokens?, temperature?, top_p?}`
  - Output: `{request_id, model_id, output_text, output_token_ids}`
- Keep it separate from the OpenAI-compatible server and MAX inference path.

### Phase 2: Add Postgres migration (backend)
- Add `0014_add_activation_run_previews.sql` to create `activation_run_previews`.
- Run `backend/run_migration.sh` against staging `DATABASE_URL` only.

### Phase 3: Frontend polish (activation explorer)
- Hide/disable “Feature Delta Timeline” panel (since backend returns 501).
- Adjust copy:
  - Replace “Token/feature rows from engine activation store” with “Preview rows from SAE timeline”.

### Acceptance Criteria
- Visiting `/playground/activations` in staging:
  - Running a prompt succeeds end-to-end.
  - Results persist and show up in “Recent Runs” after refresh.
  - “Activation Rows” table populates.
  - “Top Features” populates.
  - No container crashes; no dependency on `/debug/fullpass/*`.
- Injection playground continues working exactly as before.

## Risks / Known Follow-Ups (Not Blockers)
- Modal volumes in engine are currently globally named (`models`, `mods`, `users`, etc.).
  - For strict staging/prod isolation, we should eventually namespace volume names by environment.
- HF inference and MAX inference sharing a GPU container could cause memory contention.
  - Mitigation: keep HF inference endpoint as a separate function/container (still within same Modal app).
- Long-term: “feature deltas” and richer activations storage should be built on a real schema and possibly separate service/storage tier.

