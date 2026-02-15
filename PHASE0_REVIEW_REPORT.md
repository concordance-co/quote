# Phase 0 Deep Review: Backend Activation Handlers

## Executive Summary

Phase 0 of `STAGING_ACTIVATIONS_SPEC.md` requires rewiring the backend activation explorer (`backend/src/handlers/activation_explorer.rs`) to stop proxying engine `/debug/fullpass/*` endpoints and instead use:

1. A new **HF inference endpoint** for text generation + token IDs
2. The existing **SAE service** (`PLAYGROUND_SAE_URL`) for feature extraction
3. **Postgres** for persisting preview payloads (new `activation_run_previews` table)

This report identifies every file/function that needs to change, gaps and ambiguities in the spec, missing infrastructure, and proposes concrete implementation tasks.

---

## 1. Current State Analysis

### 1.1 Files with `/debug/fullpass/*` dependency

All in `backend/src/handlers/activation_explorer.rs`:

| Function | Line | Current Behavior | Engine Endpoint Used |
|----------|------|-----------------|---------------------|
| `run_activation()` | 400 | Proxies run to engine | `POST /debug/fullpass/run` |
| `get_activation_rows()` | 783 | Proxies row query to engine | `GET /debug/fullpass/activations` |
| `get_feature_deltas()` | 864 | Proxies delta query to engine | `GET /debug/fullpass/feature-deltas` |
| `get_top_features()` | 926 | Proxies top-features query to engine | `GET /debug/fullpass/top-features` |
| `activation_health()` | 979 | Checks engine health | `GET {ENGINE_BASE_URL}/healthz` |

### 1.2 Engine-related constants/functions to remove

- `DEFAULT_ENGINE_BASE_URL` (line 20) — `http://127.0.0.1:8000`
- `engine_base_url()` (lines 143-148) — reads `ENGINE_BASE_URL` env var
- `build_http_client()` still needed but timeout values may change

### 1.3 Existing infrastructure that can be reused

| Component | Location | Notes |
|-----------|----------|-------|
| `activation_run_index` table | Migration 0013 | Keep as-is for listing/metadata |
| `upsert_run_index()` | Line 200 | Keep for persisting run metadata |
| `list_activation_runs()` | Line 614 | No changes needed (reads from PG) |
| `get_activation_run_summary()` | Line 717 | No changes needed (reads from PG) |
| `map_summary_row()` | Line 265 | No changes needed |
| `parse_cursor()` | Line 187 | No changes needed |
| All request/response types | Lines 24-121 | May need additions, not replacements |
| SAE extract logic | `playground.rs:1283` | `extract_features()` calls `{PLAYGROUND_SAE_URL}/extract_features` — reusable pattern |
| `ModelEndpoints::get_sae_url()` | `playground.rs:76` | Already reads `PLAYGROUND_SAE_URL` |
| Route definitions | `routes.rs:416-467` | Keep all activation routes as-is |

---

## 2. Gaps and Ambiguities

### 2.1 Missing: HF Inference Endpoint (Phase 1 dependency)

**Status:** Does not exist yet. The spec says Phase 0 backend changes should call the HF inference endpoint, but Phase 1 is where that endpoint gets built.

**Impact:** Phase 0 backend cannot be fully tested end-to-end until Phase 1 delivers the HF inference endpoint. However, the backend code can be written to call it, with the understanding that integration testing requires Phase 1.

**Ambiguity:** The spec says the HF endpoint lives in "the same staging engine Modal app" but gives no specific route path. Is it `/hf/inference`? `/v1/hf/completions`? The spec only defines the I/O contract:
- Input: `{prompt, model_id?, max_tokens?, temperature?, top_p?}`
- Output: `{request_id, model_id, output_text, output_token_ids}`

**Recommendation:** Define the endpoint path now (e.g., `POST /v1/hf/generate`) and document it. The `PLAYGROUND_ACTIVATIONS_HF_URL` env var should point to the base URL.

### 2.2 Missing: `activation_run_previews` table (Phase 2)

**Status:** Migration `0014_add_activation_run_previews.sql` does not exist yet. Phase 2 of the spec creates it.

**Impact:** Phase 0 backend handler changes need to write to this table, but it won't exist until Phase 2.

**Recommendation:** Phase 2 (migration) should be done before or concurrently with Phase 0 backend handler changes. The dependency order in the spec (Phase 0 → Phase 1 → Phase 2) seems wrong — the migration should come first or at least with Phase 0.

### 2.3 Ambiguity: `run_activation()` flow — step-by-step logic unclear

The spec describes the new behavior at a high level:
1. Call HF inference endpoint
2. Call SAE extract
3. Persist to `activation_run_index` + `activation_run_previews`
4. Return response

**Missing details:**
- **What exact payload does SAE `/extract_features` expect?** Looking at `playground.rs:1327`, it expects `{tokens: Vec<i64>, top_k?, layer?, injection_positions?}`. The activation explorer needs to call this with `output_token_ids` from HF inference. But should it also include the prompt tokens? The SAE service internally tokenizes using `meta-llama/Llama-3.1-8B-Instruct`, so passing raw token IDs from a different tokenizer could cause mismatches.
- **How are `activation_rows` derived from `feature_timeline`?** The spec says "activation_rows are derived from feature_timeline (preview rows)". The frontend expects rows with `{step, token_position, feature_id, activation_value, rank}`. The SAE service returns `feature_timeline` with `{position, token, token_str, top_features: [{id, activation}]}`. A transformation is needed to flatten the timeline into rows with rank assignment.
- **How are `events_count`, `actions_count`, `unique_features_count` computed?** In the new flow, there are no engine events/actions. The spec says "events and actions can be empty for now". So `events_count` and `actions_count` should be 0. `unique_features_count` should be derived from the feature_timeline.

### 2.4 Ambiguity: `get_activation_rows()` — deriving rows from Postgres

The spec says: "Read preview payload from Postgres, derive a rows table."

**Missing details:**
- The `feature_timeline` stored in `activation_run_previews` is JSONB. The handler needs to:
  1. Fetch the JSONB blob
  2. Flatten it into `{step, token_position, feature_id, activation_value, rank, token_id}` rows
  3. Apply query filters (feature_id, token_start, token_end, rank_max, limit)
- Should this filtering happen in Postgres (JSONB query) or in Rust (parse JSON, filter in memory)?
- For small previews (< 500 positions × 20 features = 10K rows), in-memory filtering is fine. JSONB queries for this would be over-engineered.

**Recommendation:** Parse JSONB in Rust, apply filters in memory. Add a `step` field convention: for a single-step generation, `step` = `position` from the timeline.

### 2.5 Ambiguity: `get_top_features()` — aggregation source

The spec says: "Read feature_timeline from Postgres and aggregate: max_activation per feature_id, hits count."

**Missing details:**
- The current frontend expects `{request_id, items: [{feature_id, max_activation, hits}]}`.
- The current handler returns raw engine JSON. The new handler must construct this shape.
- Aggregation should be: for each unique feature_id across all positions, compute `max(activation)` and count of positions where it appears.

### 2.6 Ambiguity: `activation_health()` — what to check

The spec says: "check PG reachable, HF inference service reachable, SAE service reachable (optional)."

**Missing details:**
- Current health check calls `{ENGINE_BASE_URL}/healthz`. What should the HF health endpoint be? Just a TCP connect check? An HTTP GET to a specific path?
- Should the response shape change? Currently returns `{status, engine_reachable, index_db_reachable, last_error}`. The spec implies changing to check HF + SAE + PG. Field names should be updated (e.g., `hf_inference_reachable`, `sae_reachable`).

**Frontend impact:** The frontend at line 284 checks `health.status === "ok"` and renders `health.engine_reachable` and `health.index_db_reachable`. If field names change, frontend needs updating too.

**Recommendation:** Keep backward-compatible field names or update frontend simultaneously. Proposed response:
```json
{
  "status": "ok" | "degraded",
  "index_db_reachable": true,
  "hf_inference_reachable": true,
  "sae_reachable": true,
  "last_error": null
}
```

### 2.7 Ambiguity: Auth for activation endpoints

The spec says "No auth for v0" — the routes have no auth middleware. But the SAE endpoints in `playground.rs` require an `X-API-Key` header.

**Question:** When the activation explorer handler calls SAE `/extract_features` internally, does it need an API key? If so, whose key? A service-to-service key? Or should the SAE call be made without auth (internal service mesh)?

**Recommendation:** Since this is staging, make the internal SAE call without auth, or use a configured service key from env.

### 2.8 Missing: Error handling for SAE service failures

The spec doesn't specify what happens if:
- HF inference succeeds but SAE extraction fails
- HF inference times out
- SAE returns partial results

**Recommendation:**
- If HF inference fails: return error, persist error status to index
- If SAE extraction fails: still persist the run with `output_text` and `output_token_ids` but with empty `feature_timeline`, and set a warning/partial status
- SAE failure should not block returning the generation result

### 2.9 Ambiguity: `model_id` default and routing

The spec says: "Backend should treat any unknown/empty as 'use the staging HF default' for now."

The default should be `meta-llama/Llama-3.1-8B-Instruct`. But the existing `ActivationRunRequest` has `model_id: Option<String>`. What value should be stored in the index and preview tables when the default is used?

**Recommendation:** Default to `"meta-llama/Llama-3.1-8B-Instruct"` and store that string in the database.

### 2.10 Response shape: `output_ids` vs `output_token_ids`

The current `run_activation()` handler reads `output_ids` from engine JSON (line 516). The HF inference spec says the output field is `output_token_ids`. The frontend `ActivationOutput` type expects `token_ids: Vec<i64>`. These naming inconsistencies need to be resolved.

**Current mapping:** Engine returns `output_ids` → handler maps to `ActivationOutput.token_ids`.
**New mapping:** HF returns `output_token_ids` → handler maps to `ActivationOutput.token_ids`.

### 2.11 Missing: `PLAYGROUND_ACTIVATIONS_HF_URL` environment variable

Not set anywhere in the codebase. Needs to be:
1. Added to backend env config documentation
2. Added to Modal backend deployment (Vercel rewrites / Modal secrets)
3. Read in the activation_explorer handler

---

## 3. Dependency / Ordering Constraints

The spec's phase ordering has a problem:

```
Phase 0: Backend handler changes (needs HF endpoint + previews table)
Phase 1: Add HF inference endpoint (engine)
Phase 2: Add Postgres migration (activation_run_previews)
```

**Problem:** Phase 0 depends on both Phase 1 and Phase 2 to be functional. You can't test Phase 0 without the HF endpoint (Phase 1) and the preview table (Phase 2).

**Recommended reordering:**
1. **Phase 2 first:** Create the `activation_run_previews` migration (simple, no dependencies)
2. **Phase 1 next:** Build the HF inference endpoint in the engine
3. **Phase 0 last:** Rewire backend handlers (can now test end-to-end)

Or, do Phase 2 + Phase 0 concurrently, mocking the HF endpoint for testing, then integrate with Phase 1 when ready.

---

## 4. Files That Need to Change

### Must change:

| File | What Changes | Impact |
|------|-------------|--------|
| `backend/src/handlers/activation_explorer.rs` | Major rewrite of 5 functions | ~400 LOC changed |
| `backend/migrations/0014_add_activation_run_previews.sql` | New file | ~20 LOC |

### Likely need changes:

| File | What Changes | Impact |
|------|-------------|--------|
| `backend/src/utils/config.rs` | Add `PLAYGROUND_ACTIVATIONS_HF_URL` | ~5 LOC |
| `frontend/src/components/ActivationExplorer.tsx` | Update health response field names; hide feature deltas panel | ~20 LOC |

### No changes needed:

| File | Reason |
|------|--------|
| `backend/src/routes.rs` | Route paths stay the same |
| `backend/src/handlers/playground.rs` | Injection playground unchanged |
| `backend/src/utils/state.rs` | AppState unchanged |
| `backend/src/handlers/mod.rs` | No new modules needed |
| `backend/migrations/0013_add_activation_run_index.sql` | Keep as-is |

---

## 5. Proposed Implementation Tasks

### Task 1: Create `activation_run_previews` migration
**File:** `backend/migrations/0014_add_activation_run_previews.sql`
**Estimated LOC:** 25

Create the table with:
- `request_id TEXT PRIMARY KEY`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`
- `model_id TEXT NOT NULL`
- `prompt TEXT NOT NULL`
- `output_text TEXT NOT NULL`
- `output_token_ids BIGINT[] NOT NULL`
- `sae_id TEXT NULL`
- `sae_layer INT NULL`
- `sae_top_k INT NULL`
- `feature_timeline JSONB NOT NULL`
- Index on `created_at DESC`

**Dependencies:** None

---

### Task 2: Add HF inference + SAE client functions
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 120

Add helper functions:
1. `hf_inference_url() -> String` — reads `PLAYGROUND_ACTIVATIONS_HF_URL`
2. `sae_url() -> String` — reads `PLAYGROUND_SAE_URL`
3. `call_hf_inference(client, prompt, model_id, max_tokens, temperature, top_p) -> Result<HfInferenceResponse>` — calls HF endpoint, returns `{request_id, model_id, output_text, output_token_ids}`
4. `call_sae_extract(client, token_ids, top_k, layer) -> Result<Vec<FeatureTimelineEntry>>` — calls SAE `/extract_features`, returns parsed feature timeline
5. `upsert_preview(state, request_id, model_id, prompt, output_text, output_token_ids, sae_id, sae_layer, sae_top_k, feature_timeline) -> Result<()>` — inserts/updates `activation_run_previews`
6. `flatten_timeline_to_rows(feature_timeline) -> Vec<ActivationRow>` — converts feature_timeline to flat row format for the rows endpoint
7. `aggregate_top_features(feature_timeline) -> Vec<TopFeatureAggregate>` — aggregates max_activation + hits per feature

**Dependencies:** Task 1

---

### Task 3: Rewrite `run_activation()` handler
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 150

Replace the engine proxy logic:
1. Validate request (keep existing validation)
2. Generate `request_id` (keep existing logic)
3. Call HF inference endpoint
4. Call SAE extract with `output_token_ids`
5. Flatten feature_timeline to `activation_rows`
6. Compute summary stats from feature_timeline
7. Upsert `activation_run_index`
8. Upsert `activation_run_previews`
9. Return `ActivationRunResponse` in the expected shape

Handle error cases:
- HF inference failure → persist error status, return error
- SAE failure → persist partial success (generation OK, no features), return with empty features

**Dependencies:** Tasks 1, 2

---

### Task 4: Rewrite `get_activation_rows()` handler
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 80

Replace engine proxy with Postgres read:
1. Query `activation_run_previews` by `request_id`
2. Parse `feature_timeline` JSONB
3. Flatten to rows: `{step, token_position, feature_id, activation_value, rank, token_id}`
4. Apply query filters (feature_id, token_start, token_end, rank_max)
5. Apply limit
6. Return `{request_id, row_count, rows}`

Now needs `State(state): State<AppState>` parameter (currently doesn't take state).

**Dependencies:** Tasks 1, 2

---

### Task 5: Rewrite `get_top_features()` handler
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 60

Replace engine proxy with Postgres read:
1. Query `activation_run_previews` by `request_id`
2. Parse `feature_timeline` JSONB
3. Aggregate: per feature_id, compute `max_activation` and `hits` count
4. Sort by `max_activation` DESC
5. Apply `n` limit
6. Return `{request_id, items: [{feature_id, max_activation, hits}]}`

Now needs `State(state): State<AppState>` parameter.

**Dependencies:** Tasks 1, 2

---

### Task 6: Rewrite `get_feature_deltas()` to return 501
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 15

Replace engine proxy with:
```rust
StatusCode::NOT_IMPLEMENTED with body:
{"status": "error", "error_code": "NOT_IMPLEMENTED", "message": "Feature deltas are not yet available in staging"}
```

**Dependencies:** None

---

### Task 7: Rewrite `activation_health()` handler
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** 40

Replace engine health check with:
1. Check PG reachable (keep existing)
2. Check HF inference URL reachable (HTTP GET to health/root)
3. Optionally check SAE URL reachable
4. Return updated response shape

**Dependencies:** None

---

### Task 8: Remove dead engine proxy code
**File:** `backend/src/handlers/activation_explorer.rs`
**Estimated LOC:** -60 (deletions)

Remove:
- `DEFAULT_ENGINE_BASE_URL` constant
- `engine_base_url()` function
- `DEFAULT_RUN_TIMEOUT_SECS` and `DEFAULT_QUERY_TIMEOUT_SECS` constants (replace with new timeout constants appropriate for HF + SAE calls)

**Dependencies:** Tasks 3-7

---

### Task 9: Frontend — hide feature deltas panel, update health display
**File:** `frontend/src/components/ActivationExplorer.tsx`
**Estimated LOC:** 20

1. Disable/hide "Feature Delta Timeline" panel or handle 501 gracefully
2. Update health display to show new fields (`hf_inference_reachable`, `sae_reachable` instead of `engine_reachable`)
3. Handle the case where `engine_reachable` field is gone

**Dependencies:** Task 7

---

### Task 10: Add/update environment variables in deployment config
**Files:** Modal deploy configs, staging env
**Estimated LOC:** 10

1. Add `PLAYGROUND_ACTIVATIONS_HF_URL` to backend Modal deployment
2. Ensure `PLAYGROUND_SAE_URL` is set for staging backend
3. Remove `ENGINE_BASE_URL` from activation-related contexts (may still be needed for other things)

**Dependencies:** Phase 1 (HF endpoint must be deployed to get a URL)

---

## 6. Total Estimated Effort

| Task | Est. LOC | Priority |
|------|----------|----------|
| Task 1: Migration | 25 | P0 (blocker) |
| Task 2: Client functions | 120 | P0 (blocker) |
| Task 3: Rewrite run_activation | 150 | P0 |
| Task 4: Rewrite get_activation_rows | 80 | P0 |
| Task 5: Rewrite get_top_features | 60 | P0 |
| Task 6: Feature deltas → 501 | 15 | P0 (quick win) |
| Task 7: Rewrite health | 40 | P1 |
| Task 8: Remove dead code | -60 | P1 (cleanup) |
| Task 9: Frontend updates | 20 | P1 |
| Task 10: Env var config | 10 | P1 |
| **Total** | **~460 net LOC** | |

---

## 7. Key Risks

1. **Phase ordering:** Phase 0 backend changes can't be integration-tested without Phase 1 (HF endpoint) and Phase 2 (migration). Recommend reordering or doing mock-based development.

2. **SAE service contract mismatch:** The SAE `/extract_features` endpoint in `playground.rs` expects `tokens: Vec<i64>` (token IDs from a specific tokenizer). If the HF inference endpoint returns tokens from a different tokenizer configuration, features will be wrong. Both must use the same tokenizer (`meta-llama/Llama-3.1-8B-Instruct`).

3. **JSONB storage size:** If `feature_timeline` is large (say 500 positions × 20 features per position = 10K feature entries), the JSONB blob could be 1-2 MB per run. This is fine for staging but should be monitored.

4. **Handler signature changes:** `get_activation_rows()` and `get_top_features()` currently don't take `State(state)` — they proxy to engine directly. The new implementations need DB access, so their function signatures must change, and `routes.rs` may need updating (though Axum usually handles this via the extractor pattern without route changes).

5. **Frontend backward compatibility:** If health response field names change (`engine_reachable` → `hf_inference_reachable`), the frontend will break unless updated simultaneously.
