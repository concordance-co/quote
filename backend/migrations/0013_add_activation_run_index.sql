-- ============================================================================
-- Add Activation Explorer Run Index
-- ============================================================================
-- Local-first metadata index for activation explorer runs.
-- Full activation rows remain in engine-local DuckDB/parquet.

CREATE TABLE IF NOT EXISTS activation_run_index (
    request_id VARCHAR(255) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_id VARCHAR(255) NOT NULL DEFAULT '',
    prompt_chars INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    events_count INT NOT NULL DEFAULT 0,
    actions_count INT NOT NULL DEFAULT 0,
    activation_rows_count INT NOT NULL DEFAULT 0,
    unique_features_count INT NOT NULL DEFAULT 0,
    sae_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    sae_id VARCHAR(255),
    sae_layer INT,
    duration_ms INT NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL DEFAULT 'ok',
    error_message TEXT,
    top_features_preview JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT activation_run_index_status_check CHECK (status IN ('ok', 'error'))
);

CREATE INDEX IF NOT EXISTS idx_activation_run_index_created_at
    ON activation_run_index (created_at DESC, request_id DESC);

CREATE INDEX IF NOT EXISTS idx_activation_run_index_status
    ON activation_run_index (status);

CREATE INDEX IF NOT EXISTS idx_activation_run_index_model
    ON activation_run_index (model_id);

CREATE INDEX IF NOT EXISTS idx_activation_run_index_sae_enabled
    ON activation_run_index (sae_enabled);

COMMENT ON TABLE activation_run_index IS 'Fast listing/index table for activation explorer runs.';
COMMENT ON COLUMN activation_run_index.top_features_preview IS 'Small preview payload for UI list rendering; not the source of truth.';
