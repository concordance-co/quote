//! Handlers for managing collections of requests.
//!
//! This module provides endpoints for creating, listing, updating, and deleting
//! collections, as well as adding/removing requests from collections.
//!
//! Collections are owned by users and only visible to their owner or admins.

use axum::{
    Json,
    extract::{Path, Query, State},
    http::{HeaderMap, StatusCode},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;

use crate::utils::{
    ApiError, AppState,
    auth::{AuthenticatedKey, extract_api_key_from_headers, validate_api_key},
};

pub type Result<T> = std::result::Result<T, ApiError>;

// ============================================================================
// Data Types
// ============================================================================

/// A collection of requests.
#[derive(Debug, Serialize, FromRow)]
pub struct Collection {
    pub id: i64,
    pub name: String,
    pub description: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub created_by: Option<String>,
    pub is_public: bool,
    pub public_token: Option<String>,
}

/// Collection with request count for list views.
#[derive(Debug, Serialize, FromRow)]
pub struct CollectionSummary {
    pub id: i64,
    pub name: String,
    pub description: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub created_by: Option<String>,
    pub request_count: Option<i64>,
    pub is_public: bool,
    pub public_token: Option<String>,
}

/// A request in a collection with metadata about when it was added.
#[derive(Debug, Serialize, Deserialize, FromRow)]
pub struct CollectionRequest {
    pub request_id: String,
    pub added_at: DateTime<Utc>,
    pub added_by: Option<String>,
    pub notes: Option<String>,
    // Request summary fields
    pub created_ts: DateTime<Utc>,
    pub finished_ts: Option<DateTime<Utc>>,
    pub model_id: Option<String>,
    pub final_text: Option<String>,
}

// ============================================================================
// Request/Response Types
// ============================================================================

/// Request body for creating a collection.
#[derive(Debug, Deserialize)]
pub struct CreateCollectionRequest {
    pub name: String,
    pub description: Option<String>,
    pub created_by: Option<String>,
}

/// Response after creating a collection.
#[derive(Debug, Serialize)]
pub struct CreateCollectionResponse {
    pub collection: Collection,
    pub message: String,
}

/// Request body for updating a collection.
#[derive(Debug, Deserialize)]
pub struct UpdateCollectionRequest {
    pub name: Option<String>,
    pub description: Option<String>,
}

/// Response after updating a collection.
#[derive(Debug, Serialize)]
pub struct UpdateCollectionResponse {
    pub collection: Collection,
    pub message: String,
}

/// Response after deleting a collection.
#[derive(Debug, Serialize)]
pub struct DeleteCollectionResponse {
    pub id: i64,
    pub message: String,
}

/// Query parameters for listing collections.
#[derive(Debug, Deserialize)]
pub struct ListCollectionsQuery {
    #[serde(default = "default_limit")]
    pub limit: i64,
    #[serde(default)]
    pub offset: i64,
}

fn default_limit() -> i64 {
    50
}

/// Response for listing collections.
#[derive(Debug, Serialize)]
pub struct ListCollectionsResponse {
    pub collections: Vec<CollectionSummary>,
    pub total: i64,
    pub limit: i64,
    pub offset: i64,
}

/// Response for getting a single collection with its requests.
#[derive(Debug, Serialize)]
pub struct GetCollectionResponse {
    pub collection: Collection,
    pub requests: Vec<CollectionRequest>,
    pub total_requests: i64,
}

/// Request body for adding a request to a collection.
#[derive(Debug, Deserialize)]
pub struct AddRequestToCollectionRequest {
    pub request_id: String,
    pub added_by: Option<String>,
    pub notes: Option<String>,
}

/// Response after adding a request to a collection.
#[derive(Debug, Serialize)]
pub struct AddRequestToCollectionResponse {
    pub collection_id: i64,
    pub request_id: String,
    pub message: String,
}

/// Request body for removing a request from a collection.
#[derive(Debug, Deserialize)]
pub struct RemoveRequestFromCollectionRequest {
    pub request_id: String,
}

/// Response after removing a request from a collection.
#[derive(Debug, Serialize)]
pub struct RemoveRequestFromCollectionResponse {
    pub collection_id: i64,
    pub request_id: String,
    pub message: String,
}

/// Response for getting collections that contain a specific request.
#[derive(Debug, Serialize)]
pub struct RequestCollectionsResponse {
    pub request_id: String,
    pub collections: Vec<CollectionSummary>,
}

// ============================================================================
// Handlers
// ============================================================================

/// Helper to get authenticated user from headers
async fn get_auth(state: &AppState, headers: &HeaderMap) -> Result<AuthenticatedKey> {
    let api_key = extract_api_key_from_headers(headers)
        .ok_or_else(|| ApiError::unauthorized("Authentication required"))?;

    validate_api_key(&state.auth.pool, &state.auth.cache, &api_key)
        .await
        .map_err(|_| ApiError::unauthorized("Invalid API key"))
}

/// Generate a secure random token for public collection URLs
fn generate_public_token() -> String {
    use rand::RngCore;
    let mut bytes = [0u8; 32];
    rand::thread_rng().fill_bytes(&mut bytes);
    hex::encode(bytes)
}

/// Check if user can access a collection (is owner or admin)
fn can_access_collection(auth: &AuthenticatedKey, collection_created_by: Option<&str>) -> bool {
    if auth.is_admin {
        return true;
    }
    // Non-admins can only access collections they created
    match (collection_created_by, &auth.allowed_api_key) {
        (Some(created_by), Some(allowed_key)) => created_by == allowed_key,
        (Some(created_by), None) => created_by == auth.name,
        _ => false,
    }
}

/// Get the owner identifier for the current user
fn get_owner_id(auth: &AuthenticatedKey) -> String {
    auth.allowed_api_key
        .clone()
        .unwrap_or_else(|| auth.name.clone())
}

/// Create a new collection.
///
/// POST /collections
pub async fn create_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(payload): Json<CreateCollectionRequest>,
) -> Result<(StatusCode, Json<CreateCollectionResponse>)> {
    let auth = get_auth(&state, &headers).await?;

    let name = payload.name.trim().to_string();

    if name.is_empty() {
        return Err(ApiError::BadRequest(
            "Collection name cannot be empty".into(),
        ));
    }

    if name.len() > 255 {
        return Err(ApiError::BadRequest(
            "Collection name cannot exceed 255 characters".into(),
        ));
    }

    // Use provided created_by or default to the authenticated user's identifier
    let created_by = payload
        .created_by
        .clone()
        .unwrap_or_else(|| get_owner_id(&auth));

    let collection = sqlx::query_as::<_, Collection>(
        r#"
        INSERT INTO collections (name, description, created_by)
        VALUES ($1, $2, $3)
        RETURNING id, name, description, created_at, updated_at, created_by, is_public, public_token
        "#,
    )
    .bind(&name)
    .bind(&payload.description)
    .bind(&created_by)
    .fetch_one(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    Ok((
        StatusCode::CREATED,
        Json(CreateCollectionResponse {
            collection,
            message: format!("Collection '{}' created", name),
        }),
    ))
}

/// List all collections with request counts.
/// Admins see all collections, non-admins only see their own.
///
/// GET /collections
pub async fn list_collections(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(query): Query<ListCollectionsQuery>,
) -> Result<Json<ListCollectionsResponse>> {
    let auth = get_auth(&state, &headers).await?;

    let limit = query.limit.clamp(1, 100);
    let offset = query.offset.max(0);

    let (collections, total) = if auth.is_admin {
        // Admins see all collections
        let collections = sqlx::query_as::<_, CollectionSummary>(
            r#"
            SELECT
                c.id,
                c.name,
                c.description,
                c.created_at,
                c.updated_at,
                c.created_by,
                COUNT(cr.id)::bigint as request_count,
                c.is_public,
                c.public_token
            FROM collections c
            LEFT JOIN collection_requests cr ON c.id = cr.collection_id
            GROUP BY c.id, c.name, c.description, c.created_at, c.updated_at, c.created_by
            ORDER BY c.updated_at DESC
            LIMIT $1 OFFSET $2
            "#,
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

        let total = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM collections")
            .fetch_one(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

        (collections, total)
    } else {
        // Non-admins only see collections they created
        let owner_id = get_owner_id(&auth);

        let collections = sqlx::query_as::<_, CollectionSummary>(
            r#"
            SELECT
                c.id,
                c.name,
                c.description,
                c.created_at,
                c.updated_at,
                c.created_by,
                COUNT(cr.id)::bigint as request_count,
                c.is_public,
                c.public_token
            FROM collections c
            LEFT JOIN collection_requests cr ON c.id = cr.collection_id
            WHERE c.created_by = $3
            GROUP BY c.id, c.name, c.description, c.created_at, c.updated_at, c.created_by
            ORDER BY c.updated_at DESC
            LIMIT $1 OFFSET $2
            "#,
        )
        .bind(limit)
        .bind(offset)
        .bind(&owner_id)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

        let total =
            sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM collections WHERE created_by = $1")
                .bind(&owner_id)
                .fetch_one(&state.db_pool)
                .await
                .map_err(ApiError::from)?;

        (collections, total)
    };

    Ok(Json(ListCollectionsResponse {
        collections,
        total,
        limit,
        offset,
    }))
}

/// Get a single collection with its requests.
/// Only accessible by owner or admin.
///
/// GET /collections/:collection_id
pub async fn get_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
    Query(query): Query<ListCollectionsQuery>,
) -> Result<Json<GetCollectionResponse>> {
    let auth = get_auth(&state, &headers).await?;

    let limit = query.limit.clamp(1, 100);
    let offset = query.offset.max(0);

    // First check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }

    // Get the collection
    let collection = sqlx::query_as::<_, Collection>(
        r#"
        SELECT id, name, description, created_at, updated_at, created_by
        FROM collections
        WHERE id = $1
        "#,
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?
    .ok_or_else(|| ApiError::NotFound(format!("Collection '{}' not found", collection_id)))?;

    // Get the requests in this collection
    let requests = sqlx::query_as::<_, CollectionRequest>(
        r#"
        SELECT
            cr.request_id,
            cr.added_at,
            cr.added_by,
            cr.notes,
            r.created_at as created_ts,
            r.completed_at as finished_ts,
            r.model as model_id,
            (
                SELECT SUBSTRING(
                    string_agg(
                        COALESCE(e.token_text, ''),
                        '' ORDER BY e.step, e.sequence_order
                    ),
                    1, 500
                )
                FROM events e
                WHERE e.request_id = r.request_id
                AND e.event_type = 'Sampled'
            ) as final_text
        FROM collection_requests cr
        JOIN requests r ON cr.request_id = r.request_id
        WHERE cr.collection_id = $1
        ORDER BY cr.added_at DESC
        LIMIT $2 OFFSET $3
        "#,
    )
    .bind(collection_id)
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    // Get total count
    let total_requests = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM collection_requests WHERE collection_id = $1",
    )
    .bind(collection_id)
    .fetch_one(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    Ok(Json(GetCollectionResponse {
        collection,
        requests,
        total_requests,
    }))
}

/// Update a collection.
/// Update a collection's name and/or description.
/// Only accessible by owner or admin.
///
/// PUT /collections/:collection_id
pub async fn update_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
    Json(payload): Json<UpdateCollectionRequest>,
) -> Result<Json<UpdateCollectionResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    // Check if at least one field is being updated
    if payload.name.is_none() && payload.description.is_none() {
        return Err(ApiError::BadRequest(
            "At least one field (name or description) must be provided".into(),
        ));
    }

    // Validate name if provided
    if let Some(ref name) = payload.name {
        let name = name.trim();
        if name.is_empty() {
            return Err(ApiError::BadRequest(
                "Collection name cannot be empty".into(),
            ));
        }
        if name.len() > 255 {
            return Err(ApiError::BadRequest(
                "Collection name cannot exceed 255 characters".into(),
            ));
        }
    }

    // Build dynamic update query
    let collection = if let Some(ref name) = payload.name {
        if let Some(ref description) = payload.description {
            sqlx::query_as::<_, Collection>(
                r#"
                UPDATE collections
                SET name = $2, description = $3
                WHERE id = $1
                RETURNING id, name, description, created_at, updated_at, created_by
                "#,
            )
            .bind(collection_id)
            .bind(name.trim())
            .bind(description)
            .fetch_optional(&state.db_pool)
            .await
        } else {
            sqlx::query_as::<_, Collection>(
                r#"
                UPDATE collections
                SET name = $2
                WHERE id = $1
                RETURNING id, name, description, created_at, updated_at, created_by
                "#,
            )
            .bind(collection_id)
            .bind(name.trim())
            .fetch_optional(&state.db_pool)
            .await
        }
    } else {
        sqlx::query_as::<_, Collection>(
            r#"
            UPDATE collections
            SET description = $2
            WHERE id = $1
            RETURNING id, name, description, created_at, updated_at, created_by
            "#,
        )
        .bind(collection_id)
        .bind(&payload.description)
        .fetch_optional(&state.db_pool)
        .await
    }
    .map_err(ApiError::from)?
    .ok_or_else(|| ApiError::NotFound(format!("Collection '{}' not found", collection_id)))?;

    // Invalidate collection caches
    state.invalidate_collection_caches(collection_id);
    if let Some(ref token) = collection_meta.public_token {
        state.invalidate_public_collection_cache(token);
    }

    Ok(Json(UpdateCollectionResponse {
        message: format!("Collection '{}' updated", collection.name),
        collection,
    }))
}

/// Delete a collection.
/// Only accessible by owner or admin.
///
/// DELETE /collections/:collection_id
pub async fn delete_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
) -> Result<Json<DeleteCollectionResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    let result = sqlx::query("DELETE FROM collections WHERE id = $1")
        .bind(collection_id)
        .execute(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

    if result.rows_affected() == 0 {
        return Err(ApiError::NotFound(format!(
            "Collection '{}' not found",
            collection_id
        )));
    }

    // Invalidate collection caches
    state.invalidate_collection_caches(collection_id);
    if let Some(ref token) = collection_meta.public_token {
        state.invalidate_public_collection_cache(token);
    }

    Ok(Json(DeleteCollectionResponse {
        id: collection_id,
        message: "Collection deleted".into(),
    }))
}

/// Add a request to a collection.
/// Only accessible by owner or admin.
///
/// POST /collections/:collection_id/requests
pub async fn add_request_to_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
    Json(payload): Json<AddRequestToCollectionRequest>,
) -> Result<(StatusCode, Json<AddRequestToCollectionResponse>)> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    let request_id = payload.request_id.trim().to_string();

    if request_id.is_empty() {
        return Err(ApiError::BadRequest("Request ID cannot be empty".into()));
    }

    // Check if the collection exists
    let collection_exists =
        sqlx::query_scalar::<_, bool>("SELECT EXISTS(SELECT 1 FROM collections WHERE id = $1)")
            .bind(collection_id)
            .fetch_one(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    if !collection_exists {
        return Err(ApiError::NotFound(format!(
            "Collection '{}' not found",
            collection_id
        )));
    }

    // Check if the request exists
    let request_exists = sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM requests WHERE request_id = $1)",
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

    // Try to insert, handle duplicate gracefully
    let result = sqlx::query(
        r#"
        INSERT INTO collection_requests (collection_id, request_id, added_by, notes)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (collection_id, request_id) DO NOTHING
        "#,
    )
    .bind(collection_id)
    .bind(&request_id)
    .bind(&payload.added_by)
    .bind(&payload.notes)
    .execute(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let message = if result.rows_affected() > 0 {
        // Invalidate collection caches when request is added
        state.invalidate_collection_caches(collection_id);
        if let Some(ref token) = collection_meta.public_token {
            state.invalidate_public_collection_cache(token);
        }
        "Request added to collection"
    } else {
        "Request already in collection"
    };

    Ok((
        StatusCode::OK,
        Json(AddRequestToCollectionResponse {
            collection_id,
            request_id,
            message: message.into(),
        }),
    ))
}

/// Remove a request from a collection.
/// Only accessible by owner or admin.
///
/// DELETE /collections/:collection_id/requests
pub async fn remove_request_from_collection(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
    Json(payload): Json<RemoveRequestFromCollectionRequest>,
) -> Result<Json<RemoveRequestFromCollectionResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    let request_id = payload.request_id.trim().to_string();

    if request_id.is_empty() {
        return Err(ApiError::BadRequest("Request ID cannot be empty".into()));
    }

    let result =
        sqlx::query("DELETE FROM collection_requests WHERE collection_id = $1 AND request_id = $2")
            .bind(collection_id)
            .bind(&request_id)
            .execute(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    if result.rows_affected() == 0 {
        return Err(ApiError::NotFound(format!(
            "Request '{}' not found in collection '{}'",
            request_id, collection_id
        )));
    }

    // Invalidate collection caches
    state.invalidate_collection_caches(collection_id);
    if let Some(ref token) = collection_meta.public_token {
        state.invalidate_public_collection_cache(token);
    }

    Ok(Json(RemoveRequestFromCollectionResponse {
        collection_id,
        request_id,
        message: "Request removed from collection".into(),
    }))
}

/// Get all collections that contain a specific request.
/// Only returns collections the user owns or is admin.
///
/// GET /logs/:request_id/collections
pub async fn get_request_collections(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
) -> Result<Json<RequestCollectionsResponse>> {
    let auth = get_auth(&state, &headers).await?;
    // Check if request exists
    let request_exists = sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM requests WHERE request_id = $1)",
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

    let collections = if auth.is_admin {
        // Admins see all collections containing this request
        sqlx::query_as::<_, CollectionSummary>(
            r#"
            SELECT
                c.id,
                c.name,
                c.description,
                c.created_at,
                c.updated_at,
                c.created_by,
                (SELECT COUNT(*) FROM collection_requests cr2 WHERE cr2.collection_id = c.id)::bigint as request_count,
                c.is_public,
                c.public_token
            FROM collections c
            INNER JOIN collection_requests cr ON c.id = cr.collection_id
            WHERE cr.request_id = $1
            ORDER BY c.name ASC
            "#,
        )
        .bind(&request_id)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    } else {
        // Non-admins only see their own collections
        let owner_id = get_owner_id(&auth);
        sqlx::query_as::<_, CollectionSummary>(
            r#"
            SELECT
                c.id,
                c.name,
                c.description,
                c.created_at,
                c.updated_at,
                c.created_by,
                (SELECT COUNT(*) FROM collection_requests cr2 WHERE cr2.collection_id = c.id)::bigint as request_count,
                c.is_public,
                c.public_token
            FROM collections c
            INNER JOIN collection_requests cr ON c.id = cr.collection_id
            WHERE cr.request_id = $1 AND c.created_by = $2
            ORDER BY c.name ASC
            "#,
        )
        .bind(&request_id)
        .bind(&owner_id)
        .fetch_all(&state.db_pool)
        .await
        .map_err(ApiError::from)?
    };

    Ok(Json(RequestCollectionsResponse {
        request_id,
        collections,
    }))
}

/// Add a request to a collection (alternative endpoint from request context).
/// Add a request to a collection (alternative endpoint).
/// Only accessible by collection owner or admin.
///
/// POST /logs/:request_id/collections
pub async fn add_request_to_collection_by_request(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<AddToCollectionByRequestPayload>,
) -> Result<(StatusCode, Json<AddRequestToCollectionResponse>)> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(payload.collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    // Check if the request exists
    let request_exists = sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM requests WHERE request_id = $1)",
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

    // Check if the collection exists
    let collection_exists =
        sqlx::query_scalar::<_, bool>("SELECT EXISTS(SELECT 1 FROM collections WHERE id = $1)")
            .bind(payload.collection_id)
            .fetch_one(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    if !collection_exists {
        return Err(ApiError::NotFound(format!(
            "Collection '{}' not found",
            payload.collection_id
        )));
    }

    // Try to insert, handle duplicate gracefully
    let result = sqlx::query(
        r#"
        INSERT INTO collection_requests (collection_id, request_id, added_by, notes)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (collection_id, request_id) DO NOTHING
        "#,
    )
    .bind(payload.collection_id)
    .bind(&request_id)
    .bind(&payload.added_by)
    .bind(&payload.notes)
    .execute(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let message = if result.rows_affected() > 0 {
        "Request added to collection"
    } else {
        "Request already in collection"
    };

    Ok((
        StatusCode::OK,
        Json(AddRequestToCollectionResponse {
            collection_id: payload.collection_id,
            request_id,
            message: message.into(),
        }),
    ))
}

/// Payload for adding a request to a collection from the request context.
#[derive(Debug, Deserialize)]
pub struct AddToCollectionByRequestPayload {
    pub collection_id: i64,
    pub added_by: Option<String>,
    pub notes: Option<String>,
}

/// Remove a request from a collection (from request context).
/// Remove a request from a collection (alternative endpoint).
/// Only accessible by collection owner or admin.
///
/// DELETE /logs/:request_id/collections
pub async fn remove_request_from_collection_by_request(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(request_id): Path<String>,
    Json(payload): Json<RemoveFromCollectionByRequestPayload>,
) -> Result<Json<RemoveRequestFromCollectionResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(payload.collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection_meta =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection_meta.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }
    let result =
        sqlx::query("DELETE FROM collection_requests WHERE collection_id = $1 AND request_id = $2")
            .bind(payload.collection_id)
            .bind(&request_id)
            .execute(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    if result.rows_affected() == 0 {
        return Err(ApiError::NotFound(format!(
            "Request '{}' not found in collection '{}'",
            request_id, payload.collection_id
        )));
    }

    Ok(Json(RemoveRequestFromCollectionResponse {
        collection_id: payload.collection_id,
        request_id,
        message: "Request removed from collection".into(),
    }))
}

/// Payload for removing a request from a collection from the request context.
#[derive(Debug, Deserialize)]
pub struct RemoveFromCollectionByRequestPayload {
    pub collection_id: i64,
}

// ============================================================================
// Public Collection Handlers
// ============================================================================

/// Make a collection public and generate a shareable link.
/// Only accessible by owner or admin.
///
/// POST /collections/:collection_id/public
pub async fn make_collection_public(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
) -> Result<Json<MakePublicResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }

    // Generate a new public token
    let public_token = generate_public_token();

    // Update the collection
    sqlx::query("UPDATE collections SET is_public = TRUE, public_token = $1 WHERE id = $2")
        .bind(&public_token)
        .bind(collection_id)
        .execute(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

    let public_url = format!("/share/{}", public_token);

    // Invalidate collection caches
    state.invalidate_collection_caches(collection_id);

    Ok(Json(MakePublicResponse {
        collection_id,
        is_public: true,
        public_token: Some(public_token.clone()),
        public_url: Some(public_url),
        message: "Collection is now public".to_string(),
    }))
}

/// Make a collection private (remove public access).
/// Only accessible by owner or admin.
///
/// DELETE /collections/:collection_id/public
pub async fn make_collection_private(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(collection_id): Path<i64>,
) -> Result<Json<MakePublicResponse>> {
    let auth = get_auth(&state, &headers).await?;

    // Check if collection exists and user has access
    let collection_check = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE id = $1",
    )
    .bind(collection_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection =
        collection_check.ok_or_else(|| ApiError::NotFound("Collection not found".into()))?;

    if !can_access_collection(&auth, collection.created_by.as_deref()) {
        return Err(ApiError::forbidden(
            "You don't have access to this collection",
        ));
    }

    // Invalidate public collection cache before removing access
    if let Some(ref token) = collection.public_token {
        state.invalidate_public_collection_cache(token);
    }

    // Update the collection
    sqlx::query("UPDATE collections SET is_public = FALSE, public_token = NULL WHERE id = $1")
        .bind(collection_id)
        .execute(&state.db_pool)
        .await
        .map_err(ApiError::from)?;

    // Invalidate collection caches
    state.invalidate_collection_caches(collection_id);

    Ok(Json(MakePublicResponse {
        collection_id,
        is_public: false,
        public_token: None,
        public_url: None,
        message: "Collection is now private".to_string(),
    }))
}

/// Get a public collection by its public token.
/// No authentication required.
///
/// GET /share/:public_token
pub async fn get_public_collection(
    State(state): State<AppState>,
    Path(public_token): Path<String>,
    Query(query): Query<ListCollectionsQuery>,
) -> Result<Json<PublicCollectionResponse>> {
    let limit = query.limit.clamp(1, 100);
    let offset = query.offset.max(0);

    // Create cache key including pagination params
    let cache_key = format!("{}:{}:{}", public_token, limit, offset);

    // Check cache first
    if let Some(cached) = state.public_collection_cache.get(&cache_key) {
        tracing::debug!(public_token = %public_token, "Public collection cache hit");
        let response: PublicCollectionResponse = serde_json::from_str(&cached)
            .map_err(|e| ApiError::internal(format!("Cache deserialization error: {}", e)))?;
        return Ok(Json(response));
    }

    tracing::debug!(public_token = %public_token, "Public collection cache miss");

    // Find the collection by public token
    let collection = sqlx::query_as::<_, Collection>(
        "SELECT id, name, description, created_at, updated_at, created_by, is_public, public_token FROM collections WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&public_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let collection = collection.ok_or_else(|| {
        ApiError::NotFound("Public collection not found or link has expired".into())
    })?;

    // Get request count
    let total_requests: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM collection_requests WHERE collection_id = $1")
            .bind(collection.id)
            .fetch_one(&state.db_pool)
            .await
            .map_err(ApiError::from)?;

    // Get requests in the collection
    let requests = sqlx::query_as::<_, CollectionRequest>(
        r#"
        SELECT
            cr.request_id,
            cr.added_at,
            cr.added_by,
            cr.notes,
            r.created_at as created_ts,
            r.completed_at as finished_ts,
            r.model as model_id,
            r.final_text
        FROM collection_requests cr
        INNER JOIN requests r ON cr.request_id = r.request_id
        WHERE cr.collection_id = $1
        ORDER BY cr.added_at DESC
        LIMIT $2 OFFSET $3
        "#,
    )
    .bind(collection.id)
    .bind(limit)
    .bind(offset)
    .fetch_all(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let response = PublicCollectionResponse {
        collection: PublicCollectionInfo {
            id: collection.id,
            name: collection.name,
            description: collection.description,
            created_at: collection.created_at,
            request_count: total_requests,
        },
        requests,
        total_requests,
    };

    // Cache the response
    if let Ok(serialized) = serde_json::to_string(&response) {
        state.public_collection_cache.insert(cache_key, serialized);
    }

    Ok(Json(response))
}

/// Response for making a collection public.
#[derive(Debug, Serialize)]
pub struct MakePublicResponse {
    pub collection_id: i64,
    pub is_public: bool,
    pub public_token: Option<String>,
    pub public_url: Option<String>,
    pub message: String,
}

/// Response for getting a public collection.
#[derive(Debug, Serialize, Deserialize)]
pub struct PublicCollectionResponse {
    pub collection: PublicCollectionInfo,
    pub requests: Vec<CollectionRequest>,
    pub total_requests: i64,
}

/// Public collection info (limited fields for public view).
#[derive(Debug, Serialize, Deserialize)]
pub struct PublicCollectionInfo {
    pub id: i64,
    pub name: String,
    pub description: Option<String>,
    pub created_at: DateTime<Utc>,
    pub request_count: i64,
}
