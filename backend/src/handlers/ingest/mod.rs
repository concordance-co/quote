use axum::{Json, extract::State, http::StatusCode};
use tracing::info;

use crate::utils::{ApiError, AppState, NewLogEvent};

pub type Result<T> = std::result::Result<T, ApiError>;

mod payload;
mod persist;
mod to_response;
pub mod util;

use persist::{
    persist_request, replace_actions, replace_events, replace_mod_calls, replace_mod_logs,
};
use to_response::payload_to_response;

pub use payload::{
    ActionRecord, ActionType, EventRecord, EventType, FullIngestPayload, LogLevel, ModCallRecord,
    ModLogRecord, RequestRecord,
};

/// Persist a full inference payload, replacing previous request artifacts in a single transaction.
///
/// After successfully persisting to the database, the response is also cached for fast retrieval,
/// and a new log event is broadcast to all SSE subscribers.
pub async fn ingest_payload(
    State(state): State<AppState>,
    Json(payload): Json<FullIngestPayload>,
) -> Result<StatusCode> {
    let request = &payload.request;
    let request_id = request.request_id.clone();

    info!("Received ingest request for request_id: {}", request_id);

    // Wrap the ingest in a transaction so request data across tables remains consistent.
    let mut tx = state.db_pool.begin().await.map_err(ApiError::from)?;

    // 1. Persist request
    persist_request(&mut tx, request).await?;

    // 2. Persist events and get their IDs
    let event_ids = replace_events(&mut tx, request, &payload.events).await?;

    // 3. Persist mod_calls and get their IDs
    let mod_call_ids = replace_mod_calls(&mut tx, request, &payload.mod_calls, &event_ids).await?;

    // 4. Persist mod_logs (using mod_call_ids)
    replace_mod_logs(&mut tx, request, &payload.mod_logs, &mod_call_ids).await?;

    // 5. Persist actions (using mod_call_ids)
    replace_actions(&mut tx, request, &payload.actions, &mod_call_ids).await?;

    // Commit the transaction
    tx.commit().await.map_err(ApiError::from)?;

    info!(
        "Successfully persisted payload to Neon for request_id: {}",
        request_id
    );

    // Populate cache with the response (write-through caching)
    // This allows subsequent reads to be served from cache immediately
    let response = payload_to_response(&payload, &event_ids, &mod_call_ids);
    state.log_cache.insert(request_id.clone(), response.clone());

    info!(
        request_id = %request_id,
        "Cached response for fast retrieval"
    );

    // Broadcast new log event to SSE subscribers
    // Calculate total steps from events (step is 0-indexed, so max + 1 = count)
    let total_steps = payload
        .events
        .iter()
        .map(|e| e.step)
        .max()
        .map(|s| s as i64 + 1)
        .unwrap_or(0);

    // Extract final text from response or payload
    let final_text = response.final_text.clone();

    let new_log_event = NewLogEvent {
        request_id: request_id.clone(),
        created_ts: response.created_ts,
        finished_ts: response.finished_ts,
        model_id: response.model_id.clone(),
        user_api_key: request.user_api_key.clone(),
        final_text,
        total_steps,
        favorited_by: vec![],
        discussion_count: 0,
    };

    state.broadcast_new_log(new_log_event);

    info!(
        request_id = %request_id,
        "Broadcast new log event to SSE subscribers"
    );

    Ok(StatusCode::CREATED)
}
