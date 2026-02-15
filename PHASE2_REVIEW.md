# Phase 2 Deep Review: Postgres Migration for `activation_run_previews`

## 1. Executive Summary

Phase 2 of STAGING_ACTIVATIONS_SPEC.md calls for adding a single new migration
(`0014_add_activation_run_previews.sql`) to create the `activation_run_previews` table.
This table persists the "source of truth" for the preview experience — tokens +
feature timeline data — so that activation rows and top features can be served
from Postgres instead of proxying to the engine's `/debug/fullpass/*` endpoints.

After reviewing the spec against the existing codebase, I found the spec is
**mostly complete** but has several gaps and ambiguities that need resolution
before implementation. This report documents all findings and proposes concrete
implementation tasks.

---

## 2. Current State Analysis

### 2.1 Migration Framework
- **Tool**: SQLx 0.7 (Postgres) with a custom `run_migration.sh` bash runner
- **Pattern**: Sequential `.sql` files in `backend/migrations/` using zero-padded
  numeric prefixes (`0001_` through `0013_`)
- **Execution**: Manual via `psql` — migrations are NOT auto-run at server startup
  (the `sqlx::migrate!()` macro is commented out in `server.rs:17-22`)
- **No tracking table**: The project does NOT use SQLx's `_sqlx_migrations` table
  for tracking applied migrations. The runner script blindly re-executes files.

### 2.2 Existing Activation Tables
- **`activation_run_index`** (migration 0013): Lightweight metadata/listing table
  with `request_id VARCHAR(255) PRIMARY KEY`, plus summary stats (prompt_chars,
  output_tokens, events/actions counts, SAE config, status, etc.)
- **No preview/payload table** exists yet — the "real data" was assumed to live
  engine-local in DuckDB/parquet.

### 2.3 Query Patterns
- All queries use **raw SQL via `sqlx::query`** with manual `.bind()` calls
- Row mapping uses `sqlx::Row::try_get()` (manual, not `query_as!`)
- UPSERT via `INSERT ... ON CONFLICT (request_id) DO UPDATE SET ...`
- Dynamic filters built with `sqlx::QueryBuilder<Postgres>`
- Cursor-based pagination using `(created_at, request_id)` compound key

### 2.4 Relevant Rust Types
The SAE service returns `feature_timeline` as:
```rust
pub struct FeatureTimelineEntry {
    pub position: usize,          // 0-indexed position in sequence
    pub token: i64,               // token ID
    pub token_str: String,        // decoded token text
    pub top_features: Vec<FeatureActivation>,
}

pub struct FeatureActivation {
    pub id: i64,                  // feature ID
    pub activation: f64,          // activation value
}
```

The frontend expects **activation rows** as:
```json
{ "step": 0, "token_position": 0, "feature_id": 1234, "activation_value": 2.456, "rank": 1 }
```

And **top features** as:
```json
{ "feature_id": 1234, "max_activation": 2.456, "hits": 15 }
```

---

## 3. Spec vs. Codebase Gap Analysis

### 3.1 Schema Gaps (Spec is Ambiguous or Missing)

| Issue | Spec Says | What's Needed | Recommendation |
|-------|-----------|---------------|----------------|
| **PK type** | `request_id TEXT PRIMARY KEY` | Existing `activation_run_index` uses `VARCHAR(255)`. Should match. | Use `VARCHAR(255)` for consistency |
| **FK constraint** | Not mentioned | Should `request_id` FK to `activation_run_index`? | **Yes** — add `REFERENCES activation_run_index(request_id) ON DELETE CASCADE`. This ensures previews can't be orphaned and cascade-deletes work. |
| **`output_token_ids` type** | `BIGINT[] NOT NULL` | Current Rust code uses `Vec<i64>` for token IDs. BIGINT[] maps correctly to `Vec<i64>` in sqlx. | Use `BIGINT[] NOT NULL` as spec says |
| **`feature_timeline` JSONB structure** | "JSONB NOT NULL" but no schema specified | Should be `Vec<FeatureTimelineEntry>` serialized as JSON. Typical payload is ~1-50KB. | Document the expected JSON schema in migration comments |
| **`sae_top_k` column** | Listed in spec schema | Not present in `activation_run_index`. Needed to know how many features per position were requested. | Add `sae_top_k INT NULL` as spec says |
| **`updated_at` trigger** | Not mentioned | `activation_run_index` sets `updated_at = NOW()` in the UPSERT. The previews table should do the same via UPSERT, no trigger needed. | No trigger — just set in UPSERT |
| **Size limits** | Not discussed | `feature_timeline` JSONB could be large (128 tokens × 20 features = 2560 entries). At ~50 bytes each ≈ 128KB per row. Acceptable for staging. | Add a `COMMENT` noting expected payload size |
| **GIN index** | "can wait; don't over-index early" | Correct — no GIN index on `feature_timeline` for now. | Skip GIN index |
| **`model_id` default** | `TEXT NOT NULL` | Existing index table uses `VARCHAR(255) NOT NULL DEFAULT ''`. For consistency use VARCHAR(255). | `VARCHAR(255) NOT NULL DEFAULT ''` |
| **UUID generation** | Spec says "Pick request_id (stable key; if not provided, generate)" | Already implemented in handler: `format!("ax-{}", Uuid::new_v4().simple())`. No schema change needed. | No action — `uuid` crate v1 with `v4` feature is already in Cargo.toml |

### 3.2 Missing Spec Details

1. **No `prompt` column length limit**: The spec says `prompt TEXT NOT NULL` but the
   handler already validates max 12,000 chars. TEXT is fine but should add a CHECK
   or note this.

2. **No `output_text` size consideration**: Output text could be up to 2048 tokens
   (max_tokens limit). TEXT type is appropriate.

3. **No mention of `sae_top_k` in index table**: The previews table has `sae_top_k`
   but `activation_run_index` doesn't. This is fine — it's only needed for the
   preview data context.

4. **No pruning/TTL mechanism defined**: Spec says "we can prune old rows later"
   but doesn't define when or how. Not a blocker — just needs a `created_at`
   index (which is already proposed).

5. **Idempotency of migration**: The migration runner re-executes all migrations
   on every run. The SQL MUST use `CREATE TABLE IF NOT EXISTS` and
   `CREATE INDEX IF NOT EXISTS` (matching existing migration patterns).

### 3.3 Handler Changes Required (Beyond Phase 2 Scope but Informing It)

The migration itself (Phase 2) is pure SQL, but the **Rust code changes** needed
to USE the new table are significant and should be planned as follow-on tasks:

1. **New `upsert_run_preview()` function**: Analogous to `upsert_run_index()` but
   writing to `activation_run_previews`. Needs to serialize `feature_timeline`
   as JSONB.

2. **New `ActivationRunPreview` struct**: Maps to the new table columns.

3. **Rewrite `get_activation_rows()`**: Currently proxies to
   `{ENGINE_BASE_URL}/debug/fullpass/activations`. Must instead:
   - Query `feature_timeline` JSONB from Postgres
   - Derive rows: `(step, token_position, feature_id, activation_value, rank)`
   - Apply filters (feature_id, token_start, token_end, rank_max, limit)

4. **Rewrite `get_top_features()`**: Currently proxies to
   `{ENGINE_BASE_URL}/debug/fullpass/top-features`. Must instead:
   - Query `feature_timeline` from Postgres
   - Aggregate: max_activation per feature, hits per feature
   - Sort by max_activation DESC

5. **Rewrite `run_activation()`**: Currently calls
   `{ENGINE_BASE_URL}/debug/fullpass/run`. Must instead:
   - Call HF inference endpoint for `output_text` + `output_token_ids`
   - Call SAE service `/extract_features` for `feature_timeline`
   - Persist both to `activation_run_index` AND `activation_run_previews`

6. **Rewrite `activation_health()`**: Currently checks engine health. Must instead
   check PG reachability, HF inference reachability, SAE service reachability.

---

## 4. Proposed Migration SQL

Based on the analysis, here is the recommended schema for
`0014_add_activation_run_previews.sql`:

```sql
-- ============================================================================
-- Add Activation Run Previews
-- ============================================================================
-- Persists token data + feature timelines for the preview experience.
-- This is the "source of truth" for activation rows and top-features queries.
-- Replaces engine-local DuckDB/parquet storage for staging.
--
-- Expected feature_timeline JSONB structure:
-- [
--   {
--     "position": 0,
--     "token": 259,
--     "token_str": " word",
--     "top_features": [
--       { "id": 1234, "activation": 2.456 },
--       ...
--     ]
--   },
--   ...
-- ]
--
-- Typical payload size: 50-150KB per run (128 tokens × 20 features).

CREATE TABLE IF NOT EXISTS activation_run_previews (
    request_id    VARCHAR(255) PRIMARY KEY
                  REFERENCES activation_run_index(request_id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_id      VARCHAR(255) NOT NULL DEFAULT '',
    prompt        TEXT NOT NULL,
    output_text   TEXT NOT NULL DEFAULT '',
    output_token_ids BIGINT[] NOT NULL DEFAULT '{}',
    sae_id        VARCHAR(255),
    sae_layer     INT,
    sae_top_k     INT,
    feature_timeline JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_activation_run_previews_created_at
    ON activation_run_previews (created_at DESC);

COMMENT ON TABLE activation_run_previews IS
    'Preview payload storage for activation explorer. Source of truth for activation rows and top-features in staging.';
COMMENT ON COLUMN activation_run_previews.feature_timeline IS
    'SAE feature timeline: array of {position, token, token_str, top_features: [{id, activation}]}';
COMMENT ON COLUMN activation_run_previews.output_token_ids IS
    'Token IDs from HF inference, stored as BIGINT[] for SAE service compatibility.';
```

### Design Decisions Explained

1. **FK with CASCADE**: `request_id REFERENCES activation_run_index(request_id)
   ON DELETE CASCADE` — deleting from the index automatically cleans up previews.
   This is safe because the index is the "master" record and previews are
   supplementary.

2. **No GIN index on `feature_timeline`**: Per spec guidance. JSONB queries will
   be full-scan within a single row (we load the whole timeline per request_id),
   not cross-row searches.

3. **No separate `token_id` column**: `output_token_ids` as `BIGINT[]` is
   sufficient. The feature_timeline already contains per-position token IDs.

4. **DEFAULT values**: `DEFAULT ''` and `DEFAULT '[]'::jsonb` allow partial
   inserts during error flows where only some data is available.

5. **VARCHAR(255) for request_id**: Matches `activation_run_index` exactly.

---

## 5. Proposed Implementation Tasks

### Task 1: Write Migration SQL File
**What**: Create `backend/migrations/0014_add_activation_run_previews.sql`
with the schema above.
**LOC estimate**: ~35 lines (SQL)
**Dependencies**: None
**Notes**: Must use `IF NOT EXISTS` for idempotency.

### Task 2: Add `ActivationRunPreview` Rust Struct
**What**: Add a new struct in `activation_explorer.rs` (or a new models module)
that maps to the `activation_run_previews` table columns. Include serde derives
for JSON serialization.
**LOC estimate**: ~25 lines
**Dependencies**: Task 1 (schema must be defined first)

### Task 3: Add `upsert_run_preview()` Function
**What**: Write the Postgres UPSERT function for `activation_run_previews`,
similar to the existing `upsert_run_index()`. Must serialize
`Vec<FeatureTimelineEntry>` into JSONB.
**LOC estimate**: ~50 lines
**Dependencies**: Tasks 1, 2

### Task 4: Add `read_preview()` Function
**What**: Query function to load `activation_run_previews` by `request_id`,
deserializing the JSONB `feature_timeline` back into
`Vec<FeatureTimelineEntry>`.
**LOC estimate**: ~30 lines
**Dependencies**: Tasks 1, 2

### Task 5: Implement `derive_activation_rows()` Helper
**What**: Pure function that takes `Vec<FeatureTimelineEntry>` and query filters
(`feature_id`, `token_start`, `token_end`, `rank_max`, `limit`) and returns
the flattened rows the frontend expects:
`Vec<{step, token_position, feature_id, activation_value, rank}>`.
**LOC estimate**: ~60 lines
**Dependencies**: Task 2

### Task 6: Implement `derive_top_features()` Helper
**What**: Pure function that takes `Vec<FeatureTimelineEntry>` and returns
aggregated top features: `Vec<{feature_id, max_activation, hits}>` sorted by
`max_activation DESC`.
**LOC estimate**: ~40 lines
**Dependencies**: Task 2

### Task 7: Integration — Wire `run_activation()` to Persist Previews
**What**: Modify `run_activation()` to call `upsert_run_preview()` after
obtaining HF inference + SAE results (Phase 0/1 must be done first for the
actual HF+SAE call chain; but the persist call can be wired with placeholder
data initially).
**LOC estimate**: ~20 lines (the persist call itself)
**Dependencies**: Tasks 3, and Phase 0/1 completion for full integration

### Task 8: Integration — Rewrite `get_activation_rows()` to Use Postgres
**What**: Replace engine proxy with: read preview from PG → derive rows →
return. Remove `ENGINE_BASE_URL` dependency.
**LOC estimate**: ~40 lines
**Dependencies**: Tasks 4, 5

### Task 9: Integration — Rewrite `get_top_features()` to Use Postgres
**What**: Replace engine proxy with: read preview from PG → derive top
features → return. Remove `ENGINE_BASE_URL` dependency.
**LOC estimate**: ~35 lines
**Dependencies**: Tasks 4, 6

### Task 10: Run Migration Against Staging DB
**What**: Execute `./run_migration.sh 14` against the staging `DATABASE_URL`.
Verify table creation with `\d activation_run_previews`.
**LOC estimate**: 0 (operational task)
**Dependencies**: Task 1

---

## 6. Risks and Considerations

### 6.1 JSONB Performance
The `feature_timeline` column stores the entire timeline as a single JSONB value.
For 128 tokens × 20 features = 2560 feature entries, this is ~50-150KB per row.
PostgreSQL handles this well. However:
- Deriving rows/top-features in Rust (load JSONB → parse → filter/aggregate) is
  done per-request. For a single user in staging, this is negligible.
- If we later need cross-run queries (e.g., "find all runs where feature X
  activated"), we'd need a GIN index or a normalized table. Not needed now.

### 6.2 FK Ordering Constraint
With `REFERENCES activation_run_index(request_id) ON DELETE CASCADE`, the index
row MUST be inserted BEFORE the preview row. The current code already inserts
the index row first in `run_activation()`, so this ordering is naturally
satisfied. The UPSERT for previews should happen AFTER the index upsert.

### 6.3 Migration Runner Idempotency
The `run_migration.sh` script doesn't track which migrations have been applied.
Using `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` ensures
re-running is safe. However, if the schema ever needs to be ALTERED after
initial deployment, a new migration file (0015+) would be needed.

### 6.4 No Rollback Mechanism
There's no `DOWN` migration support. If the table needs to be dropped, it
would require a manual `DROP TABLE activation_run_previews CASCADE;` command.
This is acceptable for staging.

---

## 7. Questions for the Team

1. **Should the FK cascade be `ON DELETE CASCADE` or `ON DELETE SET NULL`?**
   CASCADE is recommended (deleting an index entry also deletes its preview),
   but if there's a use case for keeping orphaned previews, SET NULL would
   require making `request_id` nullable (not recommended).

2. **Should `sae_top_k` be stored in the previews table redundantly, or is it
   sufficient that it's only stored in the SAE extraction response within
   `feature_timeline`?** The spec explicitly includes it as a column, so I've
   kept it.

3. **Is there any need for a `status` column on the previews table?** The index
   table already has `status` ('ok'/'error'). If a run errors, should a partial
   preview still be stored? Currently the spec doesn't mention this.

4. **Token ID type: `BIGINT[]` vs `INT[]`?** The spec says `BIGINT[]` and the
   Rust code uses `Vec<i64>`. LLaMA token IDs fit in INT (max vocab ~128K), but
   BIGINT[] is safer for future models. Keeping BIGINT[] as spec says.
