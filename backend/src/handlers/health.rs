use axum::{Json, extract::State, http::StatusCode};
use serde::Serialize;
use tracing::error;

use crate::utils::AppState;

#[derive(Debug, Serialize)]
pub struct HealthResponse {
    pub status: &'static str,
    pub database: DatabaseStatus,
    pub cache: CacheStatus,
}

#[derive(Debug, Serialize)]
pub struct DatabaseStatus {
    pub status: &'static str,
    pub error: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CacheStatus {
    pub entry_count: usize,
    pub current_bytes: u64,
    pub max_bytes: u64,
    pub memory_usage_percent: f64,
    pub hits: u64,
    pub misses: u64,
    pub hit_rate_percent: f64,
}

/// Responds with service health and database connectivity status.
pub async fn health_check(State(state): State<AppState>) -> (StatusCode, Json<HealthResponse>) {
    let cache_stats = state.log_cache.stats();
    let cache_status = CacheStatus {
        entry_count: cache_stats.entry_count,
        current_bytes: cache_stats.current_bytes,
        max_bytes: cache_stats.max_bytes,
        memory_usage_percent: cache_stats.memory_usage_percent(),
        hits: cache_stats.hits,
        misses: cache_stats.misses,
        hit_rate_percent: cache_stats.hit_rate(),
    };

    match sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&state.db_pool)
        .await
    {
        Ok(_) => {
            let response = HealthResponse {
                status: "ok",
                database: DatabaseStatus {
                    status: "ok",
                    error: None,
                },
                cache: cache_status,
            };
            (StatusCode::OK, Json(response))
        }
        Err(err) => {
            error!(error = %err, "database health check failed");
            let response = HealthResponse {
                status: "degraded",
                database: DatabaseStatus {
                    status: "error",
                    error: Some("database connectivity failed".to_string()),
                },
                cache: cache_status,
            };
            (StatusCode::SERVICE_UNAVAILABLE, Json(response))
        }
    }
}
