//! Converts ingest payload data into a `LogResponse` for cache population.
//!
//! This module enables write-through caching by constructing the same response
//! that would be returned by `get_log` directly from the ingested payload data.

use chrono::Utc;
use serde_json::Value;

use crate::handlers::logs::{
    ActionLog, ActiveMod, EventLog, LogResponse, LogStep, ModCallLog, ModLogEntry,
};

use super::payload::{
    ActionRecord, EventRecord, EventType, FullIngestPayload, ModCallRecord, ModLogRecord,
};

/// Convert a full ingest payload into a LogResponse suitable for caching.
///
/// This allows us to populate the cache immediately after a write, so subsequent
/// reads can be served from cache without hitting the database.
pub fn payload_to_response(
    payload: &FullIngestPayload,
    event_ids: &[i64],
    mod_call_ids: &[i64],
) -> LogResponse {
    let request = &payload.request;

    // Build active_mod from active_mod_name
    let active_mod = request.active_mod_name.as_ref().map(|name| ActiveMod {
        id: 0, // No mod IDs in new schema
        name: Some(name.clone()),
    });

    // Convert events
    let events = convert_events(&payload.events, event_ids);

    // Build legacy steps from Sampled events for backwards compatibility
    let steps = build_legacy_steps(&payload.events);

    // Convert mod_calls
    let mod_calls = convert_mod_calls(&payload.mod_calls, event_ids, mod_call_ids);

    // Convert mod_logs
    let mod_logs = convert_mod_logs(&payload.mod_logs, mod_call_ids);

    // Convert actions
    let actions = convert_actions(&payload.actions, mod_call_ids);

    LogResponse {
        request_id: request.request_id.clone(),
        created_ts: request.created_at.unwrap_or_else(Utc::now),
        finished_ts: request.completed_at,
        system_prompt: None,
        user_prompt: request.user_prompt.clone(),
        formatted_prompt: None,
        model_id: request.model.clone(),
        user_api_key: request.user_api_key.clone(),
        is_public: false,
        public_token: None,
        model_version: None,
        tokenizer_version: None,
        vocab_hash: None,
        sampler_preset: None,
        sampler_algo: None,
        rng_seed: None,
        max_steps: request.max_tokens,
        active_mod,
        final_tokens: request.final_token_ids.clone(),
        final_text: request.final_text.clone(),
        sequence_confidence: None,
        eos_reason: None,
        request_tags: Value::Object(Default::default()),
        favorited_by: Vec::new(),
        tags: Vec::new(),
        events,
        mod_calls,
        mod_logs,
        actions,
        steps,
        step_logit_summaries: Vec::new(),
        inference_stats: None,
        discussion_count: 0,
    }
}

/// Convert event records to EventLog format.
fn convert_events(events: &[EventRecord], event_ids: &[i64]) -> Vec<EventLog> {
    events
        .iter()
        .enumerate()
        .map(|(idx, event)| {
            let id = event_ids.get(idx).copied().unwrap_or(idx as i64);
            EventLog {
                id,
                event_type: event.event_type.as_str().to_string(),
                step: event.step,
                sequence_order: event.sequence_order,
                created_at: event.created_at.unwrap_or_else(Utc::now),
                prompt_length: event.prompt_length,
                max_steps: event.max_steps,
                input_text: event.input_text.clone(),
                top_tokens: event.top_tokens.clone(),
                sampled_token: event.sampled_token,
                token_text: event.token_text.clone(),
                added_tokens: event.added_tokens.clone(),
                added_token_count: event.added_token_count,
                forced: event.forced,
            }
        })
        .collect()
}

/// Build legacy LogStep entries from Sampled events.
fn build_legacy_steps(events: &[EventRecord]) -> Vec<LogStep> {
    events
        .iter()
        .filter(|e| matches!(e.event_type, EventType::Sampled))
        .map(|event| LogStep {
            step_index: event.step,
            token: event.sampled_token,
            token_text: event.token_text.clone(),
            forced: event.forced.unwrap_or(false),
            forced_by: None,
            adjusted_logits: false,
            top_k: None,
            top_p: None,
            temperature: None,
            prob: None,
            logprob: None,
            entropy: None,
            flatness: None,
            surprisal: None,
            cum_nll: None,
            rng_counter: None,
            created_at: event.created_at.unwrap_or_else(Utc::now),
        })
        .collect()
}

/// Convert mod_call records to ModCallLog format.
fn convert_mod_calls(
    mod_calls: &[ModCallRecord],
    event_ids: &[i64],
    mod_call_ids: &[i64],
) -> Vec<ModCallLog> {
    mod_calls
        .iter()
        .enumerate()
        .map(|(idx, mc)| {
            let id = mod_call_ids.get(idx).copied().unwrap_or(idx as i64);
            let event_id = event_ids
                .get(mc.event_sequence_order as usize)
                .copied()
                .unwrap_or(mc.event_sequence_order as i64);

            ModCallLog {
                id,
                event_id,
                mod_name: mc.mod_name.clone(),
                event_type: mc.event_type.as_str().to_string(),
                step: mc.step,
                created_at: mc.created_at.unwrap_or_else(Utc::now),
                execution_time_ms: mc.execution_time_ms,
                exception_occurred: mc.exception_occurred,
                exception_message: mc.exception_message.clone(),
            }
        })
        .collect()
}

/// Convert mod_log records to ModLogEntry format.
fn convert_mod_logs(mod_logs: &[ModLogRecord], mod_call_ids: &[i64]) -> Vec<ModLogEntry> {
    mod_logs
        .iter()
        .enumerate()
        .map(|(idx, ml)| {
            let mod_call_id = mod_call_ids
                .get(ml.mod_call_sequence as usize)
                .copied()
                .unwrap_or(ml.mod_call_sequence as i64);

            ModLogEntry {
                id: idx as i64,
                mod_call_id,
                mod_name: ml.mod_name.clone(),
                log_message: ml.log_message.clone(),
                log_level: ml.log_level.as_str().to_string(),
                created_at: ml.created_at.unwrap_or_else(Utc::now),
            }
        })
        .collect()
}

/// Convert action records to ActionLog format.
fn convert_actions(actions: &[ActionRecord], mod_call_ids: &[i64]) -> Vec<ActionLog> {
    actions
        .iter()
        .enumerate()
        .map(|(idx, action)| {
            let mod_call_id = mod_call_ids
                .get(action.mod_call_sequence as usize)
                .copied()
                .unwrap_or(action.mod_call_sequence as i64);

            // Build payload by merging details with explicit fields
            let mut payload = match &action.details {
                Some(Value::Object(map)) => map.clone(),
                _ => serde_json::Map::new(),
            };

            // Add explicit fields to payload if not already present
            if let Some(ref tokens) = action.tokens {
                if !payload.contains_key("tokens") {
                    payload.insert(
                        "tokens".to_string(),
                        Value::Array(tokens.iter().map(|&n| Value::Number(n.into())).collect()),
                    );
                }
            }

            if let Some(ref preview) = action.tokens_preview {
                if !payload.contains_key("tokens_as_text") {
                    payload.insert(
                        "tokens_as_text".to_string(),
                        Value::Array(vec![Value::String(preview.clone())]),
                    );
                }
            }

            if let Some(count) = action.token_count {
                if !payload.contains_key("token_count") {
                    payload.insert("token_count".to_string(), Value::Number(count.into()));
                }
            }

            if let Some(steps) = action.backtrack_steps {
                if !payload.contains_key("backtrack_steps") {
                    payload.insert("backtrack_steps".to_string(), Value::Number(steps.into()));
                }
            }

            if let Some(ref new_prompt) = action.new_prompt {
                if !payload.contains_key("new_prompt") {
                    payload.insert("new_prompt".to_string(), Value::String(new_prompt.clone()));
                }
            }

            if let Some(new_length) = action.new_length {
                if !payload.contains_key("new_length") {
                    payload.insert("new_length".to_string(), Value::Number(new_length.into()));
                }
            }

            if let Some(adjusted_max_steps) = action.adjusted_max_steps {
                if !payload.contains_key("adjusted_max_steps") {
                    payload.insert(
                        "adjusted_max_steps".to_string(),
                        Value::Number(adjusted_max_steps.into()),
                    );
                }
            }

            if let Some(ref logits_shape) = action.logits_shape {
                if !payload.contains_key("logits_shape") {
                    payload.insert(
                        "logits_shape".to_string(),
                        Value::String(logits_shape.clone()),
                    );
                }
            }

            if let Some(temperature) = action.temperature {
                if !payload.contains_key("temperature") {
                    payload.insert(
                        "temperature".to_string(),
                        Value::Number(
                            serde_json::Number::from_f64(temperature).unwrap_or(0.into()),
                        ),
                    );
                }
            }

            if let Some(has_tool_calls) = action.has_tool_calls {
                if !payload.contains_key("has_tool_calls") {
                    payload.insert("has_tool_calls".to_string(), Value::Bool(has_tool_calls));
                }
            }

            if let Some(ref tool_calls) = action.tool_calls {
                if !payload.contains_key("tool_calls") {
                    payload.insert("tool_calls".to_string(), tool_calls.clone());
                }
            }

            if let Some(ref error_message) = action.error_message {
                if !payload.contains_key("error_message") {
                    payload.insert(
                        "error_message".to_string(),
                        Value::String(error_message.clone()),
                    );
                }
            }

            ActionLog {
                action_id: idx as i64,
                step_index: None,
                mod_id: Some(mod_call_id as i32),
                block_id: None,
                block_key: None,
                action_type: action.action_type.as_str().to_string(),
                event: None,
                payload: Value::Object(payload),
                created_at: action.created_at.unwrap_or_else(Utc::now),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::handlers::ingest::payload::{ActionType, EventType, LogLevel, RequestRecord};

    fn make_test_payload() -> FullIngestPayload {
        FullIngestPayload {
            request: RequestRecord {
                request_id: "test-req-123".to_string(),
                created_at: None,
                completed_at: None,
                model: Some("test-model".to_string()),
                user_api_key: None,
                max_tokens: Some(100),
                temperature: Some(0.7),
                mod_text: None,
                user_prompt: Some("Hello, world!".to_string()),
                user_prompt_token_ids: None,
                active_mod_name: Some("test-mod".to_string()),
                final_token_ids: Some(vec![1, 2, 3]),
                final_text: Some("Response text".to_string()),
                inference_stats: None,
            },
            events: vec![
                EventRecord {
                    event_type: EventType::Prefilled,
                    step: 0,
                    sequence_order: 0,
                    created_at: None,
                    details: None,
                    prompt_length: Some(10),
                    tokens_so_far_len: None,
                    max_steps: Some(100),
                    input_text: None,
                    top_tokens: None,
                    sampled_token: None,
                    token_text: None,
                    added_tokens: None,
                    added_token_count: None,
                    forced: None,
                },
                EventRecord {
                    event_type: EventType::Sampled,
                    step: 1,
                    sequence_order: 1,
                    created_at: None,
                    details: None,
                    prompt_length: None,
                    tokens_so_far_len: None,
                    max_steps: None,
                    input_text: None,
                    top_tokens: None,
                    sampled_token: Some(42),
                    token_text: Some("token".to_string()),
                    added_tokens: None,
                    added_token_count: None,
                    forced: Some(false),
                },
            ],
            mod_calls: vec![ModCallRecord {
                event_sequence_order: 1,
                mod_name: "test-mod".to_string(),
                event_type: EventType::Sampled,
                step: 1,
                created_at: None,
                execution_time_ms: Some(1.5),
                exception_occurred: false,
                exception_message: None,
                exception_traceback: None,
            }],
            mod_logs: vec![ModLogRecord {
                mod_call_sequence: 0,
                mod_name: "test-mod".to_string(),
                log_message: "Test log message".to_string(),
                log_level: LogLevel::Info,
                created_at: None,
            }],
            actions: vec![ActionRecord {
                mod_call_sequence: 0,
                action_type: ActionType::Noop,
                action_order: 0,
                created_at: None,
                details: None,
                new_prompt: None,
                new_length: None,
                adjusted_max_steps: None,
                token_count: None,
                tokens: None,
                tokens_preview: None,
                backtrack_steps: None,
                logits_shape: None,
                temperature: None,
                has_tool_calls: None,
                tool_calls: None,
                error_message: None,
            }],
        }
    }

    #[test]
    fn test_payload_to_response_basic() {
        let payload = make_test_payload();
        let event_ids = vec![100, 101];
        let mod_call_ids = vec![200];

        let response = payload_to_response(&payload, &event_ids, &mod_call_ids);

        assert_eq!(response.request_id, "test-req-123");
        assert_eq!(response.model_id, Some("test-model".to_string()));
        assert_eq!(response.user_prompt, Some("Hello, world!".to_string()));
        assert_eq!(response.final_text, Some("Response text".to_string()));
        assert_eq!(response.max_steps, Some(100));
    }

    #[test]
    fn test_active_mod_conversion() {
        let payload = make_test_payload();
        let response = payload_to_response(&payload, &[], &[]);

        assert!(response.active_mod.is_some());
        let active_mod = response.active_mod.unwrap();
        assert_eq!(active_mod.name, Some("test-mod".to_string()));
    }

    #[test]
    fn test_events_conversion() {
        let payload = make_test_payload();
        let event_ids = vec![100, 101];
        let response = payload_to_response(&payload, &event_ids, &[]);

        assert_eq!(response.events.len(), 2);
        assert_eq!(response.events[0].id, 100);
        assert_eq!(response.events[0].event_type, "Prefilled");
        assert_eq!(response.events[1].id, 101);
        assert_eq!(response.events[1].event_type, "Sampled");
        assert_eq!(response.events[1].sampled_token, Some(42));
    }

    #[test]
    fn test_legacy_steps_from_sampled() {
        let payload = make_test_payload();
        let response = payload_to_response(&payload, &[], &[]);

        // Only Sampled events become steps
        assert_eq!(response.steps.len(), 1);
        assert_eq!(response.steps[0].step_index, 1);
        assert_eq!(response.steps[0].token, Some(42));
        assert_eq!(response.steps[0].token_text, Some("token".to_string()));
    }

    #[test]
    fn test_mod_calls_conversion() {
        let payload = make_test_payload();
        let event_ids = vec![100, 101];
        let mod_call_ids = vec![200];
        let response = payload_to_response(&payload, &event_ids, &mod_call_ids);

        assert_eq!(response.mod_calls.len(), 1);
        assert_eq!(response.mod_calls[0].id, 200);
        assert_eq!(response.mod_calls[0].event_id, 101); // event_sequence_order = 1
        assert_eq!(response.mod_calls[0].mod_name, "test-mod");
    }

    #[test]
    fn test_mod_logs_conversion() {
        let payload = make_test_payload();
        let mod_call_ids = vec![200];
        let response = payload_to_response(&payload, &[], &mod_call_ids);

        assert_eq!(response.mod_logs.len(), 1);
        assert_eq!(response.mod_logs[0].mod_call_id, 200);
        assert_eq!(response.mod_logs[0].log_message, "Test log message");
        assert_eq!(response.mod_logs[0].log_level, "INFO");
    }

    #[test]
    fn test_actions_conversion() {
        let payload = make_test_payload();
        let mod_call_ids = vec![200];
        let response = payload_to_response(&payload, &[], &mod_call_ids);

        assert_eq!(response.actions.len(), 1);
        assert_eq!(response.actions[0].mod_id, Some(200));
        assert_eq!(response.actions[0].action_type, "Noop");
    }
}
