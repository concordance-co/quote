//! Handlers for managing request favorites.
//!
//! This module provides endpoints for adding and removing users from a request's
//! favorited_by list.
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

/// Request body for updating favorites.
#[derive(Debug, Deserialize)]
pub struct UpdateFavoriteRequest {
    /// The name of the user to add or remove.
    pub name: String,
}

/// Response after updating favorites.
#[derive(Debug, Serialize)]
pub struct UpdateFavoriteResponse {
    /// The request ID that was updated.
    pub request_id: String,
    /// The current list of users who have favorited this request.
    pub favorited_by: Vec<String>,
    /// Description of the action taken.
    pub message: String,
}

/// Response for getting favorites.
#[derive(Debug, Serialize)]
pub struct GetFavoritesResponse {
    /// The request ID.
    pub request_id: String,
    /// The list of users who have favorited this request.
    pub favorited_by: Vec<String>,
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

/// Add a user to the favorited_by list for a request.
/// Authentication required.
///
/// POST /logs/:request_id/favorite
pub async fn add_favorite(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<UpdateFavoriteRequest>,
) -> Result<(StatusCode, Json<UpdateFavoriteResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let name = payload.name.trim().to_string();

    if name.is_empty() {
        return Err(ApiError::BadRequest("Name cannot be empty".into()));
    }

    // Use array_append with array_remove to ensure no duplicates
    // This atomically adds the name if not present
    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        UPDATE requests
        SET favorited_by = CASE
            WHEN $2 = ANY(favorited_by) THEN favorited_by
            ELSE array_append(favorited_by, $2)
        END
        WHERE request_id = $1
        RETURNING favorited_by
        "#,
    )
    .bind(&request_id)
    .bind(&name)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(favorited_by) => {
            // Invalidate cache since the data changed
            state.log_cache.invalidate(&request_id);

            let was_added = favorited_by.contains(&name);
            let message = if was_added {
                format!("'{}' added to favorites", name)
            } else {
                format!("'{}' was already in favorites", name)
            };

            Ok((
                StatusCode::OK,
                Json(UpdateFavoriteResponse {
                    request_id,
                    favorited_by,
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

/// Remove a user from the favorited_by list for a request.
/// Authentication required.
///
/// DELETE /logs/:request_id/favorite
pub async fn remove_favorite(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<UpdateFavoriteRequest>,
) -> Result<(StatusCode, Json<UpdateFavoriteResponse>)> {
    // Require authentication
    let _auth = get_auth(&state, &headers).await?;

    let name = payload.name.trim().to_string();

    if name.is_empty() {
        return Err(ApiError::BadRequest("Name cannot be empty".into()));
    }

    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        UPDATE requests
        SET favorited_by = array_remove(favorited_by, $2)
        WHERE request_id = $1
        RETURNING favorited_by
        "#,
    )
    .bind(&request_id)
    .bind(&name)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(favorited_by) => {
            // Invalidate cache since the data changed
            state.log_cache.invalidate(&request_id);

            Ok((
                StatusCode::OK,
                Json(UpdateFavoriteResponse {
                    request_id,
                    favorited_by,
                    message: format!("'{}' removed from favorites", name),
                }),
            ))
        }
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}

/// Get the list of users who have favorited a request.
/// No authentication required for public requests.
///
/// GET /logs/:request_id/favorite
pub async fn get_favorites(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<GetFavoritesResponse>> {
    // Try to authenticate (optional)
    let auth: Option<AuthenticatedKey> =
        if let Some(api_key) = extract_api_key_from_headers(&headers) {
            validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
                .await
                .ok()
        } else {
            None
        };

    // Check if user can view this request's favorites
    if !can_view_request(&state, &request_id, auth.as_ref()).await? {
        return Err(ApiError::forbidden("You don't have access to this request"));
    }

    let row = sqlx::query_scalar::<_, Vec<String>>(
        r#"
        SELECT favorited_by
        FROM requests
        WHERE request_id = $1
        "#,
    )
    .bind(&request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    match row {
        Some(favorited_by) => Ok(Json(GetFavoritesResponse {
            request_id,
            favorited_by,
        })),
        None => Err(ApiError::NotFound(format!(
            "Request '{}' not found",
            request_id
        ))),
    }
}
