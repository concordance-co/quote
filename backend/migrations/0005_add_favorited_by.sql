-- Add favorited_by column to requests table
-- This column stores a list of user names who have favorited this request

ALTER TABLE requests
ADD COLUMN favorited_by TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN requests.favorited_by IS 'List of user names who have favorited this request';

-- Index for efficient queries on favorited requests
CREATE INDEX idx_requests_favorited_by ON requests USING GIN (favorited_by);
