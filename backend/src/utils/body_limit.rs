//! Middleware for request body size limiting with logging.
//!
//! This module provides a body limit layer that logs rejected payloads,
//! including the size of the payload that was rejected.

use axum::{
    extract::Request,
    http::StatusCode,
    middleware::Next,
    response::{IntoResponse, Response},
};
use tracing::warn;

/// Maximum allowed body size in bytes (75 MB).
pub const MAX_BODY_SIZE: usize = 75 * 1024 * 1024;

/// Middleware that checks Content-Length and rejects oversized payloads with logging.
///
/// This checks the Content-Length header before the request body is read,
/// allowing us to log the size of rejected payloads and return a helpful error message.
pub async fn body_limit_middleware(request: Request, next: Next) -> Response {
    // Extract content-length header if present
    let content_length = request
        .headers()
        .get(axum::http::header::CONTENT_LENGTH)
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<usize>().ok());

    tracing::info!("Content-Length: {:?}", content_length);

    if let Some(length) = content_length {
        if length > MAX_BODY_SIZE {
            let length_mb = length as f64 / 1_000_000.0;
            let max_mb = MAX_BODY_SIZE as f64 / 1_000_000.0;

            warn!(
                payload_size_bytes = length,
                payload_size_mb = format!("{:.2}", length_mb),
                max_size_bytes = MAX_BODY_SIZE,
                max_size_mb = format!("{:.2}", max_mb),
                path = %request.uri().path(),
                method = %request.method(),
                "Rejected request: payload too large"
            );

            return (
                StatusCode::PAYLOAD_TOO_LARGE,
                format!(
                    "Request body too large: {:.2} MB exceeds maximum of {:.2} MB",
                    length_mb, max_mb
                ),
            )
                .into_response();
        }
    }

    next.run(request).await
}
