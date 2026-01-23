use std::collections::HashMap;
use std::result::Result as StdResult;

use axum::{
    Json,
    extract::{
        Path, Query, State,
        ws::{Message, WebSocket, WebSocketUpgrade},
    },
    http::HeaderMap,
    response::IntoResponse,
};
use chrono::{DateTime, Utc};
use futures::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgPool, Row};
use tokio_stream::wrappers::BroadcastStream;

use tracing::info;

use crate::utils::auth::{AuthenticatedKey, extract_api_key_from_headers, validate_api_key};
use crate::utils::{ApiError, AppState, LogCache};

pub type Result<T> = StdResult<T, ApiError>;

const DEFAULT_LIMIT: i64 = 50;
const MAX_LIMIT: i64 = 100;

#[derive(Debug, Default, Deserialize)]
pub struct ListLogsParams {
    pub limit: Option<i64>,
    pub offset: Option<i64>,
    /// Filter by collection ID
    pub collection_id: Option<i64>,
    /// Filter by API key
    pub api_key: Option<String>,
}

/// Query parameters for WebSocket stream authentication
#[derive(Debug, Default, Deserialize)]
pub struct StreamLogsParams {
    /// API key for authentication (required)
    pub api_key: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ListLogsResponse {
    pub data: Vec<LogSummary>,
    pub limit: i64,
    pub offset: i64,
    pub returned: usize,
}

#[derive(Debug, Serialize)]
pub struct LogSummary {
    pub request_id: String,
    pub created_ts: DateTime<Utc>,
    pub finished_ts: Option<DateTime<Utc>>,
    pub model_id: Option<String>,
    pub user_api_key: Option<String>,
    pub final_text: Option<String>,
    pub total_steps: i64,
    pub favorited_by: Vec<String>,
    pub discussion_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct LogResponse {
    pub request_id: String,
    pub created_ts: DateTime<Utc>,
    pub finished_ts: Option<DateTime<Utc>>,
    pub system_prompt: Option<String>,
    pub user_prompt: Option<String>,
    pub formatted_prompt: Option<String>,
    pub model_id: Option<String>,
    /// The API key that made this request (for authorization checks)
    pub user_api_key: Option<String>,
    /// Whether this request is publicly accessible
    pub is_public: bool,
    /// Public token for shareable link (if public)
    pub public_token: Option<String>,
    pub model_version: Option<String>,
    pub tokenizer_version: Option<String>,
    pub vocab_hash: Option<String>,
    pub sampler_preset: Option<String>,
    pub sampler_algo: Option<String>,
    pub rng_seed: Option<i64>,
    pub max_steps: Option<i32>,
    pub active_mod: Option<ActiveMod>,
    pub final_tokens: Option<Vec<i32>>,
    pub final_text: Option<String>,
    pub sequence_confidence: Option<f64>,
    pub eos_reason: Option<String>,
    pub request_tags: Value,
    /// List of user names who have favorited this request.
    pub favorited_by: Vec<String>,
    /// List of tags for categorizing this request.
    pub tags: Vec<String>,
    // New structured trace data
    pub events: Vec<EventLog>,
    pub mod_calls: Vec<ModCallLog>,
    pub mod_logs: Vec<ModLogEntry>,
    pub actions: Vec<ActionLog>,
    // Legacy fields for backwards compatibility
    pub steps: Vec<LogStep>,
    pub step_logit_summaries: Vec<StepLogitSummaryLog>,
    pub inference_stats: Option<RequestInferenceStatsLog>,
    /// Number of discussions for this request
    pub discussion_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct EventLog {
    pub id: i64,
    pub event_type: String,
    pub step: i32,
    pub sequence_order: i32,
    pub created_at: DateTime<Utc>,
    // Prefilled fields
    pub prompt_length: Option<i32>,
    pub max_steps: Option<i32>,
    // ForwardPass fields
    pub input_text: Option<String>,
    pub top_tokens: Option<Value>,
    // Sampled fields
    pub sampled_token: Option<i32>,
    pub token_text: Option<String>,
    // Added fields
    pub added_tokens: Option<Vec<i32>>,
    pub added_token_count: Option<i32>,
    pub forced: Option<bool>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModCallLog {
    pub id: i64,
    pub event_id: i64,
    pub mod_name: String,
    pub event_type: String,
    pub step: i32,
    pub created_at: DateTime<Utc>,
    pub execution_time_ms: Option<f64>,
    pub exception_occurred: bool,
    pub exception_message: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ModLogEntry {
    pub id: i64,
    pub mod_call_id: i64,
    pub mod_name: String,
    pub log_message: String,
    pub log_level: String,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ActiveMod {
    pub id: i32,
    pub name: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct LogStep {
    pub step_index: i32,
    pub token: Option<i32>,
    pub token_text: Option<String>,
    pub forced: bool,
    pub forced_by: Option<String>,
    pub adjusted_logits: bool,
    pub top_k: Option<i32>,
    pub top_p: Option<f64>,
    pub temperature: Option<f64>,
    pub prob: Option<f64>,
    pub logprob: Option<f64>,
    pub entropy: Option<f64>,
    pub flatness: Option<f64>,
    pub surprisal: Option<f64>,
    pub cum_nll: Option<f64>,
    pub rng_counter: Option<i64>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ActionLog {
    pub action_id: i64,
    pub step_index: Option<i32>,
    pub mod_id: Option<i32>,
    pub block_id: Option<i64>,
    pub block_key: Option<String>,
    pub action_type: String,
    pub event: Option<String>,
    pub payload: Value,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct StepLogitSummaryLog {
    pub id: i64,
    pub step_index: i32,
    pub phase: Option<String>,
    pub topk: Value,
    pub top_p_cutoff: Option<f64>,
    pub top_p_count: Option<i32>,
    pub note: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize)]
pub struct RequestInferenceStatsLog {
    pub prompt_tokens: Option<i32>,
    pub generated_tokens: Option<i32>,
    pub total_tokens: Option<i32>,
    pub wall_time_ms: Option<f64>,
    pub avg_tokens_per_sec: Option<f64>,
    pub max_tokens_per_sec: Option<f64>,
    pub queue_latency_ms: Option<f64>,
    pub scheduler_latency_ms: Option<f64>,
    pub prefill_latency_ms: Option<f64>,
    pub decode_latency_ms: Option<f64>,
    pub postprocess_latency_ms: Option<f64>,
    pub estimated_cost_usd: Option<f64>,
    pub compute_node: Option<String>,
    pub device_type: Option<String>,
    pub captured_at: DateTime<Utc>,
}

/// Summary of requests grouped by API key
#[derive(Debug, Serialize)]
pub struct ApiKeySummary {
    pub api_key: String,
    pub request_count: i64,
    pub latest_request_at: DateTime<Utc>,
}

/// Response for listing unique API keys
#[derive(Debug, Serialize)]
pub struct ListApiKeysResponse {
    pub api_keys: Vec<ApiKeySummary>,
    pub total: i64,
}

/// Return unique API keys with request counts for pseudo-collection filtering.
///
/// GET /logs/api-keys
///
/// - No API key provided: returns 401 Unauthorized
/// - Admin API key: returns all API keys
/// - User API key: returns only their allowed API key
pub async fn list_api_keys(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ListApiKeysResponse>> {
    // Require authentication
    let api_key = extract_api_key_from_headers(&headers)
        .ok_or_else(|| ApiError::unauthorized("API key required"))?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))?;

    // Determine if we should filter by a specific API key
    // - Admin auth: show all (None)
    // - User auth: filter to their allowed_api_key
    let filter_api_key: Option<String> = if auth.is_admin {
        None // Admin sees all
    } else {
        auth.allowed_api_key.clone() // Non-admin sees only their key
    };

    let rows = if let Some(ref allowed_key) = filter_api_key {
        // Filter to specific API key for non-admin users
        sqlx::query(
            r#"
            SELECT
                user_api_key,
                COUNT(*) as request_count,
                MAX(created_at) as latest_request_at
            FROM requests
            WHERE user_api_key = $1
            GROUP BY user_api_key
            ORDER BY latest_request_at DESC
            LIMIT 100
            "#,
        )
        .bind(allowed_key)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    } else {
        // Admin sees all API keys
        sqlx::query(
            r#"
            SELECT
                user_api_key,
                COUNT(*) as request_count,
                MAX(created_at) as latest_request_at
            FROM requests
            WHERE user_api_key IS NOT NULL AND user_api_key != ''
            GROUP BY user_api_key
            ORDER BY latest_request_at DESC
            LIMIT 100
            "#,
        )
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    };

    let api_keys: Vec<ApiKeySummary> = rows
        .into_iter()
        .filter_map(|row| {
            let api_key: Option<String> = row.try_get("user_api_key").ok()?;
            let api_key = api_key?;
            let request_count: i64 = row.try_get("request_count").ok()?;
            let latest_request_at: DateTime<Utc> = row.try_get("latest_request_at").ok()?;
            Some(ApiKeySummary {
                api_key,
                request_count,
                latest_request_at,
            })
        })
        .collect();

    let total = api_keys.len() as i64;

    Ok(Json(ListApiKeysResponse { api_keys, total }))
}

/// WebSocket endpoint for real-time log updates.
///
/// GET /logs/stream?api_key=<key> (WebSocket upgrade)
///
/// Authentication is required via the `api_key` query parameter.
/// - Admin users receive all log events
/// - Non-admin users only receive events for logs they own (matching their allowed_api_key)
///
/// Clients receive messages when new logs are ingested. Each message is a JSON object
/// with a `type` field ("new_log", "lagged", or "error") and corresponding data.
///
/// This endpoint uses a broadcast channel that does not hold any locks or block
/// other requests. Each client gets its own receiver from the broadcast channel.
pub async fn stream_logs(
    State(state): State<AppState>,
    Query(params): Query<StreamLogsParams>,
    ws: WebSocketUpgrade,
) -> std::result::Result<impl IntoResponse, ApiError> {
    // Require API key authentication
    let api_key = params
        .api_key
        .ok_or_else(|| ApiError::unauthorized("API key required. Pass api_key query parameter."))?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))?;

    info!(
        "WebSocket connection established for user: {} (admin: {})",
        auth.name, auth.is_admin
    );

    // Extract the filter criteria for this user
    let is_admin = auth.is_admin;
    let allowed_api_key = auth.allowed_api_key.clone();

    Ok(ws.on_upgrade(move |socket| handle_log_websocket(socket, state, is_admin, allowed_api_key)))
}

/// Handle an individual WebSocket connection for log streaming
async fn handle_log_websocket(
    socket: WebSocket,
    state: AppState,
    is_admin: bool,
    allowed_api_key: Option<String>,
) {
    info!(
        "handle log websocket (admin: {}, allowed_api_key: {:?})",
        is_admin, allowed_api_key
    );
    let (mut sender, mut receiver) = socket.split();

    // Subscribe to log events
    let rx = state.subscribe_log_events();
    let mut broadcast_stream = BroadcastStream::new(rx);

    // Spawn a task to handle incoming messages (for ping/pong and close)
    let mut recv_task = tokio::spawn(async move {
        while let Some(msg) = receiver.next().await {
            match msg {
                Ok(Message::Close(_)) => break,
                Ok(Message::Ping(data)) => {
                    // Pong is handled automatically by axum
                    let _ = data;
                }
                Err(_) => break,
                _ => {}
            }
        }
    });

    // Send log events to the client (filtered by user permissions)
    let mut send_task = tokio::spawn(async move {
        while let Some(result) = broadcast_stream.next().await {
            let message = match result {
                Ok(event) => {
                    // Filter events based on user permissions
                    // Admins see everything, non-admins only see their own logs
                    let can_see = if is_admin {
                        true
                    } else {
                        match (&allowed_api_key, &event.user_api_key) {
                            (Some(allowed), Some(event_key)) => allowed == event_key,
                            // If user has no allowed_api_key restriction, they can't see any logs
                            // If the event has no user_api_key, it's not visible to non-admins
                            _ => false,
                        }
                    };

                    if !can_see {
                        // Skip events the user is not allowed to see
                        continue;
                    }

                    // Hide user_api_key from non-admins in the response
                    let event_data = if is_admin {
                        serde_json::json!(event)
                    } else {
                        serde_json::json!({
                            "request_id": event.request_id,
                            "created_ts": event.created_ts,
                            "finished_ts": event.finished_ts,
                            "model_id": event.model_id,
                            "user_api_key": null,
                            "final_text": event.final_text,
                            "total_steps": event.total_steps,
                            "favorited_by": event.favorited_by,
                            "discussion_count": event.discussion_count,
                        })
                    };

                    let json = serde_json::json!({
                        "type": "new_log",
                        "data": event_data
                    });
                    Message::Text(json.to_string().into())
                }
                Err(tokio_stream::wrappers::errors::BroadcastStreamRecvError::Lagged(n)) => {
                    let json = serde_json::json!({
                        "type": "lagged",
                        "missed": n
                    });
                    Message::Text(json.to_string().into())
                }
            };

            if sender.send(message).await.is_err() {
                break;
            }
        }
    });

    // Wait for either task to complete, then abort the other
    tokio::select! {
        _ = &mut recv_task => {
            send_task.abort();
        }
        _ = &mut send_task => {
            recv_task.abort();
        }
    }

    info!("WebSocket connection closed");
}

/// Return paginated request summaries ordered by recency.
///
/// Supports optional filters:
/// - `collection_id`: Filter to requests in a specific collection
/// - `api_key`: Filter to requests from a specific API key
///
/// Authentication behavior:
/// - No API key provided: returns 401 Unauthorized
/// - Admin API key: shows all data (can use query params to filter)
/// - User API key: automatically filtered to only show that user's data
pub async fn list_logs(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(params): Query<ListLogsParams>,
) -> Result<Json<ListLogsResponse>> {
    let limit = params.limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let offset = params.offset.unwrap_or(0).max(0);

    // Require authentication
    let api_key = extract_api_key_from_headers(&headers)
        .ok_or_else(|| ApiError::unauthorized("API key required"))?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))?;

    // Determine the effective API key filter
    // - Admin auth: use query param filter or show all
    // - User auth: force filter to their allowed_api_key
    let effective_api_key_filter: Option<String> = if auth.is_admin {
        // Admin can filter by any api_key or see all
        params.api_key.clone()
    } else {
        // Non-admin must filter by their allowed_api_key
        auth.allowed_api_key.clone()
    };

    // Build query based on filters
    let rows = if let Some(collection_id) = params.collection_id {
        // Filter by collection - join with collection_requests
        sqlx::query(
            r#"
            SELECT
                r.request_id,
                r.created_at,
                r.completed_at,
                r.model,
                r.user_api_key,
                r.final_text,
                r.favorited_by,
                (
                    SELECT COUNT(DISTINCT step)
                    FROM events
                    WHERE events.request_id = r.request_id
                ) AS total_steps,
                (
                    SELECT COUNT(*)
                    FROM discussions
                    WHERE discussions.request_id = r.request_id
                ) AS discussion_count
            FROM requests r
            INNER JOIN collection_requests cr ON r.request_id = cr.request_id
            WHERE cr.collection_id = $3
            ORDER BY cr.added_at DESC
            LIMIT $1 OFFSET $2
            "#,
        )
        .bind(limit)
        .bind(offset)
        .bind(collection_id)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    } else if let Some(ref api_key) = effective_api_key_filter {
        // Filter by API key (either from query param for admins or forced for non-admins)
        sqlx::query(
            r#"
            SELECT
                request_id,
                created_at,
                completed_at,
                model,
                user_api_key,
                final_text,
                favorited_by,
                (
                    SELECT COUNT(DISTINCT step)
                    FROM events
                    WHERE events.request_id = requests.request_id
                ) AS total_steps,
                (
                    SELECT COUNT(*)
                    FROM discussions
                    WHERE discussions.request_id = requests.request_id
                ) AS discussion_count
            FROM requests
            WHERE user_api_key = $3
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            "#,
        )
        .bind(limit)
        .bind(offset)
        .bind(api_key)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    } else {
        // No filter - return all requests
        sqlx::query(
            r#"
            SELECT
                request_id,
                created_at,
                completed_at,
                model,
                user_api_key,
                final_text,
                favorited_by,
                (
                    SELECT COUNT(DISTINCT step)
                    FROM events
                    WHERE events.request_id = requests.request_id
                ) AS total_steps,
                (
                    SELECT COUNT(*)
                    FROM discussions
                    WHERE discussions.request_id = requests.request_id
                ) AS discussion_count
            FROM requests
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            "#,
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    };

    // Only admins can see user_api_key
    let is_admin = auth.is_admin;

    let data: Vec<LogSummary> = rows
        .into_iter()
        .map(|row| {
            let request_id: String = row.try_get("request_id")?;
            let created_ts: DateTime<Utc> = row.try_get("created_at")?;
            let finished_ts: Option<DateTime<Utc>> = row.try_get("completed_at")?;
            let model_id: Option<String> = row.try_get("model")?;
            let user_api_key: Option<String> = if is_admin {
                row.try_get("user_api_key")?
            } else {
                None
            };
            let final_text: Option<String> = row.try_get("final_text")?;
            let favorited_by: Vec<String> = row.try_get("favorited_by")?;
            let total_steps: i64 = row.try_get("total_steps")?;
            let discussion_count: i64 = row.try_get("discussion_count")?;

            Ok(LogSummary {
                request_id,
                created_ts,
                finished_ts,
                model_id,
                user_api_key,
                final_text,
                total_steps,
                favorited_by,
                discussion_count,
            })
        })
        .collect::<std::result::Result<Vec<_>, sqlx::Error>>()
        .map_err(ApiError::from)?;

    let returned = data.len();

    Ok(Json(ListLogsResponse {
        data,
        limit,
        offset,
        returned,
    }))
}

/// Fetch a fully hydrated log record from the database.
///
/// This is the core logic extracted for reuse in cache warming and the get_log handler.
pub async fn fetch_log_response(pool: &PgPool, request_id: &str) -> Result<LogResponse> {
    let record_row = sqlx::query(
        r#"
        SELECT
            r.request_id,
            r.created_at,
            r.completed_at,
            r.model,
            r.user_api_key,
            r.is_public,
            r.public_token,
            r.max_tokens,
            r.temperature,
            r.mod,
            r.user_prompt,
            r.user_prompt_token_ids,
            r.active_mod_name,
            r.final_token_ids,
            r.final_text,
            r.inference_stats,
            r.favorited_by,
            r.tags
        FROM requests r
        WHERE r.request_id = $1
        "#,
    )
    .bind(request_id)
    .fetch_optional(pool)
    .await
    .map_err(ApiError::from)?
    .ok_or_else(|| ApiError::NotFound("requested log not found".into()))?;

    let created_ts: DateTime<Utc> = record_row.try_get("created_at")?;
    let finished_ts: Option<DateTime<Utc>> = record_row.try_get("completed_at")?;
    let model_id: Option<String> = record_row.try_get("model")?;
    let user_api_key: Option<String> = record_row.try_get("user_api_key")?;
    let is_public: bool = record_row.try_get("is_public").unwrap_or(false);
    let public_token: Option<String> = record_row.try_get("public_token").ok().flatten();
    let max_tokens: Option<i32> = record_row.try_get("max_tokens")?;
    let _temperature: Option<f64> = record_row.try_get("temperature")?;
    let _mod_text: Option<String> = record_row.try_get("mod")?;
    let user_prompt: Option<String> = record_row.try_get("user_prompt")?;
    let _user_prompt_token_ids: Option<Vec<i32>> = record_row.try_get("user_prompt_token_ids")?;
    let active_mod_name: Option<String> = record_row.try_get("active_mod_name")?;
    let final_tokens: Option<Vec<i32>> = record_row.try_get("final_token_ids")?;
    let final_text: Option<String> = record_row.try_get("final_text")?;
    let _inference_stats: Option<Value> = record_row.try_get("inference_stats")?;
    let favorited_by: Vec<String> = record_row.try_get("favorited_by").unwrap_or_default();
    let tags: Vec<String> = record_row.try_get("tags").unwrap_or_default();

    let active_mod = active_mod_name.map(|name| ActiveMod {
        id: 0, // No longer have mod IDs in new schema
        name: Some(name),
    });

    // Fetch events
    let event_rows = sqlx::query(
        r#"
        SELECT
            id,
            event_type::text AS event_type,
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
        FROM events
        WHERE request_id = $1
        ORDER BY sequence_order ASC
        "#,
    )
    .bind(request_id)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    // Build legacy steps from Sampled events for backwards compatibility
    let steps = event_rows
        .iter()
        .filter_map(|row| {
            let event_type: String = row.try_get("event_type").ok()?;
            // Only create steps from Sampled events
            if event_type != "Sampled" {
                return None;
            }
            let step: i32 = row.try_get("step").ok()?;
            let created_at: DateTime<Utc> = row.try_get("created_at").ok()?;
            let sampled_token: Option<i32> = row.try_get("sampled_token").ok()?;
            let token_text: Option<String> = row.try_get("token_text").ok()?;
            let forced: Option<bool> = row.try_get("forced").ok()?;

            Some(LogStep {
                step_index: step,
                token: sampled_token,
                token_text,
                forced: forced.unwrap_or(false),
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
                created_at,
            })
        })
        .collect::<Vec<_>>();

    // Fetch mod_calls
    let mod_call_rows = sqlx::query(
        r#"
        SELECT
            id,
            event_id,
            mod_name,
            event_type::text AS event_type,
            step,
            created_at,
            execution_time_ms,
            exception_occurred,
            exception_message
        FROM mod_calls
        WHERE request_id = $1
        ORDER BY created_at ASC
        "#,
    )
    .bind(request_id)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    let mod_calls: Vec<ModCallLog> = mod_call_rows
        .into_iter()
        .map(|row| {
            let id: i64 = row.try_get("id")?;
            let event_id: i64 = row.try_get("event_id")?;
            let mod_name: String = row.try_get("mod_name")?;
            let event_type: String = row.try_get("event_type")?;
            let step: i32 = row.try_get("step")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;
            let execution_time_ms: Option<f64> = row.try_get("execution_time_ms")?;
            let exception_occurred: bool = row.try_get("exception_occurred")?;
            let exception_message: Option<String> = row.try_get("exception_message")?;

            Ok(ModCallLog {
                id,
                event_id,
                mod_name,
                event_type,
                step,
                created_at,
                execution_time_ms,
                exception_occurred,
                exception_message,
            })
        })
        .collect::<std::result::Result<Vec<_>, sqlx::Error>>()
        .map_err(ApiError::from)?;

    // Fetch mod_logs
    let mod_log_rows = sqlx::query(
        r#"
        SELECT
            id,
            mod_call_id,
            mod_name,
            log_message,
            log_level::text AS log_level,
            created_at
        FROM mod_logs
        WHERE request_id = $1
        ORDER BY created_at ASC
        "#,
    )
    .bind(request_id)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    let mod_logs: Vec<ModLogEntry> = mod_log_rows
        .into_iter()
        .map(|row| {
            let id: i64 = row.try_get("id")?;
            let mod_call_id: i64 = row.try_get("mod_call_id")?;
            let mod_name: String = row.try_get("mod_name")?;
            let log_message: String = row.try_get("log_message")?;
            let log_level: String = row.try_get("log_level")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;

            Ok(ModLogEntry {
                id,
                mod_call_id,
                mod_name,
                log_message,
                log_level,
                created_at,
            })
        })
        .collect::<std::result::Result<Vec<_>, sqlx::Error>>()
        .map_err(ApiError::from)?;

    // Fetch actions
    let action_rows = sqlx::query(
        r#"
        SELECT
            id,
            mod_call_id,
            action_type::text AS action_type,
            action_order,
            created_at,
            details,
            tokens,
            tokens_as_text,
            token_count,
            backtrack_steps
        FROM actions
        WHERE request_id = $1
        ORDER BY created_at ASC, action_order ASC
        "#,
    )
    .bind(request_id)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    let actions = action_rows
        .into_iter()
        .map(|row| {
            let action_id: i64 = row.try_get("id")?;
            let mod_call_id: i64 = row.try_get("mod_call_id")?;
            let action_type: String = row.try_get("action_type")?;
            let _action_order: i32 = row.try_get("action_order")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;
            let details: Option<Value> = row.try_get("details")?;
            let tokens: Option<Vec<i32>> = row.try_get("tokens")?;
            // Handle both TEXT[] (new) and TEXT (old) column types for backwards compatibility
            let tokens_as_text: Option<Vec<String>> = row
                .try_get::<Option<Vec<String>>, _>("tokens_as_text")
                .ok()
                .flatten()
                .or_else(|| {
                    // Fall back to reading as single string and wrapping in vec
                    row.try_get::<Option<String>, _>("tokens_as_text")
                        .ok()
                        .flatten()
                        .map(|s| vec![s])
                });
            let token_count: Option<i32> = row.try_get("token_count")?;
            let backtrack_steps: Option<i32> = row.try_get("backtrack_steps")?;

            // Build payload by merging details with column values
            let mut payload = match details {
                Some(Value::Object(map)) => map,
                _ => serde_json::Map::new(),
            };

            // Add tokens if present and not already in payload
            if let Some(t) = tokens {
                if !payload.contains_key("tokens") {
                    payload.insert(
                        "tokens".to_string(),
                        Value::Array(t.into_iter().map(|n| Value::Number(n.into())).collect()),
                    );
                }
            }

            // Add tokens_as_text if present and not already in payload
            if let Some(t) = tokens_as_text {
                if !payload.contains_key("tokens_as_text") {
                    payload.insert(
                        "tokens_as_text".to_string(),
                        Value::Array(t.into_iter().map(Value::String).collect()),
                    );
                }
            }

            // Add token_count if present and not already in payload
            if let Some(c) = token_count {
                if !payload.contains_key("token_count") {
                    payload.insert("token_count".to_string(), Value::Number(c.into()));
                }
            }

            // Add backtrack_steps if present and not already in payload
            if let Some(n) = backtrack_steps {
                if !payload.contains_key("backtrack_steps") {
                    payload.insert("backtrack_steps".to_string(), Value::Number(n.into()));
                }
            }

            Ok(ActionLog {
                action_id,
                step_index: None,
                mod_id: Some(mod_call_id as i32),
                block_id: None,
                block_key: None,
                action_type,
                event: None,
                payload: Value::Object(payload),
                created_at,
            })
        })
        .collect::<std::result::Result<Vec<_>, sqlx::Error>>()
        .map_err(ApiError::from)?;

    // Build events list from raw event data
    let events: Vec<EventLog> = event_rows
        .iter()
        .map(|row| {
            let id: i64 = row.try_get("id")?;
            let event_type: String = row.try_get("event_type")?;
            let step: i32 = row.try_get("step")?;
            let sequence_order: i32 = row.try_get("sequence_order")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;
            let prompt_length: Option<i32> = row.try_get("prompt_length")?;
            let max_steps: Option<i32> = row.try_get("max_steps")?;
            let input_text: Option<String> = row.try_get("input_text")?;
            let top_tokens: Option<Value> = row.try_get("top_tokens")?;
            let sampled_token: Option<i32> = row.try_get("sampled_token")?;
            let token_text: Option<String> = row.try_get("token_text")?;
            let added_tokens: Option<Vec<i32>> = row.try_get("added_tokens")?;
            let added_token_count: Option<i32> = row.try_get("added_token_count")?;
            let forced: Option<bool> = row.try_get("forced")?;

            Ok(EventLog {
                id,
                event_type,
                step,
                sequence_order,
                created_at,
                prompt_length,
                max_steps,
                input_text,
                top_tokens,
                sampled_token,
                token_text,
                added_tokens,
                added_token_count,
                forced,
            })
        })
        .collect::<std::result::Result<Vec<_>, sqlx::Error>>()
        .map_err(ApiError::from)?;

    // step_logit_summaries no longer exists in new schema
    let step_logit_summaries = Vec::new();

    // inference_stats is now stored as JSONB in requests table
    let inference_stats_log = None;

    // Fetch discussion count
    let discussion_count: i64 =
        sqlx::query_scalar(r#"SELECT COUNT(*) FROM discussions WHERE request_id = $1"#)
            .bind(request_id)
            .fetch_one(pool)
            .await
            .map_err(ApiError::from)?;

    let response = LogResponse {
        request_id: request_id.to_string(),
        created_ts,
        finished_ts,
        system_prompt: None,
        user_prompt,
        formatted_prompt: None,
        model_id,
        user_api_key,
        is_public,
        public_token,
        model_version: None,
        tokenizer_version: None,
        vocab_hash: None,
        sampler_preset: None,
        sampler_algo: None,
        rng_seed: None,
        max_steps: max_tokens,
        active_mod,
        final_tokens,
        final_text,
        sequence_confidence: None,
        eos_reason: None,
        request_tags: Value::Object(Default::default()),
        favorited_by,
        tags,
        events,
        mod_calls,
        mod_logs,
        actions,
        steps,
        step_logit_summaries,
        inference_stats: inference_stats_log,
        discussion_count,
    };

    Ok(response)
}

/// Fetch a fully hydrated log record, including steps, actions, and summaries.
///
/// Results are cached in an LRU cache with a 2.8 GB memory limit.
///
/// Authentication is required for non-public requests. Non-admin users can only
/// access logs that belong to their allowed_api_key or are marked as public.
pub async fn get_log(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<LogResponse>> {
    // Try to authenticate (optional for public requests)
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    // Only admins can see user_api_key
    let is_admin = auth.as_ref().map(|a| a.is_admin).unwrap_or(false);

    // Helper to check access and return appropriate error
    let check_access = |log: &LogResponse| -> Result<()> {
        // Public logs are accessible to everyone
        if log.is_public {
            return Ok(());
        }

        // Private logs require authentication
        match &auth {
            None => {
                // No authentication provided for non-public log
                Err(ApiError::unauthorized(
                    "Authentication required to access this log",
                ))
            }
            Some(auth_key) => {
                // Admins can access everything
                if auth_key.is_admin {
                    return Ok(());
                }
                // Non-admins can only access their own logs
                if let Some(ref allowed_key) = auth_key.allowed_api_key {
                    if log.user_api_key.as_ref() == Some(allowed_key) {
                        return Ok(());
                    }
                }
                Err(ApiError::forbidden("You don't have access to this log"))
            }
        }
    };

    // Check cache first
    if let Some(cached) = state.log_cache.get(&request_id) {
        tracing::debug!(request_id = %request_id, "Cache hit");

        // Authorization check
        check_access(&cached)?;

        // Hide user_api_key for non-admins
        let mut response = cached;
        if !is_admin {
            response.user_api_key = None;
        }

        return Ok(Json(response));
    }

    tracing::debug!(request_id = %request_id, "Cache miss, fetching from database");

    let response = fetch_log_response(&state.db_pool, &request_id).await?;

    // Authorization check
    check_access(&response)?;

    // Cache the response for future requests
    state.log_cache.insert(request_id, response.clone());

    // Hide user_api_key for non-admins
    let mut response = response;
    if !is_admin {
        response.user_api_key = None;
    }

    Ok(Json(response))
}

/// Warm the cache with the latest N logs.
///
/// This is called at server startup to pre-populate the cache with recent logs.
/// Fetch multiple log responses in a single batched operation.
/// This is much more efficient than calling fetch_log_response in a loop
/// as it reduces the number of database queries from 6*N to 6.
pub async fn fetch_log_responses_batch(
    pool: &PgPool,
    request_ids: &[String],
) -> Result<HashMap<String, LogResponse>> {
    if request_ids.is_empty() {
        return Ok(HashMap::new());
    }

    // Fetch all requests in one query
    let request_rows = sqlx::query(
        r#"
        SELECT
            r.request_id,
            r.created_at,
            r.completed_at,
            r.model,
            r.user_api_key,
            r.is_public,
            r.public_token,
            r.max_tokens,
            r.temperature,
            r.mod,
            r.user_prompt,
            r.user_prompt_token_ids,
            r.active_mod_name,
            r.final_token_ids,
            r.final_text,
            r.inference_stats,
            r.favorited_by,
            r.tags
        FROM requests r
        WHERE r.request_id = ANY($1)
        "#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    // Build a map of request_id -> base request data
    let mut responses: HashMap<String, LogResponse> = HashMap::new();
    for row in request_rows {
        let request_id: String = row.try_get("request_id")?;
        let created_ts: DateTime<Utc> = row.try_get("created_at")?;
        let finished_ts: Option<DateTime<Utc>> = row.try_get("completed_at")?;
        let model_id: Option<String> = row.try_get("model")?;
        let user_api_key: Option<String> = row.try_get("user_api_key")?;
        let is_public: bool = row.try_get("is_public").unwrap_or(false);
        let public_token: Option<String> = row.try_get("public_token").ok().flatten();
        let max_tokens: Option<i32> = row.try_get("max_tokens")?;
        let user_prompt: Option<String> = row.try_get("user_prompt")?;
        let active_mod_name: Option<String> = row.try_get("active_mod_name")?;
        let final_tokens: Option<Vec<i32>> = row.try_get("final_token_ids")?;
        let final_text: Option<String> = row.try_get("final_text")?;
        let favorited_by: Vec<String> = row.try_get("favorited_by").unwrap_or_default();
        let tags: Vec<String> = row.try_get("tags").unwrap_or_default();

        let active_mod = active_mod_name.map(|name| ActiveMod {
            id: 0,
            name: Some(name),
        });

        responses.insert(
            request_id.clone(),
            LogResponse {
                request_id,
                created_ts,
                finished_ts,
                system_prompt: None,
                user_prompt,
                formatted_prompt: None,
                model_id,
                user_api_key,
                is_public,
                public_token,
                model_version: None,
                tokenizer_version: None,
                vocab_hash: None,
                sampler_preset: None,
                sampler_algo: None,
                rng_seed: None,
                max_steps: max_tokens,
                active_mod,
                final_tokens,
                final_text,
                sequence_confidence: None,
                eos_reason: None,
                request_tags: Value::Object(Default::default()),
                favorited_by,
                tags,
                events: Vec::new(),
                mod_calls: Vec::new(),
                mod_logs: Vec::new(),
                actions: Vec::new(),
                steps: Vec::new(),
                step_logit_summaries: Vec::new(),
                inference_stats: None,
                discussion_count: 0,
            },
        );
    }

    // Fetch all events in one query
    let event_rows = sqlx::query(
        r#"
        SELECT
            request_id,
            id,
            event_type::text AS event_type,
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
        FROM events
        WHERE request_id = ANY($1)
        ORDER BY request_id, sequence_order ASC
        "#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    // Group events by request_id and also build steps
    for row in &event_rows {
        let request_id: String = row.try_get("request_id")?;
        if let Some(response) = responses.get_mut(&request_id) {
            let id: i64 = row.try_get("id")?;
            let event_type: String = row.try_get("event_type")?;
            let step: i32 = row.try_get("step")?;
            let sequence_order: i32 = row.try_get("sequence_order")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;
            let prompt_length: Option<i32> = row.try_get("prompt_length")?;
            let max_steps: Option<i32> = row.try_get("max_steps")?;
            let input_text: Option<String> = row.try_get("input_text")?;
            let top_tokens: Option<Value> = row.try_get("top_tokens")?;
            let sampled_token: Option<i32> = row.try_get("sampled_token")?;
            let token_text: Option<String> = row.try_get("token_text")?;
            let added_tokens: Option<Vec<i32>> = row.try_get("added_tokens")?;
            let added_token_count: Option<i32> = row.try_get("added_token_count")?;
            let forced: Option<bool> = row.try_get("forced")?;

            response.events.push(EventLog {
                id,
                event_type: event_type.clone(),
                step,
                sequence_order,
                created_at,
                prompt_length,
                max_steps,
                input_text,
                top_tokens,
                sampled_token,
                token_text: token_text.clone(),
                added_tokens,
                added_token_count,
                forced,
            });

            // Build step from Sampled events
            if event_type == "Sampled" {
                response.steps.push(LogStep {
                    step_index: step,
                    token: sampled_token,
                    token_text,
                    forced: forced.unwrap_or(false),
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
                    created_at,
                });
            }
        }
    }

    // Fetch all mod_calls in one query
    let mod_call_rows = sqlx::query(
        r#"
        SELECT
            request_id,
            id,
            event_id,
            mod_name,
            event_type::text AS event_type,
            step,
            created_at,
            execution_time_ms,
            exception_occurred,
            exception_message
        FROM mod_calls
        WHERE request_id = ANY($1)
        ORDER BY request_id, created_at ASC
        "#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    for row in mod_call_rows {
        let request_id: String = row.try_get("request_id")?;
        if let Some(response) = responses.get_mut(&request_id) {
            response.mod_calls.push(ModCallLog {
                id: row.try_get("id")?,
                event_id: row.try_get("event_id")?,
                mod_name: row.try_get("mod_name")?,
                event_type: row.try_get("event_type")?,
                step: row.try_get("step")?,
                created_at: row.try_get("created_at")?,
                execution_time_ms: row.try_get("execution_time_ms")?,
                exception_occurred: row.try_get("exception_occurred")?,
                exception_message: row.try_get("exception_message")?,
            });
        }
    }

    // Fetch all mod_logs in one query
    let mod_log_rows = sqlx::query(
        r#"
        SELECT
            request_id,
            id,
            mod_call_id,
            mod_name,
            log_message,
            log_level::text AS log_level,
            created_at
        FROM mod_logs
        WHERE request_id = ANY($1)
        ORDER BY request_id, created_at ASC
        "#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    for row in mod_log_rows {
        let request_id: String = row.try_get("request_id")?;
        if let Some(response) = responses.get_mut(&request_id) {
            response.mod_logs.push(ModLogEntry {
                id: row.try_get("id")?,
                mod_call_id: row.try_get("mod_call_id")?,
                mod_name: row.try_get("mod_name")?,
                log_message: row.try_get("log_message")?,
                log_level: row.try_get("log_level")?,
                created_at: row.try_get("created_at")?,
            });
        }
    }

    // Fetch all actions in one query
    let action_rows = sqlx::query(
        r#"
        SELECT
            request_id,
            id,
            mod_call_id,
            action_type::text AS action_type,
            action_order,
            created_at,
            details,
            tokens,
            tokens_as_text,
            token_count,
            backtrack_steps
        FROM actions
        WHERE request_id = ANY($1)
        ORDER BY request_id, created_at ASC, action_order ASC
        "#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    for row in action_rows {
        let request_id: String = row.try_get("request_id")?;
        if let Some(response) = responses.get_mut(&request_id) {
            let action_id: i64 = row.try_get("id")?;
            let mod_call_id: i64 = row.try_get("mod_call_id")?;
            let action_type: String = row.try_get("action_type")?;
            let created_at: DateTime<Utc> = row.try_get("created_at")?;
            let details: Option<Value> = row.try_get("details")?;
            let tokens: Option<Vec<i32>> = row.try_get("tokens")?;
            let tokens_as_text: Option<Vec<String>> = row
                .try_get::<Option<Vec<String>>, _>("tokens_as_text")
                .ok()
                .flatten()
                .or_else(|| {
                    row.try_get::<Option<String>, _>("tokens_as_text")
                        .ok()
                        .flatten()
                        .map(|s| vec![s])
                });
            let token_count: Option<i32> = row.try_get("token_count")?;
            let backtrack_steps: Option<i32> = row.try_get("backtrack_steps")?;

            let mut payload = match details {
                Some(Value::Object(map)) => map,
                _ => serde_json::Map::new(),
            };

            if let Some(t) = tokens {
                if !payload.contains_key("tokens") {
                    payload.insert(
                        "tokens".to_string(),
                        Value::Array(t.into_iter().map(|n| Value::Number(n.into())).collect()),
                    );
                }
            }
            if let Some(t) = tokens_as_text {
                if !payload.contains_key("tokens_as_text") {
                    payload.insert(
                        "tokens_as_text".to_string(),
                        Value::Array(t.into_iter().map(Value::String).collect()),
                    );
                }
            }
            if let Some(c) = token_count {
                if !payload.contains_key("token_count") {
                    payload.insert("token_count".to_string(), Value::Number(c.into()));
                }
            }
            if let Some(n) = backtrack_steps {
                if !payload.contains_key("backtrack_steps") {
                    payload.insert("backtrack_steps".to_string(), Value::Number(n.into()));
                }
            }

            response.actions.push(ActionLog {
                action_id,
                step_index: None,
                mod_id: Some(mod_call_id as i32),
                block_id: None,
                block_key: None,
                action_type,
                event: None,
                payload: Value::Object(payload),
                created_at,
            });
        }
    }

    // Fetch all discussion counts in one query
    let discussion_counts: Vec<(String, i64)> = sqlx::query_as(
        r#"SELECT request_id, COUNT(*) as count FROM discussions WHERE request_id = ANY($1) GROUP BY request_id"#,
    )
    .bind(request_ids)
    .fetch_all(pool)
    .await
    .map_err(ApiError::from)?;

    for (request_id, count) in discussion_counts {
        if let Some(response) = responses.get_mut(&request_id) {
            response.discussion_count = count;
        }
    }

    Ok(responses)
}

pub async fn warm_cache(pool: &PgPool, cache: &LogCache, limit: i64) {
    info!(limit = limit, "Warming cache with latest logs");

    // Fetch the latest request_ids
    let request_ids: Vec<String> = match sqlx::query_scalar(
        r#"SELECT request_id FROM requests ORDER BY created_at DESC LIMIT $1"#,
    )
    .bind(limit)
    .fetch_all(pool)
    .await
    {
        Ok(ids) => ids,
        Err(e) => {
            tracing::warn!(error = %e, "Failed to fetch request_ids for cache warming");
            return;
        }
    };

    let total = request_ids.len();

    // Batch fetch all logs at once
    let responses = match fetch_log_responses_batch(pool, &request_ids).await {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!(error = %e, "Failed to batch fetch logs for cache warming");
            return;
        }
    };

    let cached = responses.len();
    for (request_id, response) in responses {
        cache.insert(request_id, response);
    }

    let stats = cache.stats();
    info!(
        cached = cached,
        total = total,
        cache_entries = stats.entry_count,
        cache_bytes = stats.current_bytes,
        "Cache warming complete"
    );
}

// ============================================================================
// Public Request Sharing Handlers
// ============================================================================

/// Generate a secure random token for public request URLs
fn generate_public_token() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    hex::encode(bytes)
}

/// Response for making a request public.
#[derive(Debug, Serialize)]
pub struct MakeRequestPublicResponse {
    pub request_id: String,
    pub is_public: bool,
    pub public_token: Option<String>,
    pub public_url: Option<String>,
    pub message: String,
}

/// Make a request public and generate a shareable link.
/// Only accessible by owner or admin.
///
/// POST /logs/:request_id/public
pub async fn make_request_public(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<MakeRequestPublicResponse>> {
    // Authenticate the user
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    let auth = match auth {
        Some(a) => a,
        None => {
            return Err(ApiError::unauthorized("Authentication required"));
        }
    };

    // Check if request exists and user has access
    let request_row = sqlx::query(
        "SELECT request_id, user_api_key, is_public, public_token FROM requests WHERE request_id = $1",
    )
    .bind(&request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let row = request_row.ok_or_else(|| ApiError::NotFound("Request not found".into()))?;

    let user_api_key: Option<String> = row.try_get("user_api_key").ok().flatten();

    // Authorization check: non-admin users can only make their own requests public
    if !auth.is_admin {
        if let Some(ref allowed_key) = auth.allowed_api_key {
            if user_api_key.as_ref() != Some(allowed_key) {
                return Err(ApiError::forbidden("You don't have access to this request"));
            }
        }
    }

    // Generate a new public token
    let public_token = generate_public_token();

    // Update the request
    sqlx::query("UPDATE requests SET is_public = TRUE, public_token = $1 WHERE request_id = $2")
        .bind(&public_token)
        .bind(&request_id)
        .execute(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

    // Invalidate cache for this request
    state.log_cache.invalidate(&request_id);

    let public_url = format!("/share/request/{}", public_token);

    Ok(Json(MakeRequestPublicResponse {
        request_id,
        is_public: true,
        public_token: Some(public_token),
        public_url: Some(public_url),
        message: "Request is now public".to_string(),
    }))
}

/// Make a request private (remove public access).
/// Only accessible by owner or admin.
///
/// DELETE /logs/:request_id/public
pub async fn make_request_private(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<MakeRequestPublicResponse>> {
    // Authenticate the user
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    let auth = match auth {
        Some(a) => a,
        None => {
            return Err(ApiError::unauthorized("Authentication required"));
        }
    };

    // Check if request exists and user has access
    let request_row = sqlx::query(
        "SELECT request_id, user_api_key, is_public, public_token FROM requests WHERE request_id = $1",
    )
    .bind(&request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let row = request_row.ok_or_else(|| ApiError::NotFound("Request not found".into()))?;

    let user_api_key: Option<String> = row.try_get("user_api_key").ok().flatten();

    // Authorization check: non-admin users can only make their own requests private
    if !auth.is_admin {
        if let Some(ref allowed_key) = auth.allowed_api_key {
            if user_api_key.as_ref() != Some(allowed_key) {
                return Err(ApiError::forbidden("You don't have access to this request"));
            }
        }
    }

    // Update the request
    sqlx::query("UPDATE requests SET is_public = FALSE, public_token = NULL WHERE request_id = $1")
        .bind(&request_id)
        .execute(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

    // Invalidate cache for this request
    state.log_cache.invalidate(&request_id);

    Ok(Json(MakeRequestPublicResponse {
        request_id,
        is_public: false,
        public_token: None,
        public_url: None,
        message: "Request is now private".to_string(),
    }))
}

/// Get a public request by its public token.
/// No authentication required.
///
/// GET /share/request/:public_token
pub async fn get_public_request(
    State(state): State<AppState>,
    Path(public_token): Path<String>,
) -> Result<Json<LogResponse>> {
    // Find the request by public token
    let request_id: Option<String> = sqlx::query_scalar(
        "SELECT request_id FROM requests WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&public_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let request_id = request_id
        .ok_or_else(|| ApiError::NotFound("Public request not found or link has expired".into()))?;

    // Check cache first
    if let Some(cached) = state.log_cache.get(&request_id) {
        tracing::debug!(request_id = %request_id, "Public request cache hit");
        let mut response = cached;
        // Never expose user_api_key in public endpoints
        response.user_api_key = None;
        return Ok(Json(response));
    }

    tracing::debug!(request_id = %request_id, "Public request cache miss");

    // Fetch the full log response
    let response = fetch_log_response(&state.db_pool, &request_id).await?;

    // Cache the response for future requests
    state.log_cache.insert(request_id, response.clone());

    // Never expose user_api_key in public endpoints
    let mut response = response;
    response.user_api_key = None;

    Ok(Json(response))
}

/// Path parameters for accessing a request via a public collection
#[derive(Debug, Deserialize)]
pub struct CollectionRequestPath {
    pub collection_token: String,
    pub request_id: String,
}

/// Get a request via a public collection's shareable token.
///
/// GET /share/:collection_token/request/:request_id
///
/// This allows accessing any request that belongs to a public collection,
/// even if the request itself is not individually marked as public.
/// The request must be a member of the collection identified by the token.
pub async fn get_request_via_collection(
    State(state): State<AppState>,
    Path(params): Path<CollectionRequestPath>,
) -> Result<Json<LogResponse>> {
    info!(
        collection_token = %params.collection_token,
        request_id = %params.request_id,
        "get_request_via_collection called"
    );

    // First, verify the collection exists and is public
    let collection_exists: Option<i64> = sqlx::query_scalar(
        "SELECT id FROM collections WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&params.collection_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_id = collection_exists.ok_or_else(|| {
        info!(
            collection_token = %params.collection_token,
            "Collection not found or not public"
        );
        ApiError::NotFound("Public collection not found or link has expired".into())
    })?;

    info!(
        collection_id = collection_id,
        request_id = %params.request_id,
        "Found collection, checking if request belongs to it"
    );

    // Verify the request belongs to this collection
    // Use COUNT instead of EXISTS for more reliable scalar handling
    let request_count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM collection_requests WHERE collection_id = $1 AND request_id = $2",
    )
    .bind(collection_id)
    .bind(&params.request_id)
    .fetch_one(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    info!(
        collection_id = collection_id,
        request_id = %params.request_id,
        request_count = request_count,
        "Request membership check result"
    );

    if request_count == 0 {
        return Err(ApiError::NotFound(
            "Request not found in this collection".into(),
        ));
    }

    // Check cache first
    if let Some(cached) = state.log_cache.get(&params.request_id) {
        tracing::debug!(request_id = %params.request_id, "Collection request cache hit");
        let mut response = cached;
        // Never expose user_api_key in public endpoints
        response.user_api_key = None;
        return Ok(Json(response));
    }

    tracing::debug!(request_id = %params.request_id, "Collection request cache miss");

    // Fetch the full log response
    let response = fetch_log_response(&state.db_pool, &params.request_id).await?;

    // Cache the response for future requests
    state
        .log_cache
        .insert(params.request_id.clone(), response.clone());

    // Never expose user_api_key in public endpoints
    let mut response = response;
    response.user_api_key = None;

    Ok(Json(response))
}
