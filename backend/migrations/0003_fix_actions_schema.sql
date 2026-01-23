-- Fix actions table schema to properly handle token fields
-- This migration is idempotent and safe to run multiple times

-- Drop backtrack_token_count if it exists (not needed)
ALTER TABLE actions DROP COLUMN IF EXISTS backtrack_token_count;

-- Add tokens array field if it doesn't exist
ALTER TABLE actions ADD COLUMN IF NOT EXISTS tokens INT[];

-- Add tokens_as_text if it doesn't exist
ALTER TABLE actions ADD COLUMN IF NOT EXISTS tokens_as_text TEXT;

-- Rename tokens_preview to tokens_as_text if tokens_preview exists and tokens_as_text doesn't have data
-- This handles the case where we're upgrading from the old schema
DO $$
BEGIN
    -- Check if tokens_preview column exists
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'actions' AND column_name = 'tokens_preview'
    ) THEN
        -- Copy data from tokens_preview to tokens_as_text if tokens_as_text is empty
        UPDATE actions
        SET tokens_as_text = tokens_preview
        WHERE tokens_as_text IS NULL AND tokens_preview IS NOT NULL;

        -- Drop the old column
        ALTER TABLE actions DROP COLUMN tokens_preview;
    END IF;
END $$;

-- Update comments
COMMENT ON COLUMN actions.tokens IS 'Array of token IDs for ForceTokens/ForceOutput/Backtrack actions';
COMMENT ON COLUMN actions.tokens_as_text IS 'Decoded text representation of tokens for readability';
COMMENT ON COLUMN actions.token_count IS 'Number of tokens in the array';
COMMENT ON COLUMN actions.backtrack_steps IS 'Number of steps to backtrack (Backtrack action only)';
