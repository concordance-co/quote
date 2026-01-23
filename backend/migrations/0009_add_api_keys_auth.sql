-- ============================================================================
-- API Keys Authentication Schema Migration
-- ============================================================================
-- This migration adds an api_keys table to manage authentication.
-- Each API key is associated with a user/account and determines what data
-- they can access.

-- ============================================================================
-- Create API Keys Table
-- ============================================================================

CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,

    -- The actual API key (hashed for security)
    -- We store a prefix for display purposes and the full hash for validation
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(12) NOT NULL,

    -- Human-readable name for this key
    name VARCHAR(255) NOT NULL,

    -- Description of what this key is used for
    description TEXT,

    -- The user_api_key value in requests table that this key can access
    -- If NULL, this is an admin key that can see all data
    allowed_api_key VARCHAR(255),

    -- Whether this key is currently active
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    -- Optional expiration
    expires_at TIMESTAMPTZ
);

COMMENT ON TABLE api_keys IS 'Stores API keys for authentication. Each key grants access to specific data based on allowed_api_key.';
COMMENT ON COLUMN api_keys.key_hash IS 'SHA-256 hash of the full API key';
COMMENT ON COLUMN api_keys.key_prefix IS 'First 8-12 characters of the key for display (e.g., "ck_abc123...")';
COMMENT ON COLUMN api_keys.name IS 'Human-readable name for this API key';
COMMENT ON COLUMN api_keys.allowed_api_key IS 'The user_api_key in requests that this key can access. NULL means admin access to all data.';
COMMENT ON COLUMN api_keys.is_active IS 'Whether this key is currently active and can be used';
COMMENT ON COLUMN api_keys.last_used_at IS 'Last time this key was used for authentication';
COMMENT ON COLUMN api_keys.expires_at IS 'Optional expiration timestamp. NULL means no expiration.';

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_allowed_api_key ON api_keys(allowed_api_key);
CREATE INDEX idx_api_keys_is_active ON api_keys(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at) WHERE expires_at IS NOT NULL;

-- ============================================================================
-- Helper function to update updated_at timestamp
-- ============================================================================

CREATE OR REPLACE FUNCTION update_api_keys_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER api_keys_updated_at_trigger
    BEFORE UPDATE ON api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_api_keys_updated_at();
