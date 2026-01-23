-- ============================================================================
-- Mod Event and Action Logging Schema Migration
-- ============================================================================
-- This migration implements the new comprehensive logging schema for the
-- Concordance mod system, designed for high-throughput writes and efficient analytics.

-- ============================================================================
-- Drop Old Tables
-- ============================================================================

DROP TABLE IF EXISTS request_inference_stats CASCADE;
DROP TABLE IF EXISTS step_logit_summaries CASCADE;
DROP TABLE IF EXISTS actions CASCADE;
DROP TABLE IF EXISTS request_steps CASCADE;
DROP TABLE IF EXISTS mod_blocks CASCADE;
DROP TABLE IF EXISTS mods CASCADE;
DROP TABLE IF EXISTS requests CASCADE;

-- Drop old types if they exist
DROP TYPE IF EXISTS action_event CASCADE;
DROP TYPE IF EXISTS eos_reason CASCADE;
DROP TYPE IF EXISTS logit_phase CASCADE;
DROP TYPE IF EXISTS action_type CASCADE;

-- ============================================================================
-- Create Enums
-- ============================================================================

CREATE TYPE event_type AS ENUM ('Prefilled', 'ForwardPass', 'Added', 'Sampled');

CREATE TYPE action_type AS ENUM (
    'Noop',
    'AdjustedPrefill',
    'ForceTokens',
    'ForceOutput',
    'Backtrack',
    'AdjustedLogits',
    'ToolCalls',
    'EmitError'
);

CREATE TYPE log_level AS ENUM ('DEBUG', 'INFO', 'WARNING', 'ERROR');

-- ============================================================================
-- Core Tables
-- ============================================================================

-- Top-level tracking of each inference request
CREATE TABLE requests (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    
    -- Request context
    model VARCHAR(255),
    user_api_key VARCHAR(255),
    max_tokens INT,
    temperature FLOAT,
    
    mod TEXT
);

COMMENT ON TABLE requests IS 'Top-level tracking of each inference request';
COMMENT ON COLUMN requests.request_id IS 'Unique request identifier';
COMMENT ON COLUMN requests.created_at IS 'Request start time';
COMMENT ON COLUMN requests.completed_at IS 'Request completion time';

-- Core mod events that flow through the system
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    event_type event_type NOT NULL,
    step INT NOT NULL,
    sequence_order INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Full event details
    details JSONB,
    
    -- Prefilled event fields
    prompt_length INT,
    tokens_so_far_len INT,
    max_steps INT,
    
    -- ForwardPass event fields
    input_text TEXT,
    top_tokens JSONB,
    
    -- Sampled event fields
    sampled_token INT,
    token_text VARCHAR(100),
    
    -- Added event fields
    added_tokens INT[],
    added_token_count INT,
    forced BOOLEAN
);

COMMENT ON TABLE events IS 'Core mod events that flow through the system. Each event type has specific fields relevant to that event.';
COMMENT ON COLUMN events.event_type IS 'Type of mod event';
COMMENT ON COLUMN events.step IS 'Generation step number';
COMMENT ON COLUMN events.sequence_order IS 'Order within request for replay';
COMMENT ON COLUMN events.details IS 'Complete event details';
COMMENT ON COLUMN events.prompt_length IS 'Length of initial prompt (Prefilled only)';
COMMENT ON COLUMN events.tokens_so_far_len IS 'Current token count';
COMMENT ON COLUMN events.max_steps IS 'Maximum generation steps';
COMMENT ON COLUMN events.input_text IS 'Last 70 chars of input for debugging';
COMMENT ON COLUMN events.top_tokens IS 'Top 3 tokens with probabilities [{token, prob}, ...]';
COMMENT ON COLUMN events.sampled_token IS 'Token ID that was sampled';
COMMENT ON COLUMN events.token_text IS 'Decoded token text';
COMMENT ON COLUMN events.added_tokens IS 'Array of added token IDs';
COMMENT ON COLUMN events.added_token_count IS 'Number of tokens added';
COMMENT ON COLUMN events.forced IS 'Whether tokens were forced';

-- Tracks every mod invocation for each event
CREATE TABLE mod_calls (
    id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    
    -- Mod identification
    mod_name VARCHAR(255) NOT NULL,
    event_type event_type NOT NULL,
    step INT NOT NULL,
    
    -- Timing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    execution_time_ms FLOAT,
    
    -- Error tracking
    exception_occurred BOOLEAN DEFAULT FALSE,
    exception_message TEXT,
    exception_traceback TEXT
);

COMMENT ON TABLE mod_calls IS 'Tracks every mod invocation for each event. Captures performance and error information.';
COMMENT ON COLUMN mod_calls.mod_name IS 'Name of the mod being called';
COMMENT ON COLUMN mod_calls.event_type IS 'Event type that triggered this mod';
COMMENT ON COLUMN mod_calls.step IS 'Generation step';
COMMENT ON COLUMN mod_calls.execution_time_ms IS 'Time spent executing this mod in milliseconds';
COMMENT ON COLUMN mod_calls.exception_occurred IS 'Whether mod threw exception';
COMMENT ON COLUMN mod_calls.exception_message IS 'Exception message if error occurred';
COMMENT ON COLUMN mod_calls.exception_traceback IS 'Full exception traceback';

-- Captures all output from mods (print statements, logs)
CREATE TABLE mod_logs (
    id BIGSERIAL PRIMARY KEY,
    mod_call_id BIGINT NOT NULL REFERENCES mod_calls(id) ON DELETE CASCADE,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    mod_name VARCHAR(255) NOT NULL,
    
    -- Log content
    log_message TEXT NOT NULL,
    log_level log_level DEFAULT 'INFO',
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE mod_logs IS 'Captures all output from mods (print statements, logs). Essential for debugging mod logic.';
COMMENT ON COLUMN mod_logs.log_message IS 'Full log message from mod';
COMMENT ON COLUMN mod_logs.log_level IS 'Log severity level';

-- Records all actions returned by mods
CREATE TABLE actions (
    id BIGSERIAL PRIMARY KEY,
    mod_call_id BIGINT NOT NULL REFERENCES mod_calls(id) ON DELETE CASCADE,
    request_id VARCHAR(255) NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
    action_type action_type NOT NULL,
    action_order INT NOT NULL,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Full action details
    details JSONB,
    
    -- AdjustedPrefill fields
    new_prompt TEXT,
    new_length INT,
    adjusted_max_steps INT,
    
    -- ForceTokens / ForceOutput fields
    token_count INT,
    tokens_preview TEXT,
    
    -- Backtrack fields
    backtrack_steps INT,
    backtrack_token_count INT,
    
    -- AdjustedLogits fields
    logits_shape VARCHAR(100),
    temperature FLOAT,
    
    -- ToolCalls fields
    has_tool_calls BOOLEAN,
    tool_calls JSONB,
    
    -- EmitError fields
    error_message TEXT
);

COMMENT ON TABLE actions IS 'Records all actions returned by mods. Different action types have different relevant fields.';
COMMENT ON COLUMN actions.action_type IS 'Type of action returned by mod';
COMMENT ON COLUMN actions.action_order IS 'Order if multiple actions from same mod';
COMMENT ON COLUMN actions.details IS 'Complete action details';
COMMENT ON COLUMN actions.new_prompt IS 'Can be null -- new prompt if changed';
COMMENT ON COLUMN actions.new_length IS 'New prompt length (AdjustedPrefill)';
COMMENT ON COLUMN actions.adjusted_max_steps IS 'Adjusted max steps (AdjustedPrefill)';
COMMENT ON COLUMN actions.token_count IS 'Number of forced tokens';
COMMENT ON COLUMN actions.tokens_preview IS 'First 10 tokens as string for readability';
COMMENT ON COLUMN actions.backtrack_steps IS 'Number of steps to backtrack';
COMMENT ON COLUMN actions.backtrack_token_count IS 'Number of replacement tokens';
COMMENT ON COLUMN actions.logits_shape IS 'Shape of logits tensor';
COMMENT ON COLUMN actions.has_tool_calls IS 'Whether tool calls are present';
COMMENT ON COLUMN actions.tool_calls IS 'Full tool call payload';
COMMENT ON COLUMN actions.error_message IS 'Error message for EmitError action';

-- ============================================================================
-- Indexes
-- ============================================================================

-- Requests indexes
CREATE INDEX idx_requests_request_id ON requests(request_id);
CREATE INDEX idx_requests_created_at ON requests(created_at);
CREATE INDEX idx_requests_user_api_key ON requests(user_api_key);

-- Events indexes
CREATE INDEX idx_events_request_id ON events(request_id);
CREATE INDEX idx_events_event_type ON events(event_type);
CREATE INDEX idx_events_created_at ON events(created_at);
CREATE INDEX idx_events_request_step ON events(request_id, step);
CREATE INDEX idx_events_request_sequence ON events(request_id, sequence_order);

-- Mod calls indexes
CREATE INDEX idx_mod_calls_event_id ON mod_calls(event_id);
CREATE INDEX idx_mod_calls_request_id ON mod_calls(request_id);
CREATE INDEX idx_mod_calls_mod_name ON mod_calls(mod_name);
CREATE INDEX idx_mod_calls_created_at ON mod_calls(created_at);
-- Partial index for exceptions
CREATE INDEX idx_mod_calls_exception ON mod_calls(exception_occurred) WHERE exception_occurred = TRUE;

-- Mod logs indexes
CREATE INDEX idx_mod_logs_mod_call_id ON mod_logs(mod_call_id);
CREATE INDEX idx_mod_logs_request_id ON mod_logs(request_id);
CREATE INDEX idx_mod_logs_mod_name ON mod_logs(mod_name);
CREATE INDEX idx_mod_logs_created_at ON mod_logs(created_at);
CREATE INDEX idx_mod_logs_log_level ON mod_logs(log_level);

-- Actions indexes
CREATE INDEX idx_actions_mod_call_id ON actions(mod_call_id);
CREATE INDEX idx_actions_request_id ON actions(request_id);
CREATE INDEX idx_actions_action_type ON actions(action_type);
CREATE INDEX idx_actions_created_at ON actions(created_at);
-- Partial index for non-Noop actions
CREATE INDEX idx_actions_non_noop ON actions(action_type) WHERE action_type != 'Noop';

-- ============================================================================
-- Analytics Views
-- ============================================================================

-- Request summary view
CREATE OR REPLACE VIEW request_summary AS
SELECT 
    r.request_id,
    r.created_at,
    r.completed_at,
    r.model,
    r.user_api_key,
    COUNT(DISTINCT e.id) FILTER (WHERE e.event_type = 'Prefilled') as prefilled_events,
    COUNT(DISTINCT e.id) FILTER (WHERE e.event_type = 'ForwardPass') as forward_pass_events,
    COUNT(DISTINCT e.id) FILTER (WHERE e.event_type = 'Added') as added_events,
    COUNT(DISTINCT e.id) FILTER (WHERE e.event_type = 'Sampled') as sampled_events,
    COUNT(DISTINCT mc.id) as total_mod_calls,
    COUNT(DISTINCT a.id) as total_actions,
    SUM(mc.execution_time_ms) as total_execution_time_ms,
    COUNT(DISTINCT mc.id) FILTER (WHERE mc.exception_occurred = TRUE) as exception_count
FROM requests r
LEFT JOIN events e ON r.request_id = e.request_id
LEFT JOIN mod_calls mc ON e.id = mc.event_id
LEFT JOIN actions a ON mc.id = a.mod_call_id
GROUP BY r.request_id, r.created_at, r.completed_at, r.model, r.user_api_key;

-- Mod performance view
CREATE OR REPLACE VIEW mod_performance AS
SELECT 
    mod_name,
    event_type,
    COUNT(*) as call_count,
    AVG(execution_time_ms) as avg_execution_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_time_ms) as p50_execution_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms) as p95_execution_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY execution_time_ms) as p99_execution_ms,
    COUNT(*) FILTER (WHERE exception_occurred = TRUE) as exception_count,
    COUNT(*) FILTER (WHERE exception_occurred = TRUE)::FLOAT / COUNT(*) as exception_rate
FROM mod_calls
GROUP BY mod_name, event_type;

-- Action distribution view
CREATE OR REPLACE VIEW action_distribution AS
SELECT 
    action_type,
    COUNT(*) as action_count,
    COUNT(DISTINCT request_id) as request_count,
    COUNT(DISTINCT mod_call_id) as mod_call_count
FROM actions
GROUP BY action_type;
