-- ============================================================================
-- Add is_admin Column to API Keys Table
-- ============================================================================
-- This migration adds an explicit is_admin column to allow multiple admin keys
-- and more flexible admin status assignment.

-- Add the is_admin column
ALTER TABLE api_keys
ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- Migrate existing data: keys with NULL allowed_api_key are admins
UPDATE api_keys
SET is_admin = TRUE
WHERE allowed_api_key IS NULL;

-- Add an index for quick admin lookups
CREATE INDEX idx_api_keys_is_admin ON api_keys(is_admin) WHERE is_admin = TRUE;

-- Add comment
COMMENT ON COLUMN api_keys.is_admin IS 'Whether this key has admin privileges (can see all data and manage other keys)';
