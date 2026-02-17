use axum::{
    Router,
    extract::DefaultBodyLimit,
    http::StatusCode,
    middleware,
    routing::{get, post},
};
use tower_http::{cors::CorsLayer, trace::TraceLayer};

use crate::utils::body_limit::{MAX_BODY_SIZE, body_limit_middleware};

use crate::{
    handlers::{
        activation_explorer::{
            activation_health, get_activation_rows, get_activation_run_summary, get_feature_deltas,
            get_top_features, list_activation_runs, post_extract_features, run_activation,
        },
        auth::{
            bootstrap_admin_key, create_api_key, get_current_user, list_api_keys as list_auth_keys,
            revoke_api_key, update_api_key, validate_key,
        },
        collections::{
            add_request_to_collection, add_request_to_collection_by_request, create_collection,
            delete_collection, get_collection, get_public_collection, get_request_collections,
            list_collections, make_collection_private, make_collection_public,
            remove_request_from_collection, remove_request_from_collection_by_request,
            update_collection,
        },
        discussions::{
            create_discussion, delete_discussion, get_discussion, list_discussions,
            update_discussion,
        },
        favorites::{add_favorite, get_favorites, remove_favorite},
        health::health_check,
        ingest::ingest_payload,
        logs::{
            get_log, get_request_via_collection, list_api_keys, list_logs, make_request_private,
            make_request_public, stream_logs,
        },
        og::{
            og_image_handler, playground_og_image_handler, playground_with_og,
            share_request_with_og,
        },
        playground::{
            analyze_features, extract_features, generate_mod_code, generate_playground_key,
            run_inference, upload_mod,
        },
        tags::{add_tag, get_tags, remove_tag},
    },
    utils::AppState,
};

/// Build the application's router.
///
/// ## Health Check
/// - `GET /health` / `GET /healthz` -> [`crate::handlers::health::HealthResponse`]
///
/// ## Authentication Routes
/// - `POST /auth/bootstrap` -> Bootstrap the first admin API key
/// - `GET /auth/validate` -> Validate an API key
/// - `GET /auth/me` -> Get current user info
/// - `GET /auth/keys` -> List all API keys (admin only)
/// - `POST /auth/keys` -> Create a new API key (admin only)
/// - `PUT /auth/keys` -> Update an API key (admin only)
/// - `DELETE /auth/keys` -> Revoke an API key (admin only)
///
/// ## Logs Routes
/// - `GET /logs` -> returns [`crate::handlers::logs::ListLogsResponse`]
/// - `GET /logs/stream` -> SSE stream of new logs
/// - `GET /logs/api-keys` -> List API keys with request counts
/// - `GET /logs/:request_id` -> returns [`crate::handlers::logs::LogResponse`]
/// - `GET /logs/:request_id/favorite` -> returns favorites for a request
/// - `POST /logs/:request_id/favorite` -> adds a user to favorites
/// - `DELETE /logs/:request_id/favorite` -> removes a user from favorites
/// - `GET /logs/:request_id/tags` -> returns tags for a request
/// - `POST /logs/:request_id/tags` -> adds a tag to a request
/// - `DELETE /logs/:request_id/tags` -> removes a tag from a request
/// - `GET /logs/:request_id/discussions` -> lists discussions for a request
/// - `POST /logs/:request_id/discussions` -> creates a new discussion
/// - `GET /logs/:request_id/discussions/:id` -> gets a single discussion
/// - `PUT /logs/:request_id/discussions/:id` -> updates a discussion
/// - `DELETE /logs/:request_id/discussions/:id` -> deletes a discussion
/// - `GET /logs/:request_id/collections` -> gets collections containing this request
/// - `POST /logs/:request_id/collections` -> adds request to a collection
/// - `DELETE /logs/:request_id/collections` -> removes request from a collection
///
/// ## Collections Routes
/// - `GET /collections` -> lists all collections
/// - `POST /collections` -> creates a new collection
/// - `GET /collections/:collection_id` -> gets a collection with its requests
/// - `PUT /collections/:collection_id` -> updates a collection
/// - `DELETE /collections/:collection_id` -> deletes a collection
/// - `POST /collections/:collection_id/requests` -> adds a request to the collection
/// - `DELETE /collections/:collection_id/requests` -> removes a request from the collection
/// - `POST /collections/:collection_id/public` -> makes a collection public
/// - `DELETE /collections/:collection_id/public` -> makes a collection private
///
/// ## Public Routes (no auth required)
/// - `GET /share/:public_token` -> gets a public collection by its shareable token
/// - `GET /share/:collection_token/request/:request_id` -> gets a request via its collection's public token
/// - `GET /share/request/:public_token` -> gets a public request by its shareable token
///
/// ## Request Public Sharing
/// - `POST /logs/:request_id/public` -> makes a request public
/// - `DELETE /logs/:request_id/public` -> makes a request private
///
/// ## Ingest Route
/// - `POST /v1/ingest` -> ingests full inference payloads (see [`crate::handlers::ingest`])
pub fn build_router(state: AppState) -> Router {
    Router::new()
        // Health check routes
        .route("/health", get(health_check))
        .route("/healthz", get(health_check))
        // Authentication routes
        .route(
            "/auth/bootstrap",
            post(bootstrap_admin_key).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/auth/validate",
            get(validate_key).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/auth/me",
            get(get_current_user).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/auth/keys",
            get(list_auth_keys)
                .post(create_api_key)
                .put(update_api_key)
                .delete(revoke_api_key)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Logs routes
        .route(
            "/logs",
            get(list_logs).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/",
            // Preserve trailing-slash variant for legacy clients.
            get(list_logs).options(|| async { StatusCode::NO_CONTENT }),
        )
        // SSE stream route (must be before /logs/:request_id to avoid conflict)
        .route(
            "/logs/stream",
            get(stream_logs).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/stream/",
            get(stream_logs).options(|| async { StatusCode::NO_CONTENT }),
        )
        // API keys route (must be before /logs/:request_id to avoid conflict)
        .route(
            "/logs/api-keys",
            get(list_api_keys).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/api-keys/",
            get(list_api_keys).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id",
            get(get_log).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/",
            get(get_log).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Public request sharing routes
        .route(
            "/logs/:request_id/public",
            post(make_request_public)
                .delete(make_request_private)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/public/",
            post(make_request_public)
                .delete(make_request_private)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Favorites routes
        .route(
            "/logs/:request_id/favorite",
            get(get_favorites)
                .post(add_favorite)
                .delete(remove_favorite)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/favorite/",
            get(get_favorites)
                .post(add_favorite)
                .delete(remove_favorite)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Tags routes
        .route(
            "/logs/:request_id/tags",
            get(get_tags)
                .post(add_tag)
                .delete(remove_tag)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/tags/",
            get(get_tags)
                .post(add_tag)
                .delete(remove_tag)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Discussions routes (list and create)
        .route(
            "/logs/:request_id/discussions",
            get(list_discussions)
                .post(create_discussion)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/discussions/",
            get(list_discussions)
                .post(create_discussion)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Discussions routes (single item operations)
        .route(
            "/logs/:request_id/discussions/:discussion_id",
            get(get_discussion)
                .put(update_discussion)
                .delete(delete_discussion)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/discussions/:discussion_id/",
            get(get_discussion)
                .put(update_discussion)
                .delete(delete_discussion)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Request collections routes (collections containing a specific request)
        .route(
            "/logs/:request_id/collections",
            get(get_request_collections)
                .post(add_request_to_collection_by_request)
                .delete(remove_request_from_collection_by_request)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/logs/:request_id/collections/",
            get(get_request_collections)
                .post(add_request_to_collection_by_request)
                .delete(remove_request_from_collection_by_request)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Collections routes (list and create)
        .route(
            "/collections",
            get(list_collections)
                .post(create_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/collections/",
            get(list_collections)
                .post(create_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Collections routes (single item operations)
        .route(
            "/collections/:collection_id",
            get(get_collection)
                .put(update_collection)
                .delete(delete_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/collections/:collection_id/",
            get(get_collection)
                .put(update_collection)
                .delete(delete_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Collection requests routes (add/remove requests from collection)
        .route(
            "/collections/:collection_id/requests",
            post(add_request_to_collection)
                .delete(remove_request_from_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/collections/:collection_id/requests/",
            post(add_request_to_collection)
                .delete(remove_request_from_collection)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // Public collection toggle routes
        .route(
            "/collections/:collection_id/public",
            post(make_collection_public)
                .delete(make_collection_private)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/collections/:collection_id/public/",
            post(make_collection_public)
                .delete(make_collection_private)
                .options(|| async { StatusCode::NO_CONTENT }),
        )
        // OG image route for social media previews (must come before main share route)
        .route(
            "/share/request/:public_token/og-image.png",
            get(og_image_handler).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Public shareable request route (no auth required)
        // NOTE: This must come before /share/:collection_token routes to avoid "request" being matched as a token
        // This handler detects crawlers and serves HTML with OG tags, or JSON for regular browsers
        .route(
            "/share/request/:public_token",
            get(share_request_with_og).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/share/request/:public_token/",
            get(share_request_with_og).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Access request via public collection token (no auth required)
        .route(
            "/share/:collection_token/request/:request_id",
            get(get_request_via_collection).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/share/:collection_token/request/:request_id/",
            get(get_request_via_collection).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Public shareable collection route (no auth required)
        // NOTE: This must come last as it's the most general /share/:token pattern
        .route(
            "/share/:public_token",
            get(get_public_collection).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/share/:public_token/",
            get(get_public_collection).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Ingest route
        .route(
            "/v1/ingest",
            post(ingest_payload).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Playground OG routes (for social media previews)
        .route(
            "/playground/og-image.png",
            get(playground_og_image_handler).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground",
            get(playground_with_og).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/",
            get(playground_with_og).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Playground routes (public, no auth required)
        .route(
            "/playground/api-key",
            post(generate_playground_key).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/api-key/",
            post(generate_playground_key).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/mods/generate",
            post(generate_mod_code).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/mods/generate/",
            post(generate_mod_code).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/mods/upload",
            post(upload_mod).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/mods/upload/",
            post(upload_mod).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/inference",
            post(run_inference).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/inference/",
            post(run_inference).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Feature extraction routes
        .route(
            "/playground/features/extract",
            post(extract_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/features/extract/",
            post(extract_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Feature analysis routes
        .route(
            "/playground/features/analyze",
            post(analyze_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/features/analyze/",
            post(analyze_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        // Activation explorer routes (local-first, no auth for v0)
        .route(
            "/playground/activations/run",
            post(run_activation).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/extract",
            post(post_extract_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/extract/",
            post(post_extract_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/runs",
            get(list_activation_runs).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/runs/",
            get(list_activation_runs).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/health",
            get(activation_health).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/health/",
            get(activation_health).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/summary",
            get(get_activation_run_summary).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/summary/",
            get(get_activation_run_summary).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/rows",
            get(get_activation_rows).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/rows/",
            get(get_activation_rows).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/feature-deltas",
            get(get_feature_deltas).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/feature-deltas/",
            get(get_feature_deltas).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/top-features",
            get(get_top_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .route(
            "/playground/activations/:request_id/top-features/",
            get(get_top_features).options(|| async { StatusCode::NO_CONTENT }),
        )
        .with_state(state)
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .layer(middleware::from_fn(body_limit_middleware))
        .layer(DefaultBodyLimit::max(MAX_BODY_SIZE))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use sqlx::postgres::PgPoolOptions;
    use tower::ServiceExt;

    #[tokio::test]
    async fn get_logs_route_is_not_method_not_allowed() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/logs")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_ne!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[tokio::test]
    async fn ingest_route_is_registered() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/ingest")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_ne!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[tokio::test]
    async fn activation_explorer_routes_are_registered() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response_runs = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("OPTIONS")
                    .uri("/playground/activations/runs")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");
        assert_ne!(response_runs.status(), StatusCode::METHOD_NOT_ALLOWED);

        let response_run = app
            .oneshot(
                Request::builder()
                    .method("OPTIONS")
                    .uri("/playground/activations/run")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");
        assert_ne!(response_run.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[tokio::test]
    async fn rejects_oversized_payload_with_413() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        // Create a request with Content-Length header exceeding MAX_BODY_SIZE (75 MB)
        let oversized_length = MAX_BODY_SIZE + 1;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/ingest")
                    .header("content-type", "application/json")
                    .header("content-length", oversized_length.to_string())
                    .body(Body::empty()) // Body content doesn't matter, we check header first
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_eq!(
            response.status(),
            StatusCode::PAYLOAD_TOO_LARGE,
            "Expected 413 Payload Too Large for oversized request"
        );
    }

    #[tokio::test]
    async fn accepts_payload_under_limit() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        // Create a small payload that's well under the limit
        let small_payload = r#"{"request": {}}"#;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/ingest")
                    .header("content-type", "application/json")
                    .body(Body::from(small_payload))
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        // Should not be 413 - might be 400/422 due to invalid payload, but not size-related
        assert_ne!(
            response.status(),
            StatusCode::PAYLOAD_TOO_LARGE,
            "Small payload should not be rejected for size"
        );
    }

    #[tokio::test]
    async fn rejects_payload_just_over_limit() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        // Exactly 1 byte over the limit
        let just_over_limit = MAX_BODY_SIZE + 1;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/ingest")
                    .header("content-type", "application/json")
                    .header("content-length", just_over_limit.to_string())
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_eq!(
            response.status(),
            StatusCode::PAYLOAD_TOO_LARGE,
            "Payload 1 byte over limit should be rejected"
        );
    }

    #[tokio::test]
    async fn accepts_payload_at_exact_limit() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        // Exactly at the limit should be accepted
        let at_limit = MAX_BODY_SIZE;

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/v1/ingest")
                    .header("content-type", "application/json")
                    .header("content-length", at_limit.to_string())
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        // Should not be 413 - the size is exactly at the limit, not over
        assert_ne!(
            response.status(),
            StatusCode::PAYLOAD_TOO_LARGE,
            "Payload exactly at limit should not be rejected for size"
        );
    }

    #[tokio::test]
    async fn collections_route_is_registered() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/collections")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_ne!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[tokio::test]
    async fn auth_bootstrap_route_is_registered() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/auth/bootstrap")
                    .header("content-type", "application/json")
                    .body(Body::from(r#"{"name": "test", "secret": "test"}"#))
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_ne!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    }

    #[tokio::test]
    async fn auth_validate_route_is_registered() {
        let pool = PgPoolOptions::new()
            .max_connections(1)
            .connect_lazy("postgres://postgres:postgres@localhost:5432/postgres")
            .expect("valid postgres connection string");

        let state = AppState::new(pool);
        let app = build_router(state);

        let response = app
            .oneshot(
                Request::builder()
                    .method("GET")
                    .uri("/auth/validate")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .expect("router should respond");

        assert_ne!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    }
}
