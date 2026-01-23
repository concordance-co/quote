//! Authentication module for API key validation.
//!
//! This module provides middleware and extractors for authenticating requests
//! using API keys passed in the `X-API-Key` header.

use axum::{
    Json,
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sqlx::{PgPool, Row};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Header name for the API key
pub const API_KEY_HEADER: &str = "X-API-Key";

/// Cache TTL in seconds
const CACHE_TTL_SECS: i64 = 300; // 5 minutes

/// Represents an authenticated API key with its permissions
#[derive(Debug, Clone, Serialize)]
pub struct AuthenticatedKey {
    /// The database ID of the API key
    pub id: i64,
    /// Human-readable name for this key
    pub name: String,
    /// The user_api_key value this key can access (None = admin access to all)
    pub allowed_api_key: Option<String>,
    /// Whether this is an admin key (can see all data)
    pub is_admin: bool,
}

/// Cached API key entry
#[derive(Clone)]
struct CachedKey {
    auth: AuthenticatedKey,
    cached_at: DateTime<Utc>,
}

/// In-memory cache for validated API keys
#[derive(Default)]
pub struct ApiKeyCache {
    cache: RwLock<HashMap<String, CachedKey>>,
}

impl ApiKeyCache {
    pub fn new() -> Self {
        Self {
            cache: RwLock::new(HashMap::new()),
        }
    }

    /// Get a cached key if it exists and hasn't expired
    pub async fn get(&self, key_hash: &str) -> Option<AuthenticatedKey> {
        let cache = self.cache.read().await;
        if let Some(cached) = cache.get(key_hash) {
            let age = Utc::now().signed_duration_since(cached.cached_at);
            if age.num_seconds() < CACHE_TTL_SECS {
                return Some(cached.auth.clone());
            }
        }
        None
    }

    /// Store a key in the cache
    pub async fn set(&self, key_hash: String, auth: AuthenticatedKey) {
        let mut cache = self.cache.write().await;
        cache.insert(
            key_hash,
            CachedKey {
                auth,
                cached_at: Utc::now(),
            },
        );
    }

    /// Remove expired entries from the cache
    pub async fn cleanup(&self) {
        let mut cache = self.cache.write().await;
        let now = Utc::now();
        cache.retain(|_, v| now.signed_duration_since(v.cached_at).num_seconds() < CACHE_TTL_SECS);
    }
}

/// Error type for authentication failures
#[derive(Debug)]
pub enum AuthError {
    /// No API key was provided
    MissingApiKey,
    /// The API key format is invalid
    InvalidFormat,
    /// The API key was not found or is inactive
    InvalidApiKey,
    /// The API key has expired
    ExpiredApiKey,
    /// Database error during validation
    DatabaseError(String),
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AuthError::MissingApiKey => (
                StatusCode::UNAUTHORIZED,
                "Missing API key. Please provide an API key in the X-API-Key header.",
            ),
            AuthError::InvalidFormat => (StatusCode::BAD_REQUEST, "Invalid API key format."),
            AuthError::InvalidApiKey => (StatusCode::UNAUTHORIZED, "Invalid or inactive API key."),
            AuthError::ExpiredApiKey => (StatusCode::UNAUTHORIZED, "API key has expired."),
            AuthError::DatabaseError(_) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                "Authentication service unavailable.",
            ),
        };

        let body = Json(serde_json::json!({
            "error": message,
            "code": status.as_u16()
        }));

        (status, body).into_response()
    }
}

/// Hash an API key using SHA-256
pub fn hash_api_key(key: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(key.as_bytes());
    let result = hasher.finalize();
    hex::encode(result)
}

/// Extract the prefix from an API key (first 8 chars + "...")
pub fn get_key_prefix(key: &str) -> String {
    if key.len() > 8 {
        format!("{}...", &key[..8])
    } else {
        key.to_string()
    }
}

/// Validate an API key against the database.
///
/// This function checks two sources:
/// 1. The `api_keys` table for admin and managed keys
/// 2. The `requests` table for user API keys (inference keys)
///
/// This allows users to authenticate with the same key they use for inference.
pub async fn validate_api_key(
    pool: &PgPool,
    cache: &ApiKeyCache,
    api_key: &str,
) -> Result<AuthenticatedKey, AuthError> {
    let key_hash = hash_api_key(api_key);

    // Check cache first (using the raw key as cache key for user keys)
    if let Some(auth) = cache.get(&key_hash).await {
        return Ok(auth);
    }

    // Also check cache with the raw key (for user_api_key lookups)
    if let Some(auth) = cache.get(api_key).await {
        return Ok(auth);
    }

    // First, try the api_keys table (for admin/managed keys)
    let admin_row = sqlx::query(
        r#"
        SELECT id, name, allowed_api_key, is_admin, expires_at
        FROM api_keys
        WHERE key_hash = $1 AND is_active = TRUE
        "#,
    )
    .bind(&key_hash)
    .fetch_optional(pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    if let Some(row) = admin_row {
        let id: i64 = row
            .try_get("id")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let name: String = row
            .try_get("name")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let allowed_api_key: Option<String> = row
            .try_get("allowed_api_key")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let is_admin: bool = row
            .try_get("is_admin")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let expires_at: Option<DateTime<Utc>> = row
            .try_get("expires_at")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

        // Check expiration
        if let Some(exp) = expires_at {
            if exp < Utc::now() {
                return Err(AuthError::ExpiredApiKey);
            }
        }

        // Update last_used_at (fire and forget)
        let pool_clone = pool.clone();
        let key_hash_clone = key_hash.clone();
        tokio::spawn(async move {
            let _ = sqlx::query("UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = $1")
                .bind(&key_hash_clone)
                .execute(&pool_clone)
                .await;
        });

        let auth = AuthenticatedKey {
            id,
            name,
            is_admin,
            allowed_api_key,
        };

        // Cache the result
        cache.set(key_hash, auth.clone()).await;

        return Ok(auth);
    }

    // Not found by hash, check if the key matches an allowed_api_key in api_keys table
    // This allows users to log in with their inference key and get admin status if configured
    let allowed_key_row = sqlx::query(
        r#"
        SELECT id, name, allowed_api_key, is_admin, expires_at
        FROM api_keys
        WHERE allowed_api_key = $1 AND is_active = TRUE
        "#,
    )
    .bind(api_key)
    .fetch_optional(pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    if let Some(row) = allowed_key_row {
        let id: i64 = row
            .try_get("id")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let name: String = row
            .try_get("name")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let allowed_api_key: Option<String> = row
            .try_get("allowed_api_key")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let is_admin: bool = row
            .try_get("is_admin")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;
        let expires_at: Option<DateTime<Utc>> = row
            .try_get("expires_at")
            .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

        // Check expiration
        if let Some(exp) = expires_at {
            if exp < Utc::now() {
                return Err(AuthError::ExpiredApiKey);
            }
        }

        let auth = AuthenticatedKey {
            id,
            name,
            is_admin,
            allowed_api_key,
        };

        // Cache using the raw key
        cache.set(api_key.to_string(), auth.clone()).await;

        return Ok(auth);
    }

    // Not found in api_keys table at all, check if it's a valid user_api_key in requests
    let user_key_exists = sqlx::query_scalar::<_, bool>(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM requests
            WHERE user_api_key = $1
            LIMIT 1
        )
        "#,
    )
    .bind(api_key)
    .fetch_one(pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    if user_key_exists {
        // Valid user API key - create a non-admin auth with access to their own data
        let auth = AuthenticatedKey {
            id: 0,                         // No ID in api_keys table
            name: get_key_prefix(api_key), // Use key prefix as display name
            is_admin: false,
            allowed_api_key: Some(api_key.to_string()), // Can only access their own data
        };

        // Cache using the raw key
        cache.set(api_key.to_string(), auth.clone()).await;

        return Ok(auth);
    }

    // Key not found anywhere
    Err(AuthError::InvalidApiKey)
}

/// Extract the API key from request headers
pub fn extract_api_key_from_headers(headers: &axum::http::HeaderMap) -> Option<String> {
    headers
        .get(API_KEY_HEADER)
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}

/// Extractor for optional authentication
///
/// This allows handlers to work with or without authentication.
/// Use this when you want to allow public access but provide
/// enhanced features for authenticated users.
#[derive(Debug, Clone)]
pub struct OptionalAuth(pub Option<AuthenticatedKey>);

/// Extractor for required authentication
///
/// This will reject requests without a valid API key.
/// Use this for endpoints that require authentication.
#[derive(Debug, Clone)]
pub struct RequireAuth(pub AuthenticatedKey);

/// State extension that includes the API key cache
#[derive(Clone)]
pub struct AuthState {
    pub pool: PgPool,
    pub cache: Arc<ApiKeyCache>,
}

impl AuthState {
    pub fn new(pool: PgPool) -> Self {
        Self {
            pool,
            cache: Arc::new(ApiKeyCache::new()),
        }
    }
}

/// Response for the /auth/validate endpoint
#[derive(Debug, Serialize, Deserialize)]
pub struct ValidateKeyResponse {
    pub valid: bool,
    pub name: Option<String>,
    pub allowed_api_key: Option<String>,
    pub is_admin: bool,
    pub message: String,
}

/// Validate an API key and return information about it
pub async fn validate_key_handler(
    State(auth_state): State<AuthState>,
    headers: axum::http::HeaderMap,
) -> Result<Json<ValidateKeyResponse>, AuthError> {
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&auth_state.pool, &auth_state.cache, &api_key).await?;

    Ok(Json(ValidateKeyResponse {
        valid: true,
        name: Some(auth.name),
        allowed_api_key: auth.allowed_api_key,
        is_admin: auth.is_admin,
        message: "API key is valid".to_string(),
    }))
}

/// Generate a new API key
///
/// Returns a tuple of (full_key, key_hash, key_prefix)
pub fn generate_api_key() -> (String, String, String) {
    use rand::RngCore;

    let mut random_bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut random_bytes);
    let full_key = format!("ck_{}", hex::encode(random_bytes));
    let key_hash = hash_api_key(&full_key);
    let key_prefix = get_key_prefix(&full_key);

    (full_key, key_hash, key_prefix)
}

/// Request body for creating a new API key
#[derive(Debug, Deserialize)]
pub struct CreateApiKeyRequest {
    /// Human-readable name for this key
    pub name: String,
    /// Description of what this key is used for
    pub description: Option<String>,
    /// The user_api_key value this key can access (None = admin)
    pub allowed_api_key: Option<String>,
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
    pub message: String,
}

/// Create a new API key (admin only)
pub async fn create_api_key_handler(
    State(auth_state): State<AuthState>,
    headers: axum::http::HeaderMap,
    Json(request): Json<CreateApiKeyRequest>,
) -> Result<Json<CreateApiKeyResponse>, AuthError> {
    // Verify the requester is an admin
    let api_key = extract_api_key_from_headers(&headers).ok_or(AuthError::MissingApiKey)?;

    let auth = validate_api_key(&auth_state.pool, &auth_state.cache, &api_key).await?;

    if !auth.is_admin {
        return Err(AuthError::InvalidApiKey); // Reuse error to not leak info
    }

    // Generate new key
    let (full_key, key_hash, key_prefix) = generate_api_key();

    // Insert into database
    sqlx::query(
        r#"
        INSERT INTO api_keys (key_hash, key_prefix, name, description, allowed_api_key, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        "#,
    )
    .bind(&key_hash)
    .bind(&key_prefix)
    .bind(&request.name)
    .bind(&request.description)
    .bind(&request.allowed_api_key)
    .bind(&request.expires_at)
    .execute(&auth_state.pool)
    .await
    .map_err(|e| AuthError::DatabaseError(e.to_string()))?;

    Ok(Json(CreateApiKeyResponse {
        api_key: full_key,
        key_prefix,
        name: request.name,
        allowed_api_key: request.allowed_api_key,
        message: "API key created successfully. Save this key - it won't be shown again!"
            .to_string(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hash_api_key() {
        let key = "test_key_123";
        let hash = hash_api_key(key);

        // SHA-256 produces 64 hex characters
        assert_eq!(hash.len(), 64);

        // Same input produces same hash
        assert_eq!(hash, hash_api_key(key));

        // Different input produces different hash
        assert_ne!(hash, hash_api_key("different_key"));
    }

    #[test]
    fn test_get_key_prefix() {
        assert_eq!(get_key_prefix("abcdefghijklmnop"), "abcdefgh...");
        assert_eq!(get_key_prefix("short"), "short");
        assert_eq!(get_key_prefix("exactly8"), "exactly8");
    }

    #[test]
    fn test_generate_api_key() {
        let (full_key, hash, prefix) = generate_api_key();

        // Key starts with ck_
        assert!(full_key.starts_with("ck_"));

        // Hash is valid SHA-256
        assert_eq!(hash.len(), 64);
        assert_eq!(hash, hash_api_key(&full_key));

        // Prefix matches
        assert!(full_key.starts_with(&prefix.replace("...", "")));
    }
}
