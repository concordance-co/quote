-- Add tags column to requests table
-- This column stores a list of tags for categorizing/filtering requests

ALTER TABLE requests
ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN requests.tags IS 'List of tags for categorizing and filtering requests';

-- Index for efficient queries on tagged requests
CREATE INDEX idx_requests_tags ON requests USING GIN (tags);
