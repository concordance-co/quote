use axum::{Json, http::StatusCode, response::IntoResponse};
use serde::Serialize;
use serde_json::json;
use thiserror::Error;
use tracing::error;

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("bad request: {0}")]
    BadRequest(String),
    #[error("conflict: {0}")]
    Conflict(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("unauthorized: {0}")]
    Unauthorized(String),
    #[error("forbidden: {0}")]
    Forbidden(String),
    #[error("internal error: {0}")]
    Internal(String),
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
}

impl ApiError {
    /// Create an unauthorized error (401)
    pub fn unauthorized(message: impl Into<String>) -> Self {
        ApiError::Unauthorized(message.into())
    }

    /// Create a forbidden error (403)
    pub fn forbidden(message: impl Into<String>) -> Self {
        ApiError::Forbidden(message.into())
    }

    /// Create a not found error (404)
    pub fn not_found(message: impl Into<String>) -> Self {
        ApiError::NotFound(message.into())
    }

    /// Create a bad request error (400)
    pub fn bad_request(message: impl Into<String>) -> Self {
        ApiError::BadRequest(message.into())
    }

    /// Create a conflict error (409)
    pub fn conflict(message: impl Into<String>) -> Self {
        ApiError::Conflict(message.into())
    }

    /// Create an internal server error (500)
    pub fn internal(message: impl Into<String>) -> Self {
        ApiError::Internal(message.into())
    }
}

#[derive(Serialize)]
struct ErrorBody {
    error: String,
}

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        let status = match self {
            ApiError::BadRequest(_) => StatusCode::BAD_REQUEST,
            ApiError::Conflict(_) => StatusCode::CONFLICT,
            ApiError::NotFound(_) => StatusCode::NOT_FOUND,
            ApiError::Unauthorized(_) => StatusCode::UNAUTHORIZED,
            ApiError::Forbidden(_) => StatusCode::FORBIDDEN,
            ApiError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
            ApiError::Database(_) => StatusCode::INTERNAL_SERVER_ERROR,
        };

        let message = self.to_string();
        error!(%message, "request failed");

        (status, Json(json!(ErrorBody { error: message }))).into_response()
    }
}
