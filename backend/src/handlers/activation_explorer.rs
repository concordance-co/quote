//! Activation explorer handlers.
//!
//! API layer that runs HF inference + SAE feature extraction and maintains a
//! lightweight run index in Postgres for fast listing/comparison queries.

use axum::{
    Json,
    extract::{Path, Query, State},
    http::StatusCode,
};
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sqlx::{Postgres, QueryBuilder, Row};
use uuid::Uuid;

use crate::utils::AppState;

const HF_INFERENCE_TIMEOUT_SECS: u64 = 180;

#[derive(Debug, Deserialize)]
pub struct ActivationRunRequest {
    pub prompt: String,
    pub model_id: Option<String>,
    pub max_tokens: Option<i32>,
    pub temperature: Option<f64>,
    pub top_p: Option<f64>,
    pub top_k: Option<i32>,
    pub collect_activations: Option<bool>,
    pub inline_sae: Option<bool>,
    pub sae_id: Option<String>,
    pub sae_layer: Option<i32>,
    pub sae_top_k: Option<i32>,
    pub sae_local_path: Option<String>,
    pub request_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ActivationRunSummary {
    pub request_id: String,
    pub created_at: DateTime<Utc>,
    pub model_id: String,
    pub prompt_chars: i32,
    pub output_tokens: i32,
    pub events_count: i32,
    pub actions_count: i32,
    pub activation_rows_count: i32,
    pub unique_features_count: i32,
    pub sae_enabled: bool,
    pub sae_id: Option<String>,
    pub sae_layer: Option<i32>,
    pub duration_ms: i32,
    pub status: String,
    pub error_message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_features_preview: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct ActivationRunResponse {
    pub request_id: String,
    pub status: String,
    pub run_summary: ActivationRunSummary,
    pub output: ActivationOutput,
    pub preview: ActivationPreview,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Serialize)]
pub struct ActivationOutput {
    pub text: String,
    pub token_ids: Vec<i64>,
}

#[derive(Debug, Serialize)]
pub struct ActivationPreview {
    pub events: Vec<Value>,
    pub actions: Vec<Value>,
    pub activation_rows: Vec<Value>,
}

#[derive(Debug, Serialize)]
pub struct ActivationRunsResponse {
    pub items: Vec<ActivationRunSummary>,
    pub next_cursor: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ActivationRunsQuery {
    pub limit: Option<i64>,
    pub cursor: Option<String>,
    pub status: Option<String>,
    pub model_id: Option<String>,
    pub sae_enabled: Option<bool>,
}

#[derive(Debug, Deserialize)]
pub struct ActivationRowsQuery {
    pub feature_id: Option<i64>,
    pub sae_layer: Option<i64>,
    pub token_start: Option<i64>,
    pub token_end: Option<i64>,
    pub rank_max: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct FeatureDeltaQuery {
    pub feature_id: i64,
    pub sae_layer: Option<i64>,
    pub limit: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct TopFeaturesQuery {
    pub n: Option<i64>,
    pub sae_layer: Option<i64>,
}

#[derive(Debug, Deserialize)]
pub struct ExtractFeaturesRequest {
    pub token_ids: Vec<i64>,
    pub sae_id: Option<String>,
    pub sae_layer: Option<i32>,
    pub top_k: Option<i32>,
}

#[derive(Debug)]
struct RunIndexUpsert {
    request_id: String,
    created_at: DateTime<Utc>,
    model_id: String,
    prompt_chars: i32,
    output_tokens: i32,
    events_count: i32,
    actions_count: i32,
    activation_rows_count: i32,
    unique_features_count: i32,
    sae_enabled: bool,
    sae_id: Option<String>,
    sae_layer: Option<i32>,
    duration_ms: i32,
    status: String,
    error_message: Option<String>,
    top_features_preview: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct ActivationRunPreview {
    pub request_id: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub model_id: String,
    pub prompt: String,
    pub output_text: String,
    pub output_token_ids: Vec<i64>,
    pub sae_id: Option<String>,
    pub sae_layer: Option<i32>,
    pub sae_top_k: Option<i32>,
    pub feature_timeline: Value,
}

fn build_http_client(timeout_secs: u64) -> Result<Client, (StatusCode, Json<Value>)> {
    Client::builder()
        .timeout(std::time::Duration::from_secs(timeout_secs))
        .build()
        .map_err(|e| {
            explorer_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "INTERNAL",
                format!("failed to initialize HTTP client: {e}"),
                None,
            )
        })
}

fn explorer_error(
    status: StatusCode,
    error_code: &str,
    message: impl Into<String>,
    details: Option<Value>,
) -> (StatusCode, Json<Value>) {
    let mut payload = Map::new();
    payload.insert("status".to_string(), Value::String("error".to_string()));
    payload.insert(
        "error_code".to_string(),
        Value::String(error_code.to_string()),
    );
    payload.insert("message".to_string(), Value::String(message.into()));
    if let Some(details) = details {
        payload.insert("details".to_string(), details);
    }
    (status, Json(Value::Object(payload)))
}

fn clamp_i64(v: Option<i64>, default: i64, min: i64, max: i64) -> i64 {
    v.unwrap_or(default).clamp(min, max)
}

fn parse_cursor(cursor: &str) -> Result<(DateTime<Utc>, String), String> {
    let (ts_raw, request_id) = cursor
        .split_once('|')
        .ok_or_else(|| "cursor must be '<rfc3339>|<request_id>'".to_string())?;
    let created_at = DateTime::parse_from_rfc3339(ts_raw)
        .map_err(|_| "cursor timestamp must be RFC3339".to_string())?
        .with_timezone(&Utc);
    if request_id.trim().is_empty() {
        return Err("cursor request_id cannot be empty".to_string());
    }
    Ok((created_at, request_id.to_string()))
}

async fn upsert_run_index(state: &AppState, row: &RunIndexUpsert) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO activation_run_index (
            request_id,
            created_at,
            model_id,
            prompt_chars,
            output_tokens,
            events_count,
            actions_count,
            activation_rows_count,
            unique_features_count,
            sae_enabled,
            sae_id,
            sae_layer,
            duration_ms,
            status,
            error_message,
            top_features_preview,
            updated_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW()
        )
        ON CONFLICT (request_id) DO UPDATE SET
            created_at = EXCLUDED.created_at,
            model_id = EXCLUDED.model_id,
            prompt_chars = EXCLUDED.prompt_chars,
            output_tokens = EXCLUDED.output_tokens,
            events_count = EXCLUDED.events_count,
            actions_count = EXCLUDED.actions_count,
            activation_rows_count = EXCLUDED.activation_rows_count,
            unique_features_count = EXCLUDED.unique_features_count,
            sae_enabled = EXCLUDED.sae_enabled,
            sae_id = EXCLUDED.sae_id,
            sae_layer = EXCLUDED.sae_layer,
            duration_ms = EXCLUDED.duration_ms,
            status = EXCLUDED.status,
            error_message = EXCLUDED.error_message,
            top_features_preview = EXCLUDED.top_features_preview,
            updated_at = NOW()
        "#,
    )
    .bind(&row.request_id)
    .bind(row.created_at)
    .bind(&row.model_id)
    .bind(row.prompt_chars)
    .bind(row.output_tokens)
    .bind(row.events_count)
    .bind(row.actions_count)
    .bind(row.activation_rows_count)
    .bind(row.unique_features_count)
    .bind(row.sae_enabled)
    .bind(&row.sae_id)
    .bind(row.sae_layer)
    .bind(row.duration_ms)
    .bind(&row.status)
    .bind(&row.error_message)
    .bind(&row.top_features_preview)
    .execute(&state.db_pool)
    .await
    .map(|_| ())
}

pub async fn upsert_run_preview(
    state: &AppState,
    preview: &ActivationRunPreview,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO activation_run_previews (
            request_id,
            created_at,
            updated_at,
            model_id,
            prompt,
            output_text,
            output_token_ids,
            sae_id,
            sae_layer,
            sae_top_k,
            feature_timeline
        )
        VALUES (
            $1, $2, NOW(), $3, $4, $5, $6, $7, $8, $9, $10
        )
        ON CONFLICT (request_id) DO UPDATE SET
            updated_at = NOW(),
            model_id = EXCLUDED.model_id,
            prompt = EXCLUDED.prompt,
            output_text = EXCLUDED.output_text,
            output_token_ids = EXCLUDED.output_token_ids,
            sae_id = EXCLUDED.sae_id,
            sae_layer = EXCLUDED.sae_layer,
            sae_top_k = EXCLUDED.sae_top_k,
            feature_timeline = EXCLUDED.feature_timeline
        "#,
    )
    .bind(&preview.request_id)
    .bind(preview.created_at)
    .bind(&preview.model_id)
    .bind(&preview.prompt)
    .bind(&preview.output_text)
    .bind(&preview.output_token_ids)
    .bind(&preview.sae_id)
    .bind(preview.sae_layer)
    .bind(preview.sae_top_k)
    .bind(&preview.feature_timeline)
    .execute(&state.db_pool)
    .await
    .map(|_| ())
}

pub async fn read_run_preview(
    state: &AppState,
    request_id: &str,
) -> Result<Option<ActivationRunPreview>, sqlx::Error> {
    let row = sqlx::query(
        r#"
        SELECT
            request_id,
            created_at,
            updated_at,
            model_id,
            prompt,
            output_text,
            output_token_ids,
            sae_id,
            sae_layer,
            sae_top_k,
            feature_timeline
        FROM activation_run_previews
        WHERE request_id = $1
        "#,
    )
    .bind(request_id)
    .fetch_optional(&state.db_pool)
    .await?;

    match row {
        Some(row) => Ok(Some(ActivationRunPreview {
            request_id: row.try_get("request_id")?,
            created_at: row.try_get("created_at")?,
            updated_at: row.try_get("updated_at")?,
            model_id: row.try_get("model_id")?,
            prompt: row.try_get("prompt")?,
            output_text: row.try_get("output_text")?,
            output_token_ids: row.try_get("output_token_ids")?,
            sae_id: row.try_get("sae_id")?,
            sae_layer: row.try_get("sae_layer")?,
            sae_top_k: row.try_get("sae_top_k")?,
            feature_timeline: row.try_get("feature_timeline")?,
        })),
        None => Ok(None),
    }
}

fn map_summary_row(row: &sqlx::postgres::PgRow) -> Result<ActivationRunSummary, sqlx::Error> {
    Ok(ActivationRunSummary {
        request_id: row.try_get("request_id")?,
        created_at: row.try_get("created_at")?,
        model_id: row.try_get("model_id")?,
        prompt_chars: row.try_get("prompt_chars")?,
        output_tokens: row.try_get("output_tokens")?,
        events_count: row.try_get("events_count")?,
        actions_count: row.try_get("actions_count")?,
        activation_rows_count: row.try_get("activation_rows_count")?,
        unique_features_count: row.try_get("unique_features_count")?,
        sae_enabled: row.try_get("sae_enabled")?,
        sae_id: row.try_get("sae_id")?,
        sae_layer: row.try_get("sae_layer")?,
        duration_ms: row.try_get("duration_ms")?,
        status: row.try_get("status")?,
        error_message: row.try_get("error_message")?,
        top_features_preview: row.try_get("top_features_preview")?,
    })
}

pub async fn run_activation(
    State(state): State<AppState>,
    Json(request): Json<ActivationRunRequest>,
) -> Result<Json<ActivationRunResponse>, (StatusCode, Json<Value>)> {
    let prompt = request.prompt.trim().to_string();
    if prompt.is_empty() {
        return Err(explorer_error(
            StatusCode::BAD_REQUEST,
            "INVALID_ARGUMENT",
            "prompt is required",
            None,
        ));
    }
    if prompt.chars().count() > 12_000 {
        return Err(explorer_error(
            StatusCode::BAD_REQUEST,
            "INVALID_ARGUMENT",
            "prompt exceeds 12000 characters",
            None,
        ));
    }
    if let Some(max_tokens) = request.max_tokens {
        if !(1..=2048).contains(&max_tokens) {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "max_tokens must be between 1 and 2048",
                None,
            ));
        }
    }
    if let Some(top_k) = request.top_k {
        if !(1..=200).contains(&top_k) {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "top_k must be between 1 and 200",
                None,
            ));
        }
    }
    if let Some(top_p) = request.top_p {
        if !(0.0..=1.0).contains(&top_p) {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "top_p must be between 0 and 1",
                None,
            ));
        }
    }
    if let Some(temperature) = request.temperature {
        if !(0.0..=2.0).contains(&temperature) {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "temperature must be between 0 and 2",
                None,
            ));
        }
    }

    let request_id = request
        .request_id
        .clone()
        .unwrap_or_else(|| format!("ax-{}", Uuid::new_v4().simple()));
    let created_at = Utc::now();
    let model_id = request
        .model_id
        .clone()
        .unwrap_or_else(|| "meta-llama/Llama-3.1-8B-Instruct".to_string());
    let sae_enabled = request.inline_sae.unwrap_or(true);
    let prompt_chars = prompt.chars().count() as i32;
    let max_tokens = request.max_tokens.unwrap_or(128);

    // -----------------------------------------------------------------------
    // Step 1: Call HF inference endpoint
    // -----------------------------------------------------------------------
    let hf_base_url = std::env::var("PLAYGROUND_ACTIVATIONS_HF_URL").unwrap_or_default();
    if hf_base_url.is_empty() {
        return Err(explorer_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "HF_NOT_CONFIGURED",
            "PLAYGROUND_ACTIVATIONS_HF_URL is not configured",
            None,
        ));
    }

    let client = build_http_client(HF_INFERENCE_TIMEOUT_SECS)?;
    let hf_url = format!("{}/hf/generate", hf_base_url.trim_end_matches('/'));

    let sae_id = request
        .sae_id
        .clone()
        .unwrap_or_else(|| "llama_scope_lxr_8x".to_string());
    let sae_layer = request.sae_layer.unwrap_or(16);
    let sae_top_k = request.sae_top_k.unwrap_or(20);

    let hf_payload = json!({
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": request.temperature.unwrap_or(0.7),
        "top_p": request.top_p.unwrap_or(0.9),
        "inline_sae": sae_enabled,
        "sae_id": sae_id,
        "sae_layer": sae_layer,
        "sae_top_k": sae_top_k,
    });

    let hf_result = client.post(&hf_url).json(&hf_payload).send().await;

    let hf_response = match hf_result {
        Ok(resp) => resp,
        Err(e) => {
            let (http_status, error_code, message) = if e.is_timeout() {
                (
                    StatusCode::GATEWAY_TIMEOUT,
                    "HF_TIMEOUT",
                    format!("HF inference timed out: {e}"),
                )
            } else {
                (
                    StatusCode::BAD_GATEWAY,
                    "HF_UNAVAILABLE",
                    format!("HF inference request failed: {e}"),
                )
            };

            let _ = upsert_run_index(
                &state,
                &RunIndexUpsert {
                    request_id: request_id.clone(),
                    created_at,
                    model_id: model_id.clone(),
                    prompt_chars,
                    output_tokens: 0,
                    events_count: 0,
                    actions_count: 0,
                    activation_rows_count: 0,
                    unique_features_count: 0,
                    sae_enabled,
                    sae_id: Some(sae_id.clone()),
                    sae_layer: Some(sae_layer),
                    duration_ms: 0,
                    status: "error".to_string(),
                    error_message: Some(message.clone()),
                    top_features_preview: None,
                },
            )
            .await;

            return Err(explorer_error(http_status, error_code, message, None));
        }
    };

    if !hf_response.status().is_success() {
        let status = hf_response.status();
        let body = hf_response.text().await.unwrap_or_default();
        let message = format!("HF inference returned {status}: {body}");

        let _ = upsert_run_index(
            &state,
            &RunIndexUpsert {
                request_id: request_id.clone(),
                created_at,
                model_id: model_id.clone(),
                prompt_chars,
                output_tokens: 0,
                events_count: 0,
                actions_count: 0,
                activation_rows_count: 0,
                unique_features_count: 0,
                sae_enabled,
                sae_id: Some(sae_id.clone()),
                sae_layer: Some(sae_layer),
                duration_ms: 0,
                status: "error".to_string(),
                error_message: Some(message.clone()),
                top_features_preview: None,
            },
        )
        .await;

        return Err(explorer_error(
            StatusCode::BAD_GATEWAY,
            "HF_BAD_RESPONSE",
            message,
            None,
        ));
    }

    let hf_json: Value = hf_response.json().await.map_err(|e| {
        explorer_error(
            StatusCode::BAD_GATEWAY,
            "HF_BAD_RESPONSE",
            format!("failed to parse HF response json: {e}"),
            None,
        )
    })?;

    let output_text = hf_json
        .get("output_text")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let output_token_ids: Vec<i64> = hf_json
        .get("output_token_ids")
        .and_then(Value::as_array)
        .map(|arr| arr.iter().filter_map(Value::as_i64).collect())
        .unwrap_or_default();

    // -----------------------------------------------------------------------
    // Step 2: Extract feature_timeline from the HF response (inline SAE)
    // -----------------------------------------------------------------------
    let feature_timeline = hf_json
        .get("feature_timeline")
        .cloned()
        .unwrap_or_else(|| Value::Array(vec![]));

    // -----------------------------------------------------------------------
    // Step 3: Compute summary stats from feature_timeline
    // -----------------------------------------------------------------------
    let unique_features_count = count_unique_features(&feature_timeline);
    let activation_rows = derive_activation_rows(
        &feature_timeline,
        &ActivationRowsQuery {
            feature_id: None,
            sae_layer: None,
            token_start: None,
            token_end: None,
            rank_max: None,
            limit: Some(500),
        },
    );
    let activation_rows_count = activation_rows.len().min(i32::MAX as usize) as i32;
    let top_features_preview = {
        let top = derive_top_features(&feature_timeline, 20);
        if top.is_empty() {
            None
        } else {
            Some(json!(top
                .iter()
                .filter_map(|f| f.get("feature_id").and_then(Value::as_i64))
                .collect::<Vec<_>>()))
        }
    };

    let duration_ms = Utc::now()
        .signed_duration_since(created_at)
        .num_milliseconds()
        .clamp(0, i32::MAX as i64) as i32;

    // -----------------------------------------------------------------------
    // Step 4: Persist to Postgres (index + preview)
    // -----------------------------------------------------------------------
    let summary = ActivationRunSummary {
        request_id: request_id.clone(),
        created_at,
        model_id: model_id.clone(),
        prompt_chars,
        output_tokens: output_token_ids.len().min(i32::MAX as usize) as i32,
        events_count: 0,
        actions_count: 0,
        activation_rows_count,
        unique_features_count,
        sae_enabled,
        sae_id: Some(sae_id.clone()),
        sae_layer: Some(sae_layer),
        duration_ms,
        status: "ok".to_string(),
        error_message: None,
        top_features_preview: top_features_preview.clone(),
    };

    upsert_run_index(
        &state,
        &RunIndexUpsert {
            request_id: summary.request_id.clone(),
            created_at: summary.created_at,
            model_id: summary.model_id.clone(),
            prompt_chars: summary.prompt_chars,
            output_tokens: summary.output_tokens,
            events_count: summary.events_count,
            actions_count: summary.actions_count,
            activation_rows_count: summary.activation_rows_count,
            unique_features_count: summary.unique_features_count,
            sae_enabled: summary.sae_enabled,
            sae_id: summary.sae_id.clone(),
            sae_layer: summary.sae_layer,
            duration_ms: summary.duration_ms,
            status: summary.status.clone(),
            error_message: summary.error_message.clone(),
            top_features_preview: summary.top_features_preview.clone(),
        },
    )
    .await
    .map_err(|e| {
        explorer_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "INDEX_WRITE_FAILED",
            format!("failed to persist run index: {e}"),
            None,
        )
    })?;

    let preview = ActivationRunPreview {
        request_id: request_id.clone(),
        created_at,
        updated_at: Utc::now(),
        model_id: model_id.clone(),
        prompt: prompt.clone(),
        output_text: output_text.clone(),
        output_token_ids: output_token_ids.clone(),
        sae_id: Some(sae_id.clone()),
        sae_layer: Some(sae_layer),
        sae_top_k: Some(sae_top_k),
        feature_timeline: feature_timeline.clone(),
    };

    upsert_run_preview(&state, &preview).await.map_err(|e| {
        explorer_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "PREVIEW_WRITE_FAILED",
            format!("failed to persist run preview: {e}"),
            None,
        )
    })?;

    // -----------------------------------------------------------------------
    // Step 5: Return ActivationRunResponse
    // -----------------------------------------------------------------------
    Ok(Json(ActivationRunResponse {
        request_id,
        status: "ok".to_string(),
        run_summary: summary,
        output: ActivationOutput {
            text: output_text,
            token_ids: output_token_ids,
        },
        preview: ActivationPreview {
            events: vec![],
            actions: vec![],
            activation_rows,
        },
        created_at,
    }))
}

/// Call the SAE feature extraction service. On failure, logs the error and
/// returns an empty timeline (partial success — output is OK but no features).
///
/// NOTE: This function is no longer called from `run_activation()` since SAE
/// extraction is now inline in the HF inference service. Retained for potential
/// fallback or other use cases.
#[allow(dead_code)]
async fn call_sae_extract(client: &Client, token_ids: &[i64], top_k: i32) -> Value {
    let sae_base_url = std::env::var("PLAYGROUND_SAE_URL").unwrap_or_default();
    if sae_base_url.is_empty() {
        tracing::warn!("PLAYGROUND_SAE_URL not configured; skipping feature extraction");
        return Value::Array(vec![]);
    }

    let extract_url = format!("{}/extract_features", sae_base_url.trim_end_matches('/'));
    let payload = json!({
        "tokens": token_ids,
        "top_k": top_k,
    });

    let result = client.post(&extract_url).json(&payload).send().await;
    let response = match result {
        Ok(resp) => resp,
        Err(e) => {
            tracing::error!("SAE extract request failed: {e}");
            return Value::Array(vec![]);
        }
    };

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        tracing::error!("SAE extract returned {status}: {body}");
        return Value::Array(vec![]);
    }

    match response.json::<Value>().await {
        Ok(json) => json
            .get("feature_timeline")
            .cloned()
            .unwrap_or_else(|| Value::Array(vec![])),
        Err(e) => {
            tracing::error!("failed to parse SAE extract response: {e}");
            Value::Array(vec![])
        }
    }
}

/// Call the HF inference service's `/hf/extract` endpoint for post-hoc SAE
/// feature extraction on pre-existing token IDs.
///
/// Returns the `feature_timeline` array on success, or an error tuple suitable
/// for returning from an Axum handler.
async fn call_hf_extract(
    token_ids: &[i64],
    sae_id: Option<&str>,
    sae_layer: Option<i32>,
    top_k: Option<i32>,
) -> Result<Value, (StatusCode, Json<Value>)> {
    let hf_base_url = std::env::var("PLAYGROUND_ACTIVATIONS_HF_URL").unwrap_or_default();
    if hf_base_url.is_empty() {
        return Err(explorer_error(
            StatusCode::SERVICE_UNAVAILABLE,
            "HF_NOT_CONFIGURED",
            "PLAYGROUND_ACTIVATIONS_HF_URL is not configured",
            None,
        ));
    }

    let client = build_http_client(HF_INFERENCE_TIMEOUT_SECS)?;
    let url = format!("{}/hf/extract", hf_base_url.trim_end_matches('/'));

    let mut payload = json!({ "token_ids": token_ids });
    if let Some(id) = sae_id {
        payload["sae_id"] = Value::String(id.to_string());
    }
    if let Some(layer) = sae_layer {
        payload["sae_layer"] = json!(layer);
    }
    if let Some(k) = top_k {
        payload["sae_top_k"] = json!(k);
    }

    let response = client.post(&url).json(&payload).send().await.map_err(|e| {
        if e.is_timeout() {
            explorer_error(
                StatusCode::GATEWAY_TIMEOUT,
                "HF_TIMEOUT",
                format!("HF extract timed out: {e}"),
                None,
            )
        } else {
            explorer_error(
                StatusCode::BAD_GATEWAY,
                "HF_UNAVAILABLE",
                format!("HF extract request failed: {e}"),
                None,
            )
        }
    })?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(explorer_error(
            StatusCode::BAD_GATEWAY,
            "HF_BAD_RESPONSE",
            format!("HF extract returned {status}: {body}"),
            None,
        ));
    }

    let hf_json: Value = response.json().await.map_err(|e| {
        explorer_error(
            StatusCode::BAD_GATEWAY,
            "HF_BAD_RESPONSE",
            format!("failed to parse HF extract response json: {e}"),
            None,
        )
    })?;

    Ok(hf_json
        .get("feature_timeline")
        .cloned()
        .unwrap_or_else(|| Value::Array(vec![])))
}

/// Count unique feature IDs across all positions in a feature_timeline.
fn count_unique_features(timeline: &Value) -> i32 {
    let entries = match timeline.as_array() {
        Some(arr) => arr,
        None => return 0,
    };
    let mut seen = std::collections::HashSet::new();
    for entry in entries {
        if let Some(feats) = entry.get("top_features").and_then(Value::as_array) {
            for feat in feats {
                if let Some(id) = feat.get("id").and_then(Value::as_i64) {
                    seen.insert(id);
                }
            }
        }
    }
    seen.len().min(i32::MAX as usize) as i32
}

pub async fn list_activation_runs(
    State(state): State<AppState>,
    Query(query): Query<ActivationRunsQuery>,
) -> Result<Json<ActivationRunsResponse>, (StatusCode, Json<Value>)> {
    let limit = clamp_i64(query.limit, 50, 1, 200);
    let mut cursor_filter: Option<(DateTime<Utc>, String)> = None;
    if let Some(cursor) = query.cursor.as_deref() {
        cursor_filter = Some(parse_cursor(cursor).map_err(|msg| {
            explorer_error(StatusCode::BAD_REQUEST, "INVALID_ARGUMENT", msg, None)
        })?);
    }

    let mut qb = QueryBuilder::<Postgres>::new(
        r#"
        SELECT
            request_id,
            created_at,
            model_id,
            prompt_chars,
            output_tokens,
            events_count,
            actions_count,
            activation_rows_count,
            unique_features_count,
            sae_enabled,
            sae_id,
            sae_layer,
            duration_ms,
            status,
            error_message,
            top_features_preview
        FROM activation_run_index
        WHERE 1=1
        "#,
    );

    if let Some(status) = query.status.as_deref() {
        if status != "ok" && status != "error" {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "status must be one of: ok, error",
                None,
            ));
        }
        qb.push(" AND status = ").push_bind(status);
    }
    if let Some(model_id) = query.model_id.as_deref() {
        qb.push(" AND model_id = ").push_bind(model_id);
    }
    if let Some(sae_enabled) = query.sae_enabled {
        qb.push(" AND sae_enabled = ").push_bind(sae_enabled);
    }
    if let Some((cursor_ts, cursor_request_id)) = cursor_filter {
        qb.push(" AND (created_at < ")
            .push_bind(cursor_ts)
            .push(" OR (created_at = ")
            .push_bind(cursor_ts)
            .push(" AND request_id < ")
            .push_bind(cursor_request_id)
            .push("))");
    }

    qb.push(" ORDER BY created_at DESC, request_id DESC LIMIT ")
        .push_bind(limit + 1);

    let rows = qb.build().fetch_all(&state.db_pool).await.map_err(|e| {
        explorer_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "INDEX_READ_FAILED",
            format!("failed to query run index: {e}"),
            None,
        )
    })?;

    let mut items = rows
        .iter()
        .map(map_summary_row)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| {
            explorer_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "INDEX_READ_FAILED",
                format!("failed to parse run index rows: {e}"),
                None,
            )
        })?;

    let has_next = items.len() as i64 > limit;
    if has_next {
        items.truncate(limit as usize);
    }
    let next_cursor = if has_next {
        items
            .last()
            .map(|i| format!("{}|{}", i.created_at.to_rfc3339(), i.request_id))
    } else {
        None
    };

    Ok(Json(ActivationRunsResponse { items, next_cursor }))
}

pub async fn get_activation_run_summary(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
) -> Result<Json<ActivationRunSummary>, (StatusCode, Json<Value>)> {
    let row = sqlx::query(
        r#"
        SELECT
            request_id,
            created_at,
            model_id,
            prompt_chars,
            output_tokens,
            events_count,
            actions_count,
            activation_rows_count,
            unique_features_count,
            sae_enabled,
            sae_id,
            sae_layer,
            duration_ms,
            status,
            error_message,
            top_features_preview
        FROM activation_run_index
        WHERE request_id = $1
        "#,
    )
    .bind(&request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(|e| {
        explorer_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "INDEX_READ_FAILED",
            format!("failed to query run summary: {e}"),
            None,
        )
    })?;

    let row = row.ok_or_else(|| {
        explorer_error(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("run not found for request_id={request_id}"),
            None,
        )
    })?;

    let summary = map_summary_row(&row).map_err(|e| {
        explorer_error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "INDEX_READ_FAILED",
            format!("failed to parse run summary row: {e}"),
            None,
        )
    })?;
    Ok(Json(summary))
}

pub async fn get_activation_rows(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
    Query(query): Query<ActivationRowsQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let preview = read_run_preview(&state, &request_id)
        .await
        .map_err(|e| {
            explorer_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "DB_READ_FAILED",
                format!("failed to read activation preview: {e}"),
                None,
            )
        })?;

    let preview = preview.ok_or_else(|| {
        explorer_error(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("no activation preview found for request_id={request_id}"),
            None,
        )
    })?;

    let rows = derive_activation_rows(&preview.feature_timeline, &query);
    let row_count = rows.len();

    Ok(Json(json!({
        "request_id": request_id,
        "row_count": row_count,
        "rows": rows,
    })))
}

pub async fn get_feature_deltas(
    Path(_request_id): Path<String>,
    Query(_query): Query<FeatureDeltaQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    Err(explorer_error(
        StatusCode::NOT_IMPLEMENTED,
        "NOT_IMPLEMENTED",
        "Feature deltas are not yet available in staging",
        None,
    ))
}

pub async fn get_top_features(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
    Query(query): Query<TopFeaturesQuery>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let n = clamp_i64(query.n, 50, 1, 500);

    let preview = read_run_preview(&state, &request_id)
        .await
        .map_err(|e| {
            explorer_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "DB_READ_FAILED",
                format!("failed to read run preview: {e}"),
                None,
            )
        })?;

    let preview = preview.ok_or_else(|| {
        explorer_error(
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            format!("run not found for request_id={request_id}"),
            None,
        )
    })?;

    let items = derive_top_features(&preview.feature_timeline, n);

    Ok(Json(json!({
        "request_id": request_id,
        "items": items,
    })))
}

pub async fn post_extract_features(
    State(_state): State<AppState>,
    Json(request): Json<ExtractFeaturesRequest>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    if request.token_ids.is_empty() {
        return Err(explorer_error(
            StatusCode::BAD_REQUEST,
            "INVALID_ARGUMENT",
            "token_ids must be a non-empty array",
            None,
        ));
    }
    if let Some(top_k) = request.top_k {
        if !(1..=200).contains(&top_k) {
            return Err(explorer_error(
                StatusCode::BAD_REQUEST,
                "INVALID_ARGUMENT",
                "top_k must be between 1 and 200",
                None,
            ));
        }
    }

    let feature_timeline = call_hf_extract(
        &request.token_ids,
        request.sae_id.as_deref(),
        request.sae_layer,
        request.top_k,
    )
    .await?;

    Ok(Json(json!({
        "status": "ok",
        "feature_timeline": feature_timeline,
    })))
}

pub async fn activation_health(
    State(state): State<AppState>,
) -> Result<Json<Value>, (StatusCode, Json<Value>)> {
    let client = build_http_client(5)?;

    // Check Postgres reachability
    let index_db_reachable = sqlx::query_scalar::<_, i64>("SELECT 1")
        .fetch_one(&state.db_pool)
        .await
        .is_ok();

    // Check HF inference reachability
    let hf_base_url = std::env::var("PLAYGROUND_ACTIVATIONS_HF_URL").unwrap_or_default();
    let hf_inference_reachable = if hf_base_url.is_empty() {
        false
    } else {
        let resp = client
            .get(format!("{}/health", hf_base_url.trim_end_matches('/')))
            .send()
            .await;
        matches!(resp, Ok(r) if r.status().is_success())
    };

    // Check SAE service reachability
    let sae_base_url = std::env::var("PLAYGROUND_SAE_URL").unwrap_or_default();
    let sae_reachable = if sae_base_url.is_empty() {
        false
    } else {
        let resp = client
            .get(format!("{}/health", sae_base_url.trim_end_matches('/')))
            .send()
            .await;
        matches!(resp, Ok(r) if r.status().is_success())
    };

    // SAE is now inline in HF — status is "ok" when DB + HF are reachable.
    // SAE service reachability is informational only.
    let status = if index_db_reachable && hf_inference_reachable {
        "ok"
    } else {
        "degraded"
    };

    let last_error = if index_db_reachable && hf_inference_reachable {
        None
    } else {
        let mut errors = Vec::new();
        if !index_db_reachable {
            errors.push("index database unreachable");
        }
        if !hf_inference_reachable {
            errors.push("HF inference service unreachable");
        }
        Some(errors.join("; "))
    };

    Ok(Json(json!({
        "status": status,
        "index_db_reachable": index_db_reachable,
        "hf_inference_reachable": hf_inference_reachable,
        "sae_service_reachable": sae_reachable,
        "last_error": last_error
    })))
}

// ---------------------------------------------------------------------------
// Pure helpers — derive activation rows and top features from feature_timeline
// ---------------------------------------------------------------------------

/// Flatten a `feature_timeline` JSONB value into activation rows.
///
/// The timeline is expected to be a JSON array where each entry has:
/// ```json
/// {
///   "position": 0,
///   "token": 259,
///   "token_str": " word",
///   "top_features": [{ "id": 1234, "activation": 2.456 }, ...]
/// }
/// ```
///
/// Each `(position, feature)` pair becomes one row with fields:
/// `{step, token_position, feature_id, activation_value, rank, token_id}`.
///
/// Filters from `ActivationRowsQuery` are applied:
/// - `feature_id`: keep only rows matching this feature
/// - `token_start` / `token_end`: keep only rows in this position range (inclusive)
/// - `rank_max`: keep only rows with rank <= this value (1-based)
/// - `limit`: cap the total number of returned rows
pub fn derive_activation_rows(
    timeline: &Value,
    filters: &ActivationRowsQuery,
) -> Vec<Value> {
    let entries = match timeline.as_array() {
        Some(arr) => arr,
        None => return Vec::new(),
    };

    let limit = filters.limit.unwrap_or(500).max(1) as usize;
    let mut rows: Vec<Value> = Vec::new();

    for entry in entries {
        let position = entry
            .get("position")
            .and_then(Value::as_u64)
            .unwrap_or(0) as i64;
        let token_id = entry
            .get("token")
            .and_then(Value::as_i64)
            .unwrap_or(0);

        // Apply token position range filter
        if let Some(start) = filters.token_start {
            if position < start {
                continue;
            }
        }
        if let Some(end) = filters.token_end {
            if position > end {
                continue;
            }
        }

        let top_features = match entry.get("top_features").and_then(Value::as_array) {
            Some(feats) => feats,
            None => continue,
        };

        for (rank_idx, feat) in top_features.iter().enumerate() {
            let feat_id = feat.get("id").and_then(Value::as_i64).unwrap_or(0);
            let activation = feat.get("activation").and_then(Value::as_f64).unwrap_or(0.0);
            let rank = (rank_idx + 1) as i64; // 1-based rank

            // Apply feature_id filter
            if let Some(filter_fid) = filters.feature_id {
                if feat_id != filter_fid {
                    continue;
                }
            }

            // Apply rank_max filter
            if let Some(rank_max) = filters.rank_max {
                if rank > rank_max {
                    continue;
                }
            }

            rows.push(json!({
                "step": 0,
                "token_position": position,
                "feature_id": feat_id,
                "activation_value": activation,
                "rank": rank,
                "token_id": token_id,
            }));

            if rows.len() >= limit {
                return rows;
            }
        }
    }

    rows
}

/// Aggregate `feature_timeline` into top features sorted by max activation.
///
/// For each unique `feature_id` across all positions, computes:
/// - `max_activation`: the highest activation value seen
/// - `hits`: the number of positions where this feature appears
///
/// Returns the top `n` features sorted by `max_activation` descending, with
/// `hits` as a tiebreaker (descending).
pub fn derive_top_features(timeline: &Value, n: i64) -> Vec<Value> {
    let entries = match timeline.as_array() {
        Some(arr) => arr,
        None => return Vec::new(),
    };

    // feature_id -> (max_activation, hits)
    let mut aggregates: std::collections::HashMap<i64, (f64, i64)> =
        std::collections::HashMap::new();

    for entry in entries {
        let top_features = match entry.get("top_features").and_then(Value::as_array) {
            Some(feats) => feats,
            None => continue,
        };

        for feat in top_features {
            let feat_id = feat.get("id").and_then(Value::as_i64).unwrap_or(0);
            let activation = feat.get("activation").and_then(Value::as_f64).unwrap_or(0.0);

            let entry = aggregates.entry(feat_id).or_insert((0.0, 0));
            if activation > entry.0 {
                entry.0 = activation;
            }
            entry.1 += 1;
        }
    }

    let mut features: Vec<(i64, f64, i64)> = aggregates
        .into_iter()
        .map(|(id, (max_act, hits))| (id, max_act, hits))
        .collect();

    // Sort by max_activation DESC, then hits DESC as tiebreaker
    features.sort_by(|a, b| {
        b.1.partial_cmp(&a.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| b.2.cmp(&a.2))
    });

    let n = n.max(1) as usize;
    features
        .into_iter()
        .take(n)
        .map(|(feature_id, max_activation, hits)| {
            json!({
                "feature_id": feature_id,
                "max_activation": max_activation,
                "hits": hits,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{ActivationRowsQuery, derive_activation_rows, derive_top_features};
    use serde_json::json;

    fn sample_timeline() -> serde_json::Value {
        json!([
            {
                "position": 0,
                "token": 100,
                "token_str": "Hello",
                "top_features": [
                    { "id": 10, "activation": 3.5 },
                    { "id": 20, "activation": 2.1 },
                    { "id": 30, "activation": 1.0 }
                ]
            },
            {
                "position": 1,
                "token": 200,
                "token_str": " world",
                "top_features": [
                    { "id": 10, "activation": 4.0 },
                    { "id": 40, "activation": 2.8 }
                ]
            },
            {
                "position": 2,
                "token": 300,
                "token_str": "!",
                "top_features": [
                    { "id": 20, "activation": 5.0 },
                    { "id": 50, "activation": 0.5 }
                ]
            }
        ])
    }

    fn empty_filters() -> ActivationRowsQuery {
        ActivationRowsQuery {
            feature_id: None,
            sae_layer: None,
            token_start: None,
            token_end: None,
            rank_max: None,
            limit: None,
        }
    }

    // -----------------------------------------------------------------------
    // derive_activation_rows tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_derive_rows_no_filters() {
        let timeline = sample_timeline();
        let rows = derive_activation_rows(&timeline, &empty_filters());
        // 3 + 2 + 2 = 7 rows total
        assert_eq!(rows.len(), 7);

        // First row should be position 0, feature 10, rank 1
        assert_eq!(rows[0]["token_position"], 0);
        assert_eq!(rows[0]["feature_id"], 10);
        assert_eq!(rows[0]["activation_value"], 3.5);
        assert_eq!(rows[0]["rank"], 1);
        assert_eq!(rows[0]["token_id"], 100);
        assert_eq!(rows[0]["step"], 0);
    }

    #[test]
    fn test_derive_rows_filter_feature_id() {
        let timeline = sample_timeline();
        let filters = ActivationRowsQuery {
            feature_id: Some(10),
            ..empty_filters()
        };
        let rows = derive_activation_rows(&timeline, &filters);
        // Feature 10 appears at position 0 and 1
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|r| r["feature_id"] == 10));
    }

    #[test]
    fn test_derive_rows_filter_token_range() {
        let timeline = sample_timeline();
        let filters = ActivationRowsQuery {
            token_start: Some(1),
            token_end: Some(1),
            ..empty_filters()
        };
        let rows = derive_activation_rows(&timeline, &filters);
        // Only position 1: 2 features
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|r| r["token_position"] == 1));
    }

    #[test]
    fn test_derive_rows_filter_rank_max() {
        let timeline = sample_timeline();
        let filters = ActivationRowsQuery {
            rank_max: Some(1),
            ..empty_filters()
        };
        let rows = derive_activation_rows(&timeline, &filters);
        // Only rank 1 from each position: 3 rows
        assert_eq!(rows.len(), 3);
        assert!(rows.iter().all(|r| r["rank"] == 1));
    }

    #[test]
    fn test_derive_rows_limit() {
        let timeline = sample_timeline();
        let filters = ActivationRowsQuery {
            limit: Some(3),
            ..empty_filters()
        };
        let rows = derive_activation_rows(&timeline, &filters);
        assert_eq!(rows.len(), 3);
    }

    #[test]
    fn test_derive_rows_combined_filters() {
        let timeline = sample_timeline();
        let filters = ActivationRowsQuery {
            feature_id: Some(20),
            token_start: Some(0),
            token_end: Some(2),
            rank_max: Some(5),
            limit: Some(10),
            ..empty_filters()
        };
        let rows = derive_activation_rows(&timeline, &filters);
        // Feature 20 at position 0 (rank 2) and position 2 (rank 1)
        assert_eq!(rows.len(), 2);
        assert!(rows.iter().all(|r| r["feature_id"] == 20));
    }

    #[test]
    fn test_derive_rows_empty_timeline() {
        let timeline = json!([]);
        let rows = derive_activation_rows(&timeline, &empty_filters());
        assert!(rows.is_empty());
    }

    #[test]
    fn test_derive_rows_non_array() {
        let timeline = json!(null);
        let rows = derive_activation_rows(&timeline, &empty_filters());
        assert!(rows.is_empty());
    }

    // -----------------------------------------------------------------------
    // derive_top_features tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_top_features_basic() {
        let timeline = sample_timeline();
        let top = derive_top_features(&timeline, 10);
        // 5 unique features: 10, 20, 30, 40, 50
        assert_eq!(top.len(), 5);

        // Sorted by max_activation DESC:
        // feature 20: max=5.0, hits=2
        // feature 10: max=4.0, hits=2
        // feature 40: max=2.8, hits=1
        // feature 30: max=1.0, hits=1
        // feature 50: max=0.5, hits=1
        assert_eq!(top[0]["feature_id"], 20);
        assert_eq!(top[0]["max_activation"], 5.0);
        assert_eq!(top[0]["hits"], 2);

        assert_eq!(top[1]["feature_id"], 10);
        assert_eq!(top[1]["max_activation"], 4.0);
        assert_eq!(top[1]["hits"], 2);

        assert_eq!(top[2]["feature_id"], 40);
        assert_eq!(top[2]["max_activation"], 2.8);
        assert_eq!(top[2]["hits"], 1);
    }

    #[test]
    fn test_top_features_limit_n() {
        let timeline = sample_timeline();
        let top = derive_top_features(&timeline, 2);
        assert_eq!(top.len(), 2);
        // Top 2 by max_activation: feature 20 (5.0), feature 10 (4.0)
        assert_eq!(top[0]["feature_id"], 20);
        assert_eq!(top[1]["feature_id"], 10);
    }

    #[test]
    fn test_top_features_empty_timeline() {
        let timeline = json!([]);
        let top = derive_top_features(&timeline, 10);
        assert!(top.is_empty());
    }

    #[test]
    fn test_top_features_non_array() {
        let timeline = json!(null);
        let top = derive_top_features(&timeline, 10);
        assert!(top.is_empty());
    }

    #[test]
    fn test_top_features_single_entry() {
        let timeline = json!([
            {
                "position": 0,
                "token": 42,
                "token_str": "x",
                "top_features": [
                    { "id": 999, "activation": 7.7 }
                ]
            }
        ]);
        let top = derive_top_features(&timeline, 5);
        assert_eq!(top.len(), 1);
        assert_eq!(top[0]["feature_id"], 999);
        assert_eq!(top[0]["max_activation"], 7.7);
        assert_eq!(top[0]["hits"], 1);
    }

    #[test]
    fn test_top_features_tiebreak_by_hits() {
        // Two features with same max_activation but different hit counts
        let timeline = json!([
            {
                "position": 0,
                "token": 1,
                "token_str": "a",
                "top_features": [
                    { "id": 100, "activation": 3.0 },
                    { "id": 200, "activation": 3.0 }
                ]
            },
            {
                "position": 1,
                "token": 2,
                "token_str": "b",
                "top_features": [
                    { "id": 100, "activation": 2.0 }
                ]
            }
        ]);
        let top = derive_top_features(&timeline, 10);
        assert_eq!(top.len(), 2);
        // Both have max_activation=3.0, but feature 100 has 2 hits vs 1
        assert_eq!(top[0]["feature_id"], 100);
        assert_eq!(top[0]["hits"], 2);
        assert_eq!(top[1]["feature_id"], 200);
        assert_eq!(top[1]["hits"], 1);
    }
}
