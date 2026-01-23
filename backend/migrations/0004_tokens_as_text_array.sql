-- Migration to change tokens_as_text from TEXT to TEXT[] (array of strings)
-- This allows each token to have a corresponding decoded string
-- This migration is idempotent and safe to run multiple times

-- First, check if we need to migrate (if tokens_as_text is still TEXT type)
DO $$
DECLARE
    current_type text;
BEGIN
    -- Get the current data type of tokens_as_text
    SELECT data_type INTO current_type
    FROM information_schema.columns
    WHERE table_name = 'actions' AND column_name = 'tokens_as_text';

    -- If it's already an array type, we're done
    IF current_type = 'ARRAY' THEN
        RAISE NOTICE 'tokens_as_text is already an array type, skipping migration';
        RETURN;
    END IF;

    -- If the column doesn't exist, create it as TEXT[]
    IF current_type IS NULL THEN
        ALTER TABLE actions ADD COLUMN tokens_as_text TEXT[];
        RAISE NOTICE 'Created tokens_as_text as TEXT[] (column did not exist)';
        RETURN;
    END IF;

    -- Otherwise, we need to migrate from TEXT to TEXT[]
    -- Step 1: Rename old column
    ALTER TABLE actions RENAME COLUMN tokens_as_text TO tokens_as_text_old;

    -- Step 2: Add new column as TEXT[]
    ALTER TABLE actions ADD COLUMN tokens_as_text TEXT[];

    -- Step 3: Migrate data - wrap old single string in an array
    -- This preserves backwards compatibility for existing data
    UPDATE actions
    SET tokens_as_text = ARRAY[tokens_as_text_old]
    WHERE tokens_as_text_old IS NOT NULL;

    -- Step 4: Drop the old column
    ALTER TABLE actions DROP COLUMN tokens_as_text_old;

    RAISE NOTICE 'Successfully migrated tokens_as_text from TEXT to TEXT[]';
END $$;

-- Update comment to reflect new structure
COMMENT ON COLUMN actions.tokens_as_text IS 'Array of decoded text for each token - index corresponds to tokens array';
