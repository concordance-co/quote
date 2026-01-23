-- Add new fields to requests table to support updated inference payload

ALTER TABLE requests
ADD COLUMN user_prompt TEXT,
ADD COLUMN user_prompt_token_ids INT[],
ADD COLUMN active_mod_name VARCHAR(255),
ADD COLUMN final_token_ids INT[],
ADD COLUMN final_text TEXT,
ADD COLUMN inference_stats JSONB;

COMMENT ON COLUMN requests.user_prompt IS 'The original prompt provided by the user';
COMMENT ON COLUMN requests.user_prompt_token_ids IS 'Token IDs of the user prompt';
COMMENT ON COLUMN requests.active_mod_name IS 'Name of the active mod used for the request';
COMMENT ON COLUMN requests.final_token_ids IS 'Final sequence of token IDs generated';
COMMENT ON COLUMN requests.final_text IS 'Final text output generated';
COMMENT ON COLUMN requests.inference_stats IS 'Statistics about the inference (prompt tokens, generated tokens, etc.)';
