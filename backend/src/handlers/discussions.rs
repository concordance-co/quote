//! Handlers for managing discussions (comments) on requests.
//!
//! This module provides endpoints for creating, reading, updating, and deleting
//! comments on inference requests.
//!
//! Authentication requirements:
//! - GET (list/get): No authentication required for public requests
//! - POST/PUT/DELETE: Authentication required

use axum::{
    Json,
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::utils::{
    ApiError, AppState,
    auth::{AuthenticatedKey, extract_api_key_from_headers, validate_api_key},
};

pub type Result<T> = std::result::Result<T, ApiError>;

/// A single discussion/comment.
#[derive(Debug, Clone, Serialize)]
pub struct Discussion {
    pub id: i64,
    pub request_id: String,
    pub username: String,
    pub comment: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Request body for creating a new comment.
#[derive(Debug, Deserialize)]
pub struct CreateDiscussionRequest {
    /// The username of the person posting the comment.
    pub username: String,
    /// The comment text.
    pub comment: String,
}

/// Request body for updating an existing comment.
#[derive(Debug, Deserialize)]
pub struct UpdateDiscussionRequest {
    /// The updated comment text.
    pub comment: String,
}

/// Query parameters for listing discussions.
#[derive(Debug, Default, Deserialize)]
pub struct ListDiscussionsParams {
    /// Maximum number of discussions to return (default: 50, max: 100).
    pub limit: Option<i64>,
    /// Offset for pagination (default: 0).
    pub offset: Option<i64>,
}

/// Response for listing discussions.
#[derive(Debug, Serialize)]
pub struct ListDiscussionsResponse {
    pub request_id: String,
    pub discussions: Vec<Discussion>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

/// Response after creating a discussion.
#[derive(Debug, Serialize)]
pub struct CreateDiscussionResponse {
    pub discussion: Discussion,
    pub message: String,
}

/// Response after updating a discussion.
#[derive(Debug, Serialize)]
pub struct UpdateDiscussionResponse {
    pub discussion: Discussion,
    pub message: String,
}

/// Response after deleting a discussion.
#[derive(Debug, Serialize)]
pub struct DeleteDiscussionResponse {
    pub id: i64,
    pub message: String,
}

const DEFAULT_LIMIT: i64 = 50;
const MAX_LIMIT: i64 = 100;

/// Helper to get authenticated user from headers
async fn get_auth(state: &AppState, headers: &HeaderMap) -> Result<AuthenticatedKey> {
    let api_key = extract_api_key_from_headers(headers)
        .ok_or_else(|| ApiError::unauthorized("Authentication required"))?;

    validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))
}

/// Check if user can access a request (is owner or admin, or request is public)
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

/// List all discussions for a request.
/// No authentication required for public requests.
///
/// GET /logs/:request_id/discussions
pub async fn list_discussions(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Query(params): Query<ListDiscussionsParams>,
) -> Result<Json<ListDiscussionsResponse>> {
    let limit = params.limit.unwrap_or(DEFAULT_LIMIT).clamp(1, MAX_LIMIT);
    let offset = params.offset.unwrap_or(0).max(0);

    // Try to authenticate (optional)
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    // Check if user can view this request's discussions
    if !can_view_request(&state, &request_id, auth.as_ref()).await? {
        return Err(ApiError::forbidden("You don't have access to this request"));
    }

    // Get total count
    let total =
        sqlx::query_scalar::<_, i64>(r#"SELECT COUNT(*) FROM discussions WHERE request_id = $1"#)
            .bind(&request_id)
            .fetch_one(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    // Get discussions
    let rows = sqlx::query_as::<_, (i64, String, String, String, DateTime<Utc>, DateTime<Utc>)>(
        r#"
        SELECT id, request_id, username, comment, created_at, updated_at
        FROM discussions
        WHERE request_id = $1
        ORDER BY created_at ASC
        LIMIT $2 OFFSET $3
        "#,
    )
    .bind(&request_id)
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let discussions: Vec<Discussion> = rows
        .into_iter()
        .map(
            |(id, request_id, username, comment, created_at, updated_at)| Discussion {
                id,
                request_id,
                username,
                comment,
                created_at,
                updated_at,
            },
        )
        .collect();

    Ok(Json(ListDiscussionsResponse {
        request_id,
        discussions,
        total,
        limit,
        offset,
    }))
}

/// Create a new discussion/comment on a request.
/// Authentication required.
///
/// POST /logs/:request_id/discussions
pub async fn create_discussion(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<CreateDiscussionRequest>,
) -> Result<(StatusCode, Json<CreateDiscussionResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let username = payload.username.trim().to_string();
    let comment = payload.comment.trim().to_string();

    if username.is_empty() {
        return Err(ApiError::BadRequest("Username cannot be empty".into()));
    }

    if comment.is_empty() {
        return Err(ApiError::BadRequest("Comment cannot be empty".into()));
    }

    // First verify the request exists
    let request_exists = sqlx::query_scalar::<_, bool>(
        r#"SELECT EXISTS(SELECT 1 FROM requests WHERE request_id = $1)"#,
    )
    .bind(&request_id)
    .fetch_one(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    if !request_exists {
        return Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        )));
    }

    // Insert the discussion
    let row = sqlx::query_as::<_, (i64, DateTime<Utc>, DateTime<Utc>)>(
        r#"
        INSERT INTO discussions (request_id, username, comment)
        VALUES ($1, $2, $3)
        RETURNING id, created_at, updated_at
        "#,
    )
    .bind(&request_id)
    .bind(&username)
    .bind(&comment)
    .fetch_one(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    // Invalidate discussions cache
    state.invalidate_discussions_cache(&request_id);

    let discussion = Discussion {
        id: row.0,
        request_id,
        username,
        comment,
        created_at: row.1,
        updated_at: row.2,
    };

    Ok((
        StatusCode::CREATED,
        Json(CreateDiscussionResponse {
            discussion,
            message: "Comment created successfully".to_string(),
        }),
    ))
}

/// Update an existing discussion/comment.
/// Authentication required.
///
/// PUT /logs/:request_id/discussions/:discussion_id
pub async fn update_discussion(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path((request_id, discussion_id)): Path<(String, i64)>,
    Json(payload): Json<UpdateDiscussionRequest>,
) -> Result<(StatusCode, Json<UpdateDiscussionResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let comment = payload.comment.trim().to_string();

    if comment.is_empty() {
        return Err(ApiError::BadRequest("Comment cannot be empty".into()));
    }

    let row = sqlx::query_as::<_, (i64, String, String, String, DateTime<Utc>, DateTime<Utc>)>(
        r#"
        UPDATE discussions
        SET comment = $3, updated_at = NOW()
        WHERE request_id = $1 AND id = $2
        RETURNING id, request_id, username, comment, created_at, updated_at
        "#,
    )
    .bind(&request_id)
    .bind(discussion_id)
    .bind(&comment)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some((id, req_id, username, comment, created_at, updated_at)) => {
            // Invalidate discussions cache
            state.invalidate_discussions_cache(&request_id);

            let discussion = Discussion {
                id,
                request_id: req_id,
                username,
                comment,
                created_at,
                updated_at,
            };

            Ok((
                StatusCode::OK,
                Json(UpdateDiscussionResponse {
                    discussion,
                    message: "Comment updated successfully".to_string(),
                }),
            ))
        }
        None => Err(ApiError::NotFound(format!(
            "Discussion {} not found for request '{}'",
            discussion_id, request_id
        ))),
    }
}

/// Delete a discussion/comment.
/// Authentication required.
///
/// DELETE /logs/:request_id/discussions/:discussion_id
pub async fn delete_discussion(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path((request_id, discussion_id)): Path<(String, i64)>,
) -> Result<(StatusCode, Json<DeleteDiscussionResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let row = sqlx::query_scalar::<_, i64>(
        r#"
        DELETE FROM discussions
        WHERE request_id = $1 AND id = $2
        RETURNING id
        "#,
    )
    .bind(&request_id)
    .bind(discussion_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(id) => {
            // Invalidate discussions cache
            state.invalidate_discussions_cache(&request_id);

            Ok((
                StatusCode::OK,
                Json(DeleteDiscussionResponse {
                    id,
                    message: "Comment deleted successfully".to_string(),
                }),
            ))
        }
        None => Err(ApiError::NotFound(format!(
            "Discussion {} not found for request '{}'",
            discussion_id, request_id
        ))),
    }
}

/// Get a single discussion by ID.
/// No authentication required for public requests.
///
/// GET /logs/:request_id/discussions/:discussion_id
pub async fn get_discussion(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path((request_id, discussion_id)): Path<(String, i64)>,
) -> Result<Json<Discussion>> {
    // Try to authenticate (optional)
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    // Check if user can view this request's discussions
    if !can_view_request(&state, &request_id, auth.as_ref()).await? {
        return Err(ApiError::forbidden("You don't have access to this request"));
    }

    let row = sqlx::query_as::<_, (i64, String, String, String, DateTime<Utc>, DateTime<Utc>)>(
        r#"
        SELECT id, request_id, username, comment, created_at, updated_at
        FROM discussions
        WHERE request_id = $1 AND id = $2
        "#,
    )
    .bind(&request_id)
    .bind(discussion_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some((id, request_id, username, comment, created_at, updated_at)) => Ok(Json(Discussion {
            id,
            request_id,
            username,
            comment,
            created_at,
            updated_at,
        })),
        None => Err(ApiError::NotFound(format!(
            "Discussion {} not found for request '{}'",
            discussion_id, request_id
        ))),
    }
}
