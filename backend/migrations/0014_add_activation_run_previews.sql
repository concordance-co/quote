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
