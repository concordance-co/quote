-- Add discussions table for comments on requests
-- Users can leave comments/discussions on specific requests

CREATE TABLE discussions (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE discussions IS 'Comments and discussions on inference requests';
COMMENT ON COLUMN discussions.request_id IS 'The request this comment is associated with';
COMMENT ON COLUMN discussions.username IS 'The user who posted the comment';
COMMENT ON COLUMN discussions.comment IS 'The comment text';
COMMENT ON COLUMN discussions.created_at IS 'When the comment was created';
COMMENT ON COLUMN discussions.updated_at IS 'When the comment was last updated';

-- Indexes for efficient queries
CREATE INDEX idx_discussions_request_id ON discussions(request_id);
CREATE INDEX idx_discussions_username ON discussions(username);
CREATE INDEX idx_discussions_created_at ON discussions(created_at);

-- Index for fetching comments for a request ordered by time
CREATE INDEX idx_discussions_request_timeline ON discussions(request_id, created_at);
