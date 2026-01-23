-- Add collections table for organizing requests
-- This migration creates collections and a junction table to link requests to collections

-- Collections table - stores collection metadata
CREATE TABLE collections (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255)
);

COMMENT ON TABLE collections IS 'Collections for organizing and grouping related requests';
COMMENT ON COLUMN collections.name IS 'Display name of the collection';
COMMENT ON COLUMN collections.description IS 'Optional description of what the collection contains';
COMMENT ON COLUMN collections.created_by IS 'Username/identifier of who created the collection';

-- Junction table for many-to-many relationship between collections and requests
CREATE TABLE collection_requests (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by VARCHAR(255),
    notes TEXT,

    -- Ensure a request can only be in a collection once
    UNIQUE(collection_id, request_id)
);

COMMENT ON TABLE collection_requests IS 'Junction table linking requests to collections';
COMMENT ON COLUMN collection_requests.added_by IS 'Username/identifier of who added this request to the collection';
COMMENT ON COLUMN collection_requests.notes IS 'Optional notes about why this request was added to the collection';

-- Indexes for efficient queries
CREATE INDEX idx_collections_name ON collections(name);
CREATE INDEX idx_collections_created_at ON collections(created_at);
CREATE INDEX idx_collections_created_by ON collections(created_by);

CREATE INDEX idx_collection_requests_collection_id ON collection_requests(collection_id);
CREATE INDEX idx_collection_requests_request_id ON collection_requests(request_id);
CREATE INDEX idx_collection_requests_added_at ON collection_requests(added_at);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_collection_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on collections
CREATE TRIGGER trigger_collections_updated_at
    BEFORE UPDATE ON collections
    FOR EACH ROW
    EXECUTE FUNCTION update_collection_updated_at();

-- View for collection summaries with request counts
CREATE OR REPLACE VIEW collection_summary AS
SELECT
    c.id,
    c.name,
    c.description,
    c.created_at,
    c.updated_at,
    c.created_by,
    COUNT(cr.id) as request_count,
    MAX(cr.added_at) as last_request_added_at
FROM collections c
LEFT JOIN collection_requests cr ON c.id = cr.collection_id
GROUP BY c.id, c.name, c.description, c.created_at, c.updated_at, c.created_by;
