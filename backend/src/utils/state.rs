use std::sync::Arc;
use std::time::Duration;

use chrono::{DateTime, Utc};
use serde::Serialize;
use sqlx::PgPool;
use tokio::sync::broadcast;

use super::auth::{ApiKeyCache, AuthState};
use super::cache::{LogCache, TtlCache};

/// Event sent to SSE clients when a new log is ingested
#[derive(Debug, Clone, Serialize)]
pub struct NewLogEvent {
    pub request_id: String,
    pub created_ts: DateTime<Utc>,
    pub finished_ts: Option<DateTime<Utc>>,
    pub model_id: Option<String>,
    pub user_api_key: Option<String>,
    pub final_text: Option<String>,
    pub total_steps: i64,
    pub favorited_by: Vec<String>,
    pub discussion_count: i64,
}

/// Channel capacity for SSE broadcast
const SSE_CHANNEL_CAPACITY: usize = 256;

/// TTL for collections cache (30 seconds)
const COLLECTIONS_CACHE_TTL: Duration = Duration::from_secs(30);

/// TTL for public collections cache (60 seconds - longer since they change less frequently)
const PUBLIC_COLLECTIONS_CACHE_TTL: Duration = Duration::from_secs(60);

/// TTL for discussions cache (30 seconds)
const DISCUSSIONS_CACHE_TTL: Duration = Duration::from_secs(30);

/// Cache key for collections list (includes user filter)
pub type CollectionsListCacheKey = Option<String>; // None = all, Some(user) = filtered

/// Cache key for a single collection
pub type CollectionCacheKey = i64; // collection_id

/// Cache key for public collection by token
pub type PublicCollectionCacheKey = String; // public_token

/// Cache key for discussions (request_id)
pub type DiscussionsCacheKey = String;

#[derive(Clone)]
pub struct AppState {
    pub db_pool: PgPool,
    pub log_cache: Arc<LogCache>,
    /// Broadcast channel for SSE events when new logs are ingested
    pub log_events_tx: broadcast::Sender<NewLogEvent>,
    /// Authentication state with API key cache
    pub auth: AuthState,
    /// Cache for collections list responses (keyed by user filter)
    pub collections_list_cache: Arc<TtlCache<CollectionsListCacheKey, String>>,
    /// Cache for individual collection responses
    pub collection_cache: Arc<TtlCache<CollectionCacheKey, String>>,
    /// Cache for public collection responses (keyed by public_token)
    pub public_collection_cache: Arc<TtlCache<PublicCollectionCacheKey, String>>,
    /// Cache for discussions list responses (keyed by request_id)
    pub discussions_cache: Arc<TtlCache<DiscussionsCacheKey, String>>,
}

impl AppState {
    /// Create a new AppState with the default 2.8 GB cache.
    pub fn new(db_pool: PgPool) -> Self {
        let (log_events_tx, _) = broadcast::channel(SSE_CHANNEL_CAPACITY);
        let auth = AuthState {
            pool: db_pool.clone(),
            cache: Arc::new(ApiKeyCache::new()),
        };
        Self {
            db_pool,
            log_cache: Arc::new(LogCache::new()),
            log_events_tx,
            auth,
            collections_list_cache: Arc::new(TtlCache::new(COLLECTIONS_CACHE_TTL)),
            collection_cache: Arc::new(TtlCache::new(COLLECTIONS_CACHE_TTL)),
            public_collection_cache: Arc::new(TtlCache::new(PUBLIC_COLLECTIONS_CACHE_TTL)),
            discussions_cache: Arc::new(TtlCache::new(DISCUSSIONS_CACHE_TTL)),
        }
    }

    /// Create a new AppState with a custom cache size limit.
    pub fn with_cache_size(db_pool: PgPool, max_bytes: u64) -> Self {
        let (log_events_tx, _) = broadcast::channel(SSE_CHANNEL_CAPACITY);
        let auth = AuthState {
            pool: db_pool.clone(),
            cache: Arc::new(ApiKeyCache::new()),
        };
        Self {
            db_pool,
            log_cache: Arc::new(LogCache::with_max_bytes(max_bytes)),
            log_events_tx,
            auth,
            collections_list_cache: Arc::new(TtlCache::new(COLLECTIONS_CACHE_TTL)),
            collection_cache: Arc::new(TtlCache::new(COLLECTIONS_CACHE_TTL)),
            public_collection_cache: Arc::new(TtlCache::new(PUBLIC_COLLECTIONS_CACHE_TTL)),
            discussions_cache: Arc::new(TtlCache::new(DISCUSSIONS_CACHE_TTL)),
        }
    }

    /// Invalidate collection-related caches when collections change
    pub fn invalidate_collection_caches(&self, collection_id: i64) {
        self.collection_cache.invalidate(&collection_id);
        self.collections_list_cache.clear(); // Clear all list caches since any could be affected
    }

    /// Invalidate public collection cache when a collection's public status changes
    pub fn invalidate_public_collection_cache(&self, public_token: &str) {
        self.public_collection_cache
            .invalidate(&public_token.to_string());
    }

    /// Invalidate discussions cache for a request
    pub fn invalidate_discussions_cache(&self, request_id: &str) {
        self.discussions_cache.invalidate(&request_id.to_string());
    }

    /// Subscribe to log events for SSE streaming
    pub fn subscribe_log_events(&self) -> broadcast::Receiver<NewLogEvent> {
        self.log_events_tx.subscribe()
    }

    /// Broadcast a new log event to all SSE subscribers
    pub fn broadcast_new_log(&self, event: NewLogEvent) {
        // Ignore errors (no subscribers is fine)
        let _ = self.log_events_tx.send(event);
    }
}
