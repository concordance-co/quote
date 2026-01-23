-- ============================================================================
-- Add Public Collections Support
-- ============================================================================
-- This migration adds the ability to make collections public with shareable links.
-- Public collections can be viewed by anyone with the link, without authentication.

-- Add public columns to collections table
ALTER TABLE collections
ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE collections
ADD COLUMN public_token VARCHAR(64) UNIQUE;

-- Add index for public token lookups
CREATE INDEX idx_collections_public_token ON collections(public_token) WHERE public_token IS NOT NULL;

-- Add index for listing public collections
CREATE INDEX idx_collections_is_public ON collections(is_public) WHERE is_public = TRUE;

-- Add comments
COMMENT ON COLUMN collections.is_public IS 'Whether this collection is publicly accessible via shareable link';
COMMENT ON COLUMN collections.public_token IS 'Unique token for public access URL. NULL if collection is not public.';
