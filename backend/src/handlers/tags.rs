//! Handlers for managing request tags.
//!
//! This module provides endpoints for adding and removing tags from a request's
//! tags list.
//!
//! Authentication requirements:
//! - GET: No authentication required for public requests
//! - POST/DELETE: Authentication required

use axum::{
    Json,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
};
use serde::{Deserialize, Serialize};

use crate::utils::{
    ApiError, AppState,
    auth::{AuthenticatedKey, extract_api_key_from_headers, validate_api_key},
};

pub type Result<T> = std::result::Result<T, ApiError>;

/// Request body for updating tags.
#[derive(Debug, Deserialize)]
pub struct UpdateTagRequest {
    /// The tag to add or remove.
    pub tag: String,
}

/// Response after updating tags.
#[derive(Debug, Serialize)]
pub struct UpdateTagResponse {
    /// The request ID that was updated.
    pub request_id: String,
    /// The current list of tags for this request.
    pub tags: Vec<String>,
    /// Description of the action taken.
    pub message: String,
}

/// Response for getting tags.
#[derive(Debug, Serialize)]
pub struct GetTagsResponse {
    /// The request ID.
    pub request_id: String,
    /// The list of tags for this request.
    pub tags: Vec<String>,
}

/// Helper to get authenticated user from headers
async fn get_auth(state: &AppState, headers: &HeaderMap) -> Result<AuthenticatedKey> {
    let api_key = extract_api_key_from_headers(headers)
        .ok_or_else(|| ApiError::unauthorized("Authentication required"))?;

    validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))
}

/// Check if user can view a request (is owner or admin, or request is public)
async fn can_view_request(
    state: &AppState,
    request_id: &str,
    auth: Option<&AuthenticatedKey>,
) -> Result<bool> {
    // Check if request exists and get its visibility
    let row = sqlx::query_as::<_, (Option<String>, bool)>(
        r#"SELECT user_api_key, is_public FROM requests WHERE request_id = $1"#,
    )
    .bind(request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some((user_api_key, is_public)) => {
            // Public requests are viewable by anyone
            if is_public {
                return Ok(true);
            }

            // Check authentication for private requests
            match auth {
                Some(auth) => {
                    if auth.is_admin {
                        return Ok(true);
                    }
                    // Check if user owns this request
                    if let Some(ref allowed_key) = auth.allowed_api_key {
                        if user_api_key.as_ref() == Some(allowed_key) {
                            return Ok(true);
                        }
                    }
                    Ok(false)
                }
                None => Ok(false),
            }
        }
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}

/// Add a tag to a request.
/// Authentication required.
///
/// POST /logs/:request_id/tags
pub async fn add_tag(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<UpdateTagRequest>,
) -> Result<(StatusCode, Json<UpdateTagResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let tag = payload.tag.trim().to_string();

    if tag.is_empty() {
        return Err(ApiError::BadRequest("Tag cannot be empty".into()));
    }

    // Use array_append with a check to ensure no duplicates
    // This atomically adds the tag if not present
    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        UPDATE requests
        SET tags = CASE
            WHEN $2 = ANY(tags) THEN tags
            ELSE array_append(tags, $2)
        END
        WHERE request_id = $1
        RETURNING tags
        "#,
    )
    .bind(&request_id)
    .bind(&tag)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(tags) => {
            // Invalidate cache since the data changed
            state.log_cache.invalidate(&request_id);

            let was_added = tags.contains(&tag);
            let message = if was_added {
                format!("Tag '{}' added", tag)
            } else {
                format!("Tag '{}' already exists", tag)
            };

            Ok((
                StatusCode::OK,
                Json(UpdateTagResponse {
                    request_id,
                    tags,
                    message,
                }),
            ))
        }
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}

/// Remove a tag from a request.
/// Authentication required.
///
/// DELETE /logs/:request_id/tags
pub async fn remove_tag(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<UpdateTagRequest>,
) -> Result<(StatusCode, Json<UpdateTagResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let tag = payload.tag.trim().to_string();

    if tag.is_empty() {
        return Err(ApiError::BadRequest("Tag cannot be empty".into()));
    }

    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        UPDATE requests
        SET tags = array_remove(tags, $2)
        WHERE request_id = $1
        RETURNING tags
        "#,
    )
    .bind(&request_id)
    .bind(&tag)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(tags) => {
            // Invalidate cache since the data changed
            state.log_cache.invalidate(&request_id);

            Ok((
                StatusCode::OK,
                Json(UpdateTagResponse {
                    request_id,
                    tags,
                    message: format!("Tag '{}' removed", tag),
                }),
            ))
        }
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}

/// Get the list of tags for a request.
/// No authentication required for public requests.
///
/// GET /logs/:request_id/tags
pub async fn get_tags(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<GetTagsResponse>> {
    // Try to authenticate (optional)
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    // Check if user can view this request's tags
    if !can_view_request(&state, &request_id, auth.as_ref()).await? {
        return Err(ApiError::forbidden("You don't have access to this request"));
    }

    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        SELECT tags
        FROM requests
        WHERE request_id = $1
        "#,
    )
    .bind(&request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(tags) => Ok(Json(GetTagsResponse { request_id, tags })),
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}
