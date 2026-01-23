//! Authentication handlers for API key management.
//!
//! This module provides HTTP handlers for:
//! - Validating API keys
//! - Creating new API keys (admin only)
//! - Listing API keys (admin only)
//! - Revoking API keys (admin only)

use axum::{Json, extract::State, http::StatusCode};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::Row;

use crate::utils::{
    AppState,
    auth::{AuthError, extract_api_key_from_headers, generate_api_key, validate_api_key},
};

/// Response for the /auth/validate endpoint
#[derive(Debug, Serialize)]
pub struct ValidateKeyResponse {
    pub valid: bool,
    pub name: Option<String>,
    pub allowed_api_key: Option<String>,
    pub is_admin: bool,
    pub message: String,
}

/// Validate an API key and return information about it
///
/// GET /auth/validate
/// Headers:
///   X-API-Key: <api_key>
pub async fn validate_key(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<ValidateKeyResponse>, AuthError> {
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    Ok(Json(ValidateKeyResponse {
        valid: true,
        name: Some(auth.name),
        allowed_api_key: auth.allowed_api_key,
        is_admin: auth.is_admin,
        message: "API key is valid".to_string(),
    }))
}

/// Request body for creating a new API key
#[derive(Debug, Deserialize)]
pub struct CreateApiKeyRequest {
    /// Human-readable name for this key
    pub name: String,
    /// Description of what this key is used for
    pub description: Option<String>,
    /// The user_api_key value this key can access (None means no restriction, but not necessarily admin)
    pub allowed_api_key: Option<String>,
    /// Whether this key has admin privileges
    #[serde(default)]
    pub is_admin: bool,
    /// Optional expiration timestamp
    pub expires_at: Option<DateTime<Utc>>,
}

/// Response for creating a new API key
#[derive(Debug, Serialize)]
pub struct CreateApiKeyResponse {
    /// The full API key (only shown once!)
    pub api_key: String,
    /// The key prefix for display
    pub key_prefix: String,
    /// The name of the key
    pub name: String,
    /// The allowed_api_key for this key
    pub allowed_api_key: Option<String>,
    /// Whether this is an admin key
    pub is_admin: bool,
    pub message: String,
}

/// Create a new API key (admin only)
///
/// POST /auth/keys
/// Headers:
///   X-API-Key: <admin_api_key>
/// Body:
///   { "name": "...", "description": "...", "allowed_api_key": "..." }
pub async fn create_api_key(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(request): Json<CreateApiKeyRequest>,
) -> Result<Json<CreateApiKeyResponse>, AuthError> {
    // Verify the requester is an admin
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    if !auth.is_admin {
        return Err(AuthError::InvalidApiKey);
    }

    // Validate request
    if request.name.trim().is_empty() {
        return Err(AuthError::InvalidFormat);
    }

    // Generate new key
    let (full_key, key_hash, key_prefix) = generate_api_key();

    // Insert into database
    sqlx::query(
        r#"
        INSERT INTO api_keys (key_hash, key_prefix, name, description, allowed_api_key, is_admin, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        "#,
    )
    .bind(&key_hash)
    .bind(&key_prefix)
    .bind(request.name.trim())
    .bind(&request.description)
    .bind(&request.allowed_api_key)
    .bind(request.is_admin)
    .bind(&request.expires_at)
    .execute(&state.db_pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    Ok(Json(CreateApiKeyResponse {
        api_key: full_key,
        key_prefix,
        name: request.name,
        allowed_api_key: request.allowed_api_key.clone(),
        is_admin: request.is_admin,
        message: "API key created successfully. Save this key - it won't be shown again!"
            .to_string(),
    }))
}

/// API key info for listing
#[derive(Debug, Serialize)]
pub struct ApiKeyInfo {
    pub id: i64,
    pub key_prefix: String,
    pub name: String,
    pub description: Option<String>,
    pub allowed_api_key: Option<String>,
    pub is_admin: bool,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub last_used_at: Option<DateTime<Utc>>,
    pub expires_at: Option<DateTime<Utc>>,
}

/// Response for listing API keys
#[derive(Debug, Serialize)]
pub struct ListApiKeysResponse {
    pub keys: Vec<ApiKeyInfo>,
    pub total: i64,
}

/// List all API keys (admin only)
///
/// GET /auth/keys
/// Headers:
///   X-API-Key: <admin_api_key>
pub async fn list_api_keys(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<ListApiKeysResponse>, AuthError> {
    // Verify the requester is an admin
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    if !auth.is_admin {
        return Err(AuthError::InvalidApiKey);
    }

    // Fetch all keys (without the hash)
    let rows = sqlx::query(
        r#"
        SELECT
            id, key_prefix, name, description, allowed_api_key, is_admin,
            is_active, created_at, updated_at, last_used_at, expires_at
        FROM api_keys
        ORDER BY created_at DESC
        "#,
    )
    .fetch_all(&state.db_pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    let total = rows.len() as i64;
    let keys: Vec<ApiKeyInfo> = rows
        .into_iter()
        .filter_map(|row| {
            let id: i64 = row.try_get("id").ok()?;
            let key_prefix: String = row.try_get("key_prefix").ok()?;
            let name: String = row.try_get("name").ok()?;
            let description: Option<String> = row.try_get("description").ok()?;
            let allowed_api_key: Option<String> = row.try_get("allowed_api_key").ok()?;
            let is_admin: bool = row.try_get("is_admin").ok()?;
            let is_active: bool = row.try_get("is_active").ok()?;
            let created_at: DateTime<Utc> = row.try_get("created_at").ok()?;
            let updated_at: DateTime<Utc> = row.try_get("updated_at").ok()?;
            let last_used_at: Option<DateTime<Utc>> = row.try_get("last_used_at").ok()?;
            let expires_at: Option<DateTime<Utc>> = row.try_get("expires_at").ok()?;

            Some(ApiKeyInfo {
                id,
                key_prefix,
                name,
                description,
                allowed_api_key,
                is_admin,
                is_active,
                created_at,
                updated_at,
                last_used_at,
                expires_at,
            })
        })
        .collect();

    Ok(Json(ListApiKeysResponse { keys, total }))
}

/// Request body for revoking an API key
#[derive(Debug, Deserialize)]
pub struct RevokeApiKeyRequest {
    /// The ID of the key to revoke
    pub id: i64,
}

/// Response for revoking an API key
#[derive(Debug, Serialize)]
pub struct RevokeApiKeyResponse {
    pub id: i64,
    pub message: String,
}

/// Revoke an API key (admin only)
///
/// DELETE /auth/keys
/// Headers:
///   X-API-Key: <admin_api_key>
/// Body:
///   { "id": 123 }
pub async fn revoke_api_key(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(request): Json<RevokeApiKeyRequest>,
) -> Result<Json<RevokeApiKeyResponse>, AuthError> {
    // Verify the requester is an admin
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    if !auth.is_admin {
        return Err(AuthError::InvalidApiKey);
    }

    // Prevent self-revocation
    if auth.id == request.id {
        return Err(AuthError::InvalidFormat); // Can't revoke your own key
    }

    // Deactivate the key
    let result = sqlx::query(
        r#"
        UPDATE api_keys
        SET is_active = FALSE, updated_at = NOW()
        WHERE id = $1 AND is_active = TRUE
        "#,
    )
    .bind(request.id)
    .execute(&state.db_pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    if result.rows_affected() == 0 {
        return Err(AuthError::InvalidApiKey);
    }

    Ok(Json(RevokeApiKeyResponse {
        id: request.id,
        message: "API key revoked successfully".to_string(),
    }))
}

/// Request body for updating an API key
#[derive(Debug, Deserialize)]
pub struct UpdateApiKeyRequest {
    /// The ID of the key to update
    pub id: i64,
    /// New admin status (optional)
    pub is_admin: Option<bool>,
    /// New name (optional)
    pub name: Option<String>,
    /// New description (optional)
    pub description: Option<String>,
    /// New allowed_api_key (optional, use empty string to clear)
    pub allowed_api_key: Option<String>,
}

/// Response for updating an API key
#[derive(Debug, Serialize)]
pub struct UpdateApiKeyResponse {
    pub id: i64,
    pub message: String,
}

/// Update an API key (admin only)
///
/// PUT /auth/keys
/// Headers:
///   X-API-Key: <admin_api_key>
/// Body:
///   { "id": 123, "is_admin": true }
pub async fn update_api_key(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(request): Json<UpdateApiKeyRequest>,
) -> Result<Json<UpdateApiKeyResponse>, AuthError> {
    // Verify the requester is an admin
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    if !auth.is_admin {
        return Err(AuthError::InvalidApiKey);
    }

    // Build dynamic update query based on provided fields
    let mut updates = vec!["updated_at = NOW()".to_string()];
    let mut param_index = 1;

    if request.is_admin.is_some() {
        param_index += 1;
        updates.push(format!("is_admin = ${}", param_index));
    }
    if request.name.is_some() {
        param_index += 1;
        updates.push(format!("name = ${}", param_index));
    }
    if request.description.is_some() {
        param_index += 1;
        updates.push(format!("description = ${}", param_index));
    }
    if request.allowed_api_key.is_some() {
        param_index += 1;
        updates.push(format!("allowed_api_key = ${}", param_index));
    }

    if updates.len() == 1 {
        // Only updated_at, nothing else to update
        return Ok(Json(UpdateApiKeyResponse {
            id: request.id,
            message: "No fields to update".to_string(),
        }));
    }

    let query = format!(
        "UPDATE api_keys SET {} WHERE id = $1 AND is_active = TRUE",
        updates.join(", ")
    );

    let mut query_builder = sqlx::query(&query).bind(request.id);

    if let Some(is_admin) = request.is_admin {
        query_builder = query_builder.bind(is_admin);
    }
    if let Some(ref name) = request.name {
        query_builder = query_builder.bind(name.trim());
    }
    if let Some(ref description) = request.description {
        query_builder = query_builder.bind(description);
    }
    if let Some(ref allowed_api_key) = request.allowed_api_key {
        // Empty string means NULL (clear the restriction)
        if allowed_api_key.is_empty() {
            query_builder = query_builder.bind(None::<String>);
        } else {
            query_builder = query_builder.bind(Some(allowed_api_key));
        }
    }

    let result = query_builder
        .execute(&state.db_pool)
        .await
        .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    if result.rows_affected() == 0 {
        return Err(AuthError::InvalidApiKey);
    }

    Ok(Json(UpdateApiKeyResponse {
        id: request.id,
        message: "API key updated successfully".to_string(),
    }))
}

/// Bootstrap endpoint to create the first admin key
/// This should only work when there are no existing API keys
///
/// POST /auth/bootstrap
/// Body:
///   { "name": "Admin Key", "secret": "<BOOTSTRAP_SECRET from env>" }
#[derive(Debug, Deserialize)]
pub struct BootstrapRequest {
    pub name: String,
    pub secret: String,
}

#[derive(Debug, Serialize)]
pub struct BootstrapResponse {
    pub api_key: String,
    pub key_prefix: String,
    pub name: String,
    pub message: String,
}

pub async fn bootstrap_admin_key(
    State(state): State<AppState>,
    Json(request): Json<BootstrapRequest>,
) -> Result<Json<BootstrapResponse>, (StatusCode, Json<serde_json::Value>)> {
    // Check the bootstrap secret from environment
    let bootstrap_secret = std::env::var("BOOTSTRAP_SECRET").unwrap_or_default();

    if bootstrap_secret.is_empty() {
        return Err((
            StatusCode::FORBIDDEN,
            Json(serde_json::json!({
                "error": "Bootstrap is disabled. Set BOOTSTRAP_SECRET environment variable.",
                "code": 403
            })),
        ));
    }

    if request.secret != bootstrap_secret {
        return Err((
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": "Invalid bootstrap secret",
                "code": 401
            })),
        ));
    }

    // Check if any keys exist
    let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM api_keys")
        .fetch_one(&state.db_pool)
        .await
        .map_err(|e| {
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": format!("Database error: {}", e),
                    "code": 500
                })),
            )
        })?;

    if count.0 > 0 {
        return Err((
            StatusCode::CONFLICT,
            Json(serde_json::json!({
                "error": "API keys already exist. Bootstrap is only available for initial setup.",
                "code": 409
            })),
        ));
    }

    // Generate admin key
    let (full_key, key_hash, key_prefix) = generate_api_key();

    // Insert admin key with is_admin = TRUE
    sqlx::query(
        r#"
        INSERT INTO api_keys (key_hash, key_prefix, name, description, allowed_api_key, is_admin)
        VALUES ($1, $2, $3, $4, NULL, TRUE)
        "#,
    )
    .bind(&key_hash)
    .bind(&key_prefix)
    .bind(request.name.trim())
    .bind("Bootstrap admin key")
    .execute(&state.db_pool)
    .await
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({
                "error": format!("Failed to create key: {}", e),
                "code": 500
            })),
        )
    })?;

    Ok(Json(BootstrapResponse {
        api_key: full_key,
        key_prefix,
        name: request.name,
        message: "Admin API key created successfully. Save this key - it won't be shown again!"
            .to_string(),
    }))
}

/// Get current user info based on API key
///
/// GET /auth/me
/// Headers:
///   X-API-Key: <api_key>
#[derive(Debug, Serialize)]
pub struct CurrentUserResponse {
    pub name: String,
    pub allowed_api_key: Option<String>,
    pub is_admin: bool,
}

pub async fn get_current_user(
    State(state): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<CurrentUserResponse>, AuthError> {
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&state.auth.pool, &state.auth.cache, &api_key).await?;

    Ok(Json(CurrentUserResponse {
        name: auth.name,
        allowed_api_key: auth.allowed_api_key,
        is_admin: auth.is_admin,
    }))
}
