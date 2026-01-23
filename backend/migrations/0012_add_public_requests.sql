-- ============================================================================
-- Add Public Requests Support
-- ============================================================================
-- This migration adds the ability to make individual requests public with shareable links.
-- Public requests can be viewed by anyone with the link, without authentication.

-- Add public columns to requests table
ALTER TABLE requests
ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE requests
ADD COLUMN public_token VARCHAR(64) UNIQUE;

-- Add index for public token lookups
CREATE INDEX idx_requests_public_token ON requests(public_token) WHERE public_token IS NOT NULL;

-- Add index for listing public requests
CREATE INDEX idx_requests_is_public ON requests(is_public) WHERE is_public = TRUE;

-- Add comments
COMMENT ON COLUMN requests.is_public IS 'Whether this request is publicly accessible via shareable link';
COMMENT ON COLUMN requests.public_token IS 'Unique token for public access URL. NULL if request is not public.';
