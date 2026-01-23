use chrono::{DateTime, Utc};
use serde_json::Value;
use sqlx::{Executor, Postgres, Row, Transaction};

use crate::utils::ApiError;

/// PostgreSQL has a limit of 65535 (u16::MAX) parameters per query.
/// We define batch sizes for each insert type based on their parameter count.
const EVENTS_BATCH_SIZE: usize = 4000; // 16 params per row
const MOD_CALLS_BATCH_SIZE: usize = 6000; // 10 params per row
const MOD_LOGS_BATCH_SIZE: usize = 10000; // 6 params per row
const ACTIONS_BATCH_SIZE: usize = 3500; // 18 params per row

use super::{
    Result,
    payload::{ActionRecord, EventRecord, ModCallRecord, ModLogRecord, RequestRecord},
};

/// Helper to extract a field from details JSON or use the top-level value
fn extract_i32_from_details(
    details: &Option<Value>,
    key: &str,
    top_level: Option<i32>,
) -> Option<i32> {
    if top_level.is_some() {
        return top_level;
    }
    details
        .as_ref()
        .and_then(|d| d.get(key))
        .and_then(|v| v.as_i64())
        .map(|v| v as i32)
}

fn extract_f64_from_details(
    details: &Option<Value>,
    key: &str,
    top_level: Option<f64>,
) -> Option<f64> {
    if top_level.is_some() {
        return top_level;
    }
    details
        .as_ref()
        .and_then(|d| d.get(key))
        .and_then(|v| v.as_f64())
}

fn extract_string_from_details(
    details: &Option<Value>,
    key: &str,
    top_level: Option<&str>,
) -> Option<String> {
    if top_level.is_some() {
        return top_level.map(String::from);
    }
    details
        .as_ref()
        .and_then(|d| d.get(key))
        .and_then(|v| v.as_str())
        .map(String::from)
}

fn extract_bool_from_details(
    details: &Option<Value>,
    key: &str,
    top_level: Option<bool>,
) -> Option<bool> {
    if top_level.is_some() {
        return top_level;
    }
    details
        .as_ref()
        .and_then(|d| d.get(key))
        .and_then(|v| v.as_bool())
}

fn extract_tokens_from_details(
    details: &Option<Value>,
    top_level: Option<&[i32]>,
) -> Option<Vec<i32>> {
    if top_level.is_some() {
        return top_level.map(|t| t.to_vec());
    }
    details
        .as_ref()
        .and_then(|d| d.get("tokens"))
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_i64().map(|n| n as i32))
                .collect()
        })
}

fn extract_tool_calls_from_details(
    details: &Option<Value>,
    top_level: &Option<Value>,
) -> Option<Value> {
    if top_level.is_some() {
        return top_level.clone();
    }
    details.as_ref().and_then(|d| d.get("tool_calls")).cloned()
}

/// Helper to extract a string array field from details JSON
fn extract_string_array_from_details(details: &Option<Value>, key: &str) -> Option<Vec<String>> {
    details
        .as_ref()
        .and_then(|d| d.get(key))
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
}

/// Persist or update request record
pub async fn persist_request(
    tx: &mut Transaction<'_, Postgres>,
    request: &RequestRecord,
) -> Result<()> {
    let created_at = request.created_at.unwrap_or_else(Utc::now);

    tx.execute(
        sqlx::query::<Postgres>(
            "INSERT INTO requests (
                request_id,
                created_at,
                completed_at,
                model,
                user_api_key,
                max_tokens,
                temperature,
                mod,
                user_prompt,
                user_prompt_token_ids,
                active_mod_name,
                final_token_ids,
                final_text,
                inference_stats
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            ON CONFLICT (request_id) DO UPDATE SET
                completed_at = EXCLUDED.completed_at,
                model = EXCLUDED.model,
                user_api_key = EXCLUDED.user_api_key,
                max_tokens = EXCLUDED.max_tokens,
                temperature = EXCLUDED.temperature,
                mod = EXCLUDED.mod,
                user_prompt = EXCLUDED.user_prompt,
                user_prompt_token_ids = EXCLUDED.user_prompt_token_ids,
                active_mod_name = EXCLUDED.active_mod_name,
                final_token_ids = EXCLUDED.final_token_ids,
                final_text = EXCLUDED.final_text,
                inference_stats = EXCLUDED.inference_stats",
        )
        .bind(&request.request_id)
        .bind(created_at)
        .bind(request.completed_at)
        .bind(request.model.as_deref())
        .bind(request.user_api_key.as_deref())
        .bind(request.max_tokens)
        .bind(request.temperature)
        .bind(request.mod_text.as_deref())
        .bind(request.user_prompt.as_deref())
        .bind(request.user_prompt_token_ids.as_deref())
        .bind(request.active_mod_name.as_deref())
        .bind(request.final_token_ids.as_deref())
        .bind(request.final_text.as_deref())
        .bind(&request.inference_stats),
    )
    .await
    .map_err(ApiError::from)?;

    Ok(())
}

/// Replace all events for a request using batched multi-row INSERT.
///
/// Events are inserted in batches to avoid exceeding PostgreSQL's parameter limit (65535).
pub async fn replace_events(
    tx: &mut Transaction<'_, Postgres>,
    request: &RequestRecord,
    events: &[EventRecord],
) -> Result<Vec<i64>> {
    // Delete existing events
    tx.execute(
        sqlx::query::<Postgres>("DELETE FROM events WHERE request_id = $1")
            .bind(&request.request_id),
    )
    .await
    .map_err(ApiError::from)?;

    if events.is_empty() {
        return Ok(Vec::new());
    }

    let mut all_event_ids: Vec<i64> = Vec::with_capacity(events.len());

    // Process events in batches to avoid exceeding PostgreSQL's parameter limit
    for batch in events.chunks(EVENTS_BATCH_SIZE) {
        let mut placeholders = Vec::new();
        let mut param_num = 1;

        for _ in batch {
            placeholders.push(format!(
                "(${}, ${}::event_type, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${})",
                param_num, param_num + 1, param_num + 2, param_num + 3, param_num + 4, param_num + 5,
                param_num + 6, param_num + 7, param_num + 8, param_num + 9, param_num + 10, param_num + 11,
                param_num + 12, param_num + 13, param_num + 14, param_num + 15
            ));
            param_num += 16;
        }

        let sql = format!(
            "INSERT INTO events (
                request_id,
                event_type,
                step,
                sequence_order,
                created_at,
                details,
                prompt_length,
                tokens_so_far_len,
                max_steps,
                input_text,
                top_tokens,
                sampled_token,
                token_text,
                added_tokens,
                added_token_count,
                forced
            ) VALUES {} RETURNING id",
            placeholders.join(", ")
        );

        let mut query = sqlx::query::<Postgres>(&sql);

        for event in batch {
            let created_at = event.created_at.unwrap_or_else(Utc::now);
            query = query
                .bind(&request.request_id)
                .bind(event.event_type.as_str())
                .bind(event.step)
                .bind(event.sequence_order)
                .bind(created_at)
                .bind(&event.details)
                .bind(event.prompt_length)
                .bind(event.tokens_so_far_len)
                .bind(event.max_steps)
                .bind(event.input_text.as_deref())
                .bind(&event.top_tokens)
                .bind(event.sampled_token)
                .bind(event.token_text.as_deref())
                .bind(event.added_tokens.as_deref())
                .bind(event.added_token_count)
                .bind(event.forced);
        }

        let rows = query.fetch_all(&mut **tx).await.map_err(ApiError::from)?;

        let batch_ids: Vec<i64> = rows
            .iter()
            .map(|row| row.try_get::<i64, _>(0).map_err(ApiError::from))
            .collect::<Result<Vec<_>>>()?;

        all_event_ids.extend(batch_ids);
    }

    Ok(all_event_ids)
}

/// Replace all mod calls for a request using batched multi-row INSERT.
pub async fn replace_mod_calls(
    tx: &mut Transaction<'_, Postgres>,
    request: &RequestRecord,
    mod_calls: &[ModCallRecord],
    event_ids: &[i64],
) -> Result<Vec<i64>> {
    // Delete existing mod calls (cascades to mod_logs and actions)
    tx.execute(
        sqlx::query::<Postgres>("DELETE FROM mod_calls WHERE request_id = $1")
            .bind(&request.request_id),
    )
    .await
    .map_err(ApiError::from)?;

    if mod_calls.is_empty() {
        return Ok(Vec::new());
    }

    let mut all_mod_call_ids: Vec<i64> = Vec::with_capacity(mod_calls.len());

    // Process mod_calls in batches to avoid exceeding PostgreSQL's parameter limit
    for batch in mod_calls.chunks(MOD_CALLS_BATCH_SIZE) {
        let mut placeholders = Vec::new();
        let mut param_num = 1;

        for _ in batch {
            placeholders.push(format!(
                "(${}, ${}, ${}, ${}::event_type, ${}, ${}, ${}, ${}, ${}, ${})",
                param_num,
                param_num + 1,
                param_num + 2,
                param_num + 3,
                param_num + 4,
                param_num + 5,
                param_num + 6,
                param_num + 7,
                param_num + 8,
                param_num + 9
            ));
            param_num += 10;
        }

        let sql = format!(
            "INSERT INTO mod_calls (
                event_id,
                request_id,
                mod_name,
                event_type,
                step,
                created_at,
                execution_time_ms,
                exception_occurred,
                exception_message,
                exception_traceback
            ) VALUES {} RETURNING id",
            placeholders.join(", ")
        );

        let mut query = sqlx::query::<Postgres>(&sql);

        for mod_call in batch {
            let created_at = mod_call.created_at.unwrap_or_else(Utc::now);

            // Find the event_id for this mod_call based on sequence_order
            let event_id = event_ids
                .get(mod_call.event_sequence_order as usize)
                .ok_or_else(|| {
                    ApiError::BadRequest(format!(
                        "Invalid event_sequence_order: {}",
                        mod_call.event_sequence_order
                    ))
                })?;

            query = query
                .bind(event_id)
                .bind(&request.request_id)
                .bind(&mod_call.mod_name)
                .bind(mod_call.event_type.as_str())
                .bind(mod_call.step)
                .bind(created_at)
                .bind(mod_call.execution_time_ms)
                .bind(mod_call.exception_occurred)
                .bind(mod_call.exception_message.as_deref())
                .bind(mod_call.exception_traceback.as_deref());
        }

        let rows = query.fetch_all(&mut **tx).await.map_err(ApiError::from)?;

        let batch_ids: Vec<i64> = rows
            .iter()
            .map(|row| row.try_get::<i64, _>(0).map_err(ApiError::from))
            .collect::<Result<Vec<_>>>()?;

        all_mod_call_ids.extend(batch_ids);
    }

    Ok(all_mod_call_ids)
}

/// Replace all mod logs for a request using batched multi-row INSERT.
pub async fn replace_mod_logs(
    tx: &mut Transaction<'_, Postgres>,
    request: &RequestRecord,
    mod_logs: &[ModLogRecord],
    mod_call_ids: &[i64],
) -> Result<()> {
    // Logs are already deleted via cascade from mod_calls

    if mod_logs.is_empty() {
        return Ok(());
    }

    // Process mod_logs in batches to avoid exceeding PostgreSQL's parameter limit
    for batch in mod_logs.chunks(MOD_LOGS_BATCH_SIZE) {
        let mut placeholders = Vec::new();
        let mut param_num = 1;

        for _ in batch {
            placeholders.push(format!(
                "(${}, ${}, ${}, ${}, ${}::log_level, ${})",
                param_num,
                param_num + 1,
                param_num + 2,
                param_num + 3,
                param_num + 4,
                param_num + 5
            ));
            param_num += 6;
        }

        let sql = format!(
            "INSERT INTO mod_logs (
                mod_call_id,
                request_id,
                mod_name,
                log_message,
                log_level,
                created_at
            ) VALUES {}",
            placeholders.join(", ")
        );

        let mut query = sqlx::query::<Postgres>(&sql);

        for log in batch {
            let created_at = log.created_at.unwrap_or_else(Utc::now);

            // Find the mod_call_id for this log
            let mod_call_id = mod_call_ids
                .get(log.mod_call_sequence as usize)
                .ok_or_else(|| {
                    ApiError::BadRequest(format!(
                        "Invalid mod_call_sequence: {}",
                        log.mod_call_sequence
                    ))
                })?;

            query = query
                .bind(mod_call_id)
                .bind(&request.request_id)
                .bind(&log.mod_name)
                .bind(&log.log_message)
                .bind(log.log_level.as_str())
                .bind(created_at);
        }

        query.execute(&mut **tx).await.map_err(ApiError::from)?;
    }

    Ok(())
}

/// Extracted action fields for database insertion
struct ExtractedActionFields {
    mod_call_id: i64,
    action_type_str: &'static str,
    action_order: i32,
    created_at: DateTime<Utc>,
    new_prompt: Option<String>,
    new_length: Option<i32>,
    adjusted_max_steps: Option<i32>,
    token_count: Option<i32>,
    tokens: Option<Vec<i32>>,
    tokens_as_text: Option<Vec<String>>,
    backtrack_steps: Option<i32>,
    logits_shape: Option<String>,
    temperature: Option<f64>,
    has_tool_calls: Option<bool>,
    tool_calls: Option<Value>,
    error_message: Option<String>,
}

/// Replace all actions for a request using batched multi-row INSERT.
pub async fn replace_actions(
    tx: &mut Transaction<'_, Postgres>,
    request: &RequestRecord,
    actions: &[ActionRecord],
    mod_call_ids: &[i64],
) -> Result<()> {
    // Actions are already deleted via cascade from mod_calls

    if actions.is_empty() {
        return Ok(());
    }

    // Pre-extract all fields to avoid lifetime issues
    let mut extracted_fields: Vec<ExtractedActionFields> = Vec::with_capacity(actions.len());

    for action in actions {
        let mod_call_id = *mod_call_ids
            .get(action.mod_call_sequence as usize)
            .ok_or_else(|| {
                ApiError::BadRequest(format!(
                    "Invalid mod_call_sequence: {}",
                    action.mod_call_sequence
                ))
            })?;

        let created_at = action.created_at.unwrap_or_else(Utc::now);

        // Extract fields from details if not provided at top level
        let new_prompt = extract_string_from_details(
            &action.details,
            "new_prompt",
            action.new_prompt.as_deref(),
        );
        let new_length = extract_i32_from_details(&action.details, "new_length", action.new_length);
        let adjusted_max_steps = extract_i32_from_details(
            &action.details,
            "adjusted_max_steps",
            action.adjusted_max_steps,
        );
        let token_count =
            extract_i32_from_details(&action.details, "token_count", action.token_count);
        let tokens = extract_tokens_from_details(&action.details, action.tokens.as_deref());
        // Extract tokens_as_text as array of strings (one per token)
        // Fall back to wrapping legacy single string in an array for backwards compatibility
        let tokens_as_text = extract_string_array_from_details(&action.details, "tokens_as_text")
            .or_else(|| {
                // Backwards compatibility: wrap single string in array
                extract_string_from_details(
                    &action.details,
                    "tokens_as_text",
                    action.tokens_preview.as_deref(),
                )
                .or_else(|| extract_string_from_details(&action.details, "tokens_preview", None))
                .map(|s| vec![s])
            });
        let backtrack_steps =
            extract_i32_from_details(&action.details, "backtrack_steps", action.backtrack_steps);
        let logits_shape = extract_string_from_details(
            &action.details,
            "logits_shape",
            action.logits_shape.as_deref(),
        );
        let temperature =
            extract_f64_from_details(&action.details, "temperature", action.temperature);
        let has_tool_calls =
            extract_bool_from_details(&action.details, "has_tool_calls", action.has_tool_calls);
        let tool_calls = extract_tool_calls_from_details(&action.details, &action.tool_calls);
        let error_message = extract_string_from_details(
            &action.details,
            "error_message",
            action.error_message.as_deref(),
        );

        extracted_fields.push(ExtractedActionFields {
            mod_call_id,
            action_type_str: action.action_type.as_str(),
            action_order: action.action_order,
            created_at,
            new_prompt,
            new_length,
            adjusted_max_steps,
            token_count,
            tokens,
            tokens_as_text,
            backtrack_steps,
            logits_shape,
            temperature,
            has_tool_calls,
            tool_calls,
            error_message,
        });
    }

    // Process actions in batches to avoid exceeding PostgreSQL's parameter limit
    let action_field_pairs: Vec<_> = actions.iter().zip(extracted_fields.iter()).collect();

    for batch in action_field_pairs.chunks(ACTIONS_BATCH_SIZE) {
        let mut placeholders = Vec::new();
        let mut param_num = 1;

        for _ in batch {
            placeholders.push(format!(
                "(${}, ${}, ${}::action_type, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${}, ${})",
                param_num, param_num + 1, param_num + 2, param_num + 3, param_num + 4, param_num + 5,
                param_num + 6, param_num + 7, param_num + 8, param_num + 9, param_num + 10, param_num + 11,
                param_num + 12, param_num + 13, param_num + 14, param_num + 15, param_num + 16, param_num + 17
            ));
            param_num += 18;
        }

        let sql = format!(
            "INSERT INTO actions (
                mod_call_id,
                request_id,
                action_type,
                action_order,
                created_at,
                details,
                new_prompt,
                new_length,
                adjusted_max_steps,
                token_count,
                tokens,
                tokens_as_text,
                backtrack_steps,
                logits_shape,
                temperature,
                has_tool_calls,
                tool_calls,
                error_message
            ) VALUES {}",
            placeholders.join(", ")
        );

        let mut query = sqlx::query::<Postgres>(&sql);

        for (action, fields) in batch {
            query = query
                .bind(fields.mod_call_id)
                .bind(&request.request_id)
                .bind(fields.action_type_str)
                .bind(fields.action_order)
                .bind(fields.created_at)
                .bind(&action.details)
                .bind(fields.new_prompt.as_deref())
                .bind(fields.new_length)
                .bind(fields.adjusted_max_steps)
                .bind(fields.token_count)
                .bind(fields.tokens.as_deref())
                .bind(fields.tokens_as_text.as_deref())
                .bind(fields.backtrack_steps)
                .bind(fields.logits_shape.as_deref())
                .bind(fields.temperature)
                .bind(fields.has_tool_calls)
                .bind(&fields.tool_calls)
                .bind(fields.error_message.as_deref());
        }

        query.execute(&mut **tx).await.map_err(ApiError::from)?;
    }

    Ok(())
}
