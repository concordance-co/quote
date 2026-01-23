use chrono::{DateTime, Utc};
use serde::Deserialize;
use serde_json::Value;

use super::util::deserialize_timestamp_opt;

// ============================================================================
// Top-level payload
// ============================================================================

#[derive(Debug, Deserialize)]
pub struct FullIngestPayload {
    pub request: RequestRecord,
    #[serde(default)]
    pub events: Vec<EventRecord>,
    #[serde(default)]
    pub mod_calls: Vec<ModCallRecord>,
    #[serde(default)]
    pub mod_logs: Vec<ModLogRecord>,
    #[serde(default)]
    pub actions: Vec<ActionRecord>,
}

// ============================================================================
// Core records
// ============================================================================

#[derive(Debug, Deserialize)]
pub struct RequestRecord {
    pub request_id: String,
    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub created_at: Option<DateTime<Utc>>,
    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub completed_at: Option<DateTime<Utc>>,

    // Request context
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub user_api_key: Option<String>,
    #[serde(default)]
    pub max_tokens: Option<i32>,
    #[serde(default)]
    pub temperature: Option<f64>,
    #[serde(default)]
    pub mod_text: Option<String>,
    #[serde(default)]
    pub user_prompt: Option<String>,
    #[serde(default)]
    pub user_prompt_token_ids: Option<Vec<i32>>,
    #[serde(default)]
    pub active_mod_name: Option<String>,
    #[serde(default)]
    pub final_token_ids: Option<Vec<i32>>,
    #[serde(default)]
    pub final_text: Option<String>,
    #[serde(default)]
    pub inference_stats: Option<Value>,
}

#[derive(Debug, Deserialize)]
pub struct EventRecord {
    pub event_type: EventType,
    pub step: i32,
    pub sequence_order: i32,
    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub created_at: Option<DateTime<Utc>>,

    // Full event details
    #[serde(default)]
    pub details: Option<Value>,

    // Prefilled event fields
    #[serde(default)]
    pub prompt_length: Option<i32>,
    #[serde(default)]
    pub tokens_so_far_len: Option<i32>,
    #[serde(default)]
    pub max_steps: Option<i32>,

    // ForwardPass event fields
    #[serde(default)]
    pub input_text: Option<String>,
    #[serde(default)]
    pub top_tokens: Option<Value>,

    // Sampled event fields
    #[serde(default)]
    pub sampled_token: Option<i32>,
    #[serde(default)]
    pub token_text: Option<String>,

    // Added event fields
    #[serde(default)]
    pub added_tokens: Option<Vec<i32>>,
    #[serde(default)]
    pub added_token_count: Option<i32>,
    #[serde(default)]
    pub forced: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct ModCallRecord {
    pub event_sequence_order: i32, // Used to link to event

    // Mod identification
    pub mod_name: String,
    pub event_type: EventType,
    pub step: i32,

    // Timing
    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub created_at: Option<DateTime<Utc>>,
    #[serde(default)]
    pub execution_time_ms: Option<f64>,

    // Error tracking
    #[serde(default)]
    pub exception_occurred: bool,
    #[serde(default)]
    pub exception_message: Option<String>,
    #[serde(default)]
    pub exception_traceback: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ModLogRecord {
    pub mod_call_sequence: i32, // Used to link to mod_call (event_sequence + mod lookup)
    pub mod_name: String,

    // Log content
    pub log_message: String,
    #[serde(default)]
    pub log_level: LogLevel,

    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub created_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Deserialize)]
pub struct ActionRecord {
    pub mod_call_sequence: i32, // Used to link to mod_call
    pub action_type: ActionType,
    pub action_order: i32,

    #[serde(default, deserialize_with = "deserialize_timestamp_opt")]
    pub created_at: Option<DateTime<Utc>>,

    // Full action details
    #[serde(default)]
    pub details: Option<Value>,

    // AdjustedPrefill fields
    #[serde(default)]
    pub new_prompt: Option<String>,
    #[serde(default)]
    pub new_length: Option<i32>,
    #[serde(default)]
    pub adjusted_max_steps: Option<i32>,

    // ForceTokens / ForceOutput fields
    #[serde(default)]
    pub token_count: Option<i32>,
    #[serde(default)]
    pub tokens: Option<Vec<i32>>,
    #[serde(default)]
    pub tokens_preview: Option<String>,

    // Backtrack fields
    #[serde(default)]
    pub backtrack_steps: Option<i32>,

    // AdjustedLogits fields
    #[serde(default)]
    pub logits_shape: Option<String>,
    #[serde(default)]
    pub temperature: Option<f64>,

    // ToolCalls fields
    #[serde(default)]
    pub has_tool_calls: Option<bool>,
    #[serde(default)]
    pub tool_calls: Option<Value>,

    // EmitError fields
    #[serde(default)]
    pub error_message: Option<String>,
}

// ============================================================================
// Enums
// ============================================================================

#[derive(Debug, Deserialize, Clone, Copy)]
#[serde(rename_all = "PascalCase")]
pub enum EventType {
    Prefilled,
    ForwardPass,
    Added,
    Sampled,
}

impl EventType {
    pub fn as_str(self) -> &'static str {
        match self {
            EventType::Prefilled => "Prefilled",
            EventType::ForwardPass => "ForwardPass",
            EventType::Added => "Added",
            EventType::Sampled => "Sampled",
        }
    }
}

#[derive(Debug, Deserialize, Clone, Copy)]
#[serde(rename_all = "PascalCase")]
pub enum ActionType {
    Noop,
    AdjustedPrefill,
    ForceTokens,
    ForceOutput,
    Backtrack,
    AdjustedLogits,
    ToolCalls,
    EmitError,
}

impl ActionType {
    pub fn as_str(self) -> &'static str {
        match self {
            ActionType::Noop => "Noop",
            ActionType::AdjustedPrefill => "AdjustedPrefill",
            ActionType::ForceTokens => "ForceTokens",
            ActionType::ForceOutput => "ForceOutput",
            ActionType::Backtrack => "Backtrack",
            ActionType::AdjustedLogits => "AdjustedLogits",
            ActionType::ToolCalls => "ToolCalls",
            ActionType::EmitError => "EmitError",
        }
    }
}

#[derive(Debug, Deserialize, Clone, Copy)]
#[serde(rename_all = "UPPERCASE")]
pub enum LogLevel {
    Debug,
    Info,
    Warning,
    Error,
}

impl LogLevel {
    pub fn as_str(self) -> &'static str {
        match self {
            LogLevel::Debug => "DEBUG",
            LogLevel::Info => "INFO",
            LogLevel::Warning => "WARNING",
            LogLevel::Error => "ERROR",
        }
    }
}

impl Default for LogLevel {
    fn default() -> Self {
        LogLevel::Info
    }
}
