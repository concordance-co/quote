//! Memory-aware LRU cache for log responses.
//!
//! This module provides a thread-safe LRU cache with a configurable memory limit.
//! Cache entries are evicted when the total memory usage exceeds the limit,
//! starting with the least recently used entries.

use std::{
    collections::HashMap,
    hash::Hash,
    sync::{
        RwLock,
        atomic::{AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};

use crate::handlers::logs::LogResponse;

/// Default maximum cache size: 2.8 GB
const DEFAULT_MAX_BYTES: u64 = 2_800_000_000;

/// Trait for estimating the memory size of a value.
pub trait MemorySize {
    /// Returns an estimate of the memory used by this value in bytes.
    fn memory_size(&self) -> usize;
}

impl MemorySize for String {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<String>() + self.capacity()
    }
}

impl<T: MemorySize> MemorySize for Option<T> {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<Option<T>>()
            + match self {
                Some(v) => v.memory_size(),
                None => 0,
            }
    }
}

impl<T: MemorySize> MemorySize for Vec<T> {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<Vec<T>>()
            + self.capacity() * std::mem::size_of::<T>()
            + self.iter().map(|v| v.memory_size()).sum::<usize>()
    }
}

impl MemorySize for i32 {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<i32>()
    }
}

impl MemorySize for i64 {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<i64>()
    }
}

impl MemorySize for f64 {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<f64>()
    }
}

impl MemorySize for bool {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<bool>()
    }
}

impl MemorySize for serde_json::Value {
    fn memory_size(&self) -> usize {
        // Rough estimate for JSON values
        match self {
            serde_json::Value::Null => std::mem::size_of::<serde_json::Value>(),
            serde_json::Value::Bool(_) => std::mem::size_of::<serde_json::Value>(),
            serde_json::Value::Number(_) => std::mem::size_of::<serde_json::Value>() + 16,
            serde_json::Value::String(s) => std::mem::size_of::<serde_json::Value>() + s.capacity(),
            serde_json::Value::Array(arr) => {
                std::mem::size_of::<serde_json::Value>()
                    + arr.iter().map(|v| v.memory_size()).sum::<usize>()
            }
            serde_json::Value::Object(map) => {
                std::mem::size_of::<serde_json::Value>()
                    + map
                        .iter()
                        .map(|(k, v)| k.capacity() + v.memory_size())
                        .sum::<usize>()
            }
        }
    }
}

impl MemorySize for chrono::DateTime<chrono::Utc> {
    fn memory_size(&self) -> usize {
        std::mem::size_of::<chrono::DateTime<chrono::Utc>>()
    }
}

impl MemorySize for LogResponse {
    fn memory_size(&self) -> usize {
        let mut size = std::mem::size_of::<LogResponse>();

        // String fields
        size += self.request_id.memory_size();
        size += self.system_prompt.memory_size();
        size += self.user_prompt.memory_size();
        size += self.formatted_prompt.memory_size();
        size += self.model_id.memory_size();
        size += self.model_version.memory_size();
        size += self.tokenizer_version.memory_size();
        size += self.vocab_hash.memory_size();
        size += self.sampler_preset.memory_size();
        size += self.sampler_algo.memory_size();
        size += self.final_text.memory_size();
        size += self.eos_reason.memory_size();

        // JSON fields
        size += self.request_tags.memory_size();

        // favorited_by Vec<String>
        size += self.favorited_by.memory_size();

        // tags Vec<String>
        size += self.tags.memory_size();

        // Vec<i32> for final_tokens
        if let Some(ref tokens) = self.final_tokens {
            size += tokens.len() * std::mem::size_of::<i32>();
        }

        // Active mod (small struct)
        if self.active_mod.is_some() {
            size += 64; // Approximate
        }

        // Events - estimate each event at ~200 bytes average
        size += self.events.len() * 200;

        // Mod calls - estimate each at ~150 bytes average
        size += self.mod_calls.len() * 150;

        // Mod logs - estimate each at ~100 bytes average
        size += self.mod_logs.len() * 100;

        // Actions - these can be larger due to payload
        size += self.actions.len() * 300;

        // Steps - estimate each at ~200 bytes
        size += self.steps.len() * 200;

        // Step logit summaries - estimate each at ~150 bytes
        size += self.step_logit_summaries.len() * 150;

        // Inference stats (small fixed struct)
        if self.inference_stats.is_some() {
            size += 200;
        }

        size
    }
}

/// A cached entry with its access order and size.
struct CacheEntry {
    value: LogResponse,
    size_bytes: usize,
    access_order: u64,
}

/// Thread-safe LRU cache with memory limit.
pub struct LogCache {
    /// The cached entries, keyed by request_id.
    entries: RwLock<HashMap<String, CacheEntry>>,
    /// Current total memory usage in bytes.
    current_bytes: AtomicU64,
    /// Maximum allowed memory usage in bytes.
    max_bytes: u64,
    /// Monotonically increasing counter for LRU ordering.
    access_counter: AtomicU64,
    /// Cache statistics
    hits: AtomicU64,
    misses: AtomicU64,
}

impl LogCache {
    /// Create a new cache with the default 2.8 GB limit.
    pub fn new() -> Self {
        Self::with_max_bytes(DEFAULT_MAX_BYTES)
    }

    /// Create a new cache with a custom memory limit.
    pub fn with_max_bytes(max_bytes: u64) -> Self {
        Self {
            entries: RwLock::new(HashMap::new()),
            current_bytes: AtomicU64::new(0),
            max_bytes,
            access_counter: AtomicU64::new(0),
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Get a cached log response by request_id.
    ///
    /// Returns `Some(LogResponse)` if found, `None` otherwise.
    /// Updates the access order for LRU tracking.
    pub fn get(&self, request_id: &str) -> Option<LogResponse> {
        // First try a read lock to check if the entry exists
        {
            let entries = self.entries.read().unwrap();
            if !entries.contains_key(request_id) {
                self.misses.fetch_add(1, Ordering::Relaxed);
                return None;
            }
        }

        // Entry exists, get write lock to update access order
        let mut entries = self.entries.write().unwrap();
        if let Some(entry) = entries.get_mut(request_id) {
            entry.access_order = self.access_counter.fetch_add(1, Ordering::Relaxed);
            self.hits.fetch_add(1, Ordering::Relaxed);
            Some(entry.value.clone())
        } else {
            self.misses.fetch_add(1, Ordering::Relaxed);
            None
        }
    }

    /// Insert a log response into the cache.
    ///
    /// If inserting would exceed the memory limit, evicts least recently used
    /// entries until there is enough space.
    pub fn insert(&self, request_id: String, value: LogResponse) {
        let size_bytes = value.memory_size();

        // Don't cache entries larger than half the max size
        if size_bytes as u64 > self.max_bytes / 2 {
            tracing::debug!(
                request_id = %request_id,
                size_bytes = size_bytes,
                "Skipping cache insert: entry too large"
            );
            return;
        }

        let mut entries = self.entries.write().unwrap();

        // Remove existing entry if present
        if let Some(old_entry) = entries.remove(&request_id) {
            self.current_bytes
                .fetch_sub(old_entry.size_bytes as u64, Ordering::Relaxed);
        }

        // Evict entries until we have space
        while self.current_bytes.load(Ordering::Relaxed) + size_bytes as u64 > self.max_bytes
            && !entries.is_empty()
        {
            // Find the least recently used entry
            let lru_key = entries
                .iter()
                .min_by_key(|(_, e)| e.access_order)
                .map(|(k, _)| k.clone());

            if let Some(key) = lru_key {
                if let Some(evicted) = entries.remove(&key) {
                    self.current_bytes
                        .fetch_sub(evicted.size_bytes as u64, Ordering::Relaxed);
                    tracing::trace!(
                        request_id = %key,
                        freed_bytes = evicted.size_bytes,
                        "Evicted cache entry"
                    );
                }
            } else {
                break;
            }
        }

        // Insert the new entry
        let access_order = self.access_counter.fetch_add(1, Ordering::Relaxed);
        entries.insert(
            request_id.clone(),
            CacheEntry {
                value,
                size_bytes,
                access_order,
            },
        );
        self.current_bytes
            .fetch_add(size_bytes as u64, Ordering::Relaxed);

        tracing::trace!(
            request_id = %request_id,
            size_bytes = size_bytes,
            total_bytes = self.current_bytes.load(Ordering::Relaxed),
            "Inserted cache entry"
        );
    }

    /// Remove an entry from the cache.
    ///
    /// Returns `true` if an entry was removed, `false` otherwise.
    pub fn invalidate(&self, request_id: &str) -> bool {
        let mut entries = self.entries.write().unwrap();
        if let Some(entry) = entries.remove(request_id) {
            self.current_bytes
                .fetch_sub(entry.size_bytes as u64, Ordering::Relaxed);
            true
        } else {
            false
        }
    }

    /// Clear all entries from the cache.
    pub fn clear(&self) {
        let mut entries = self.entries.write().unwrap();
        entries.clear();
        self.current_bytes.store(0, Ordering::Relaxed);
    }

    /// Get cache statistics.
    pub fn stats(&self) -> CacheStats {
        let entries = self.entries.read().unwrap();
        CacheStats {
            entry_count: entries.len(),
            current_bytes: self.current_bytes.load(Ordering::Relaxed),
            max_bytes: self.max_bytes,
            hits: self.hits.load(Ordering::Relaxed),
            misses: self.misses.load(Ordering::Relaxed),
        }
    }

    /// Get the current memory usage in bytes.
    pub fn current_bytes(&self) -> u64 {
        self.current_bytes.load(Ordering::Relaxed)
    }

    /// Get the number of cached entries.
    pub fn len(&self) -> usize {
        self.entries.read().unwrap().len()
    }

    /// Check if the cache is empty.
    pub fn is_empty(&self) -> bool {
        self.entries.read().unwrap().is_empty()
    }
}

impl Default for LogCache {
    fn default() -> Self {
        Self::new()
    }
}

/// Cache statistics.
#[derive(Debug, Clone)]
pub struct CacheStats {
    /// Number of entries in the cache.
    pub entry_count: usize,
    /// Current memory usage in bytes.
    pub current_bytes: u64,
    /// Maximum allowed memory in bytes.
    pub max_bytes: u64,
    /// Number of cache hits.
    pub hits: u64,
    /// Number of cache misses.
    pub misses: u64,
}

impl CacheStats {
    /// Calculate the cache hit rate as a percentage.
    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            (self.hits as f64 / total as f64) * 100.0
        }
    }

    /// Get memory usage as a percentage of the maximum.
    pub fn memory_usage_percent(&self) -> f64 {
        if self.max_bytes == 0 {
            0.0
        } else {
            (self.current_bytes as f64 / self.max_bytes as f64) * 100.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;

    fn make_test_response(request_id: &str, data_size: usize) -> LogResponse {
        LogResponse {
            request_id: request_id.to_string(),
            created_ts: Utc::now(),
            finished_ts: Some(Utc::now()),
            system_prompt: None,
            user_prompt: Some("x".repeat(data_size)),
            formatted_prompt: None,
            model_id: Some("test-model".to_string()),
            user_api_key: None,
            is_public: false,
            public_token: None,
            model_version: None,
            tokenizer_version: None,
            vocab_hash: None,
            sampler_preset: None,
            sampler_algo: None,
            rng_seed: None,
            max_steps: None,
            active_mod: None,
            final_tokens: None,
            final_text: Some("test output".to_string()),
            sequence_confidence: None,
            eos_reason: None,
            request_tags: serde_json::Value::Object(Default::default()),
            favorited_by: vec![],
            tags: vec![],
            events: vec![],
            mod_calls: vec![],
            mod_logs: vec![],
            actions: vec![],
            steps: vec![],
            step_logit_summaries: vec![],
            inference_stats: None,
            discussion_count: 0,
        }
    }

    #[test]
    fn test_insert_and_get() {
        let cache = LogCache::with_max_bytes(1_000_000);
        let response = make_test_response("req-1", 100);

        cache.insert("req-1".to_string(), response.clone());

        let cached = cache.get("req-1");
        assert!(cached.is_some());
        assert_eq!(cached.unwrap().request_id, "req-1");
    }

    #[test]
    fn test_cache_miss() {
        let cache = LogCache::with_max_bytes(1_000_000);

        let cached = cache.get("nonexistent");
        assert!(cached.is_none());

        let stats = cache.stats();
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hits, 0);
    }

    #[test]
    fn test_lru_eviction() {
        // Small cache that can only hold a couple entries
        let cache = LogCache::with_max_bytes(10_000);

        // Insert entries that will exceed the limit
        for i in 0..5 {
            let response = make_test_response(&format!("req-{}", i), 2000);
            cache.insert(format!("req-{}", i), response);
        }

        // Some entries should have been evicted
        assert!(cache.current_bytes() <= 10_000);
    }

    #[test]
    fn test_invalidate() {
        let cache = LogCache::with_max_bytes(1_000_000);
        let response = make_test_response("req-1", 100);

        cache.insert("req-1".to_string(), response);
        assert!(cache.get("req-1").is_some());

        let removed = cache.invalidate("req-1");
        assert!(removed);
        assert!(cache.get("req-1").is_none());
    }

    #[test]
    fn test_clear() {
        let cache = LogCache::with_max_bytes(1_000_000);

        for i in 0..10 {
            let response = make_test_response(&format!("req-{}", i), 100);
            cache.insert(format!("req-{}", i), response);
        }

        assert!(!cache.is_empty());

        cache.clear();

        assert!(cache.is_empty());
        assert_eq!(cache.current_bytes(), 0);
    }

    #[test]
    fn test_stats() {
        let cache = LogCache::with_max_bytes(1_000_000);

        cache.insert("req-1".to_string(), make_test_response("req-1", 100));
        cache.get("req-1"); // hit
        cache.get("req-2"); // miss

        let stats = cache.stats();
        assert_eq!(stats.entry_count, 1);
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hit_rate(), 50.0);
    }

    #[test]
    fn test_update_existing_entry() {
        let cache = LogCache::with_max_bytes(1_000_000);

        let response1 = make_test_response("req-1", 100);
        let response2 = make_test_response("req-1", 200);

        cache.insert("req-1".to_string(), response1);
        let bytes_after_first = cache.current_bytes();

        cache.insert("req-1".to_string(), response2);
        let bytes_after_second = cache.current_bytes();

        // Size should have changed (second entry is larger)
        assert!(bytes_after_second > bytes_after_first);

        // Should still only be one entry
        assert_eq!(cache.len(), 1);
    }
}

// ============================================================================
// Generic TTL-based Cache
// ============================================================================

/// A cache entry with expiration time
struct TtlEntry<V> {
    value: V,
    expires_at: Instant,
}

/// A generic TTL-based cache that stores values for a configurable duration.
///
/// This cache is useful for data that changes infrequently and can tolerate
/// some staleness, such as collections lists, tags, or discussions.
///
/// # Example
///
/// ```ignore
/// let cache: TtlCache<String, Vec<String>> = TtlCache::new(Duration::from_secs(60));
/// cache.insert("key".to_string(), vec!["value".to_string()]);
/// if let Some(value) = cache.get(&"key".to_string()) {
///     println!("Got: {:?}", value);
/// }
/// ```
pub struct TtlCache<K, V> {
    entries: RwLock<HashMap<K, TtlEntry<V>>>,
    ttl: Duration,
    hits: AtomicU64,
    misses: AtomicU64,
}

impl<K, V> TtlCache<K, V>
where
    K: Eq + Hash + Clone,
    V: Clone,
{
    /// Create a new TTL cache with the specified time-to-live duration.
    pub fn new(ttl: Duration) -> Self {
        Self {
            entries: RwLock::new(HashMap::new()),
            ttl,
            hits: AtomicU64::new(0),
            misses: AtomicU64::new(0),
        }
    }

    /// Get a value from the cache if it exists and hasn't expired.
    pub fn get(&self, key: &K) -> Option<V> {
        let entries = self.entries.read().unwrap();
        if let Some(entry) = entries.get(key) {
            if entry.expires_at > Instant::now() {
                self.hits.fetch_add(1, Ordering::Relaxed);
                return Some(entry.value.clone());
            }
        }
        self.misses.fetch_add(1, Ordering::Relaxed);
        None
    }

    /// Insert a value into the cache with the default TTL.
    pub fn insert(&self, key: K, value: V) {
        let mut entries = self.entries.write().unwrap();
        entries.insert(
            key,
            TtlEntry {
                value,
                expires_at: Instant::now() + self.ttl,
            },
        );
    }

    /// Insert a value with a custom TTL (useful for invalidation by setting short TTL).
    pub fn insert_with_ttl(&self, key: K, value: V, ttl: Duration) {
        let mut entries = self.entries.write().unwrap();
        entries.insert(
            key,
            TtlEntry {
                value,
                expires_at: Instant::now() + ttl,
            },
        );
    }

    /// Remove a specific key from the cache.
    pub fn invalidate(&self, key: &K) {
        let mut entries = self.entries.write().unwrap();
        entries.remove(key);
    }

    /// Clear all entries from the cache.
    pub fn clear(&self) {
        let mut entries = self.entries.write().unwrap();
        entries.clear();
    }

    /// Remove expired entries from the cache.
    /// Call this periodically to free memory.
    pub fn cleanup_expired(&self) {
        let mut entries = self.entries.write().unwrap();
        let now = Instant::now();
        entries.retain(|_, entry| entry.expires_at > now);
    }

    /// Get cache statistics.
    pub fn stats(&self) -> TtlCacheStats {
        let entries = self.entries.read().unwrap();
        let now = Instant::now();
        let valid_count = entries.values().filter(|e| e.expires_at > now).count();
        TtlCacheStats {
            entry_count: valid_count,
            total_entries: entries.len(),
            hits: self.hits.load(Ordering::Relaxed),
            misses: self.misses.load(Ordering::Relaxed),
            ttl_secs: self.ttl.as_secs(),
        }
    }
}

/// Statistics for a TTL cache.
#[derive(Debug, Clone)]
pub struct TtlCacheStats {
    /// Number of valid (non-expired) entries
    pub entry_count: usize,
    /// Total entries including expired ones not yet cleaned up
    pub total_entries: usize,
    /// Number of cache hits
    pub hits: u64,
    /// Number of cache misses
    pub misses: u64,
    /// TTL duration in seconds
    pub ttl_secs: u64,
}

impl TtlCacheStats {
    /// Calculate the hit rate as a percentage.
    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 {
            0.0
        } else {
            (self.hits as f64 / total as f64) * 100.0
        }
    }
}

#[cfg(test)]
mod ttl_cache_tests {
    use super::*;
    use std::thread::sleep;

    #[test]
    fn test_ttl_insert_and_get() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_secs(60));
        cache.insert("key1".to_string(), "value1".to_string());

        let result = cache.get(&"key1".to_string());
        assert_eq!(result, Some("value1".to_string()));
    }

    #[test]
    fn test_ttl_miss() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_secs(60));
        let result = cache.get(&"nonexistent".to_string());
        assert_eq!(result, None);
    }

    #[test]
    fn test_ttl_expiration() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_millis(50));
        cache.insert("key1".to_string(), "value1".to_string());

        // Should be present immediately
        assert!(cache.get(&"key1".to_string()).is_some());

        // Wait for expiration
        sleep(Duration::from_millis(100));

        // Should be expired now
        assert!(cache.get(&"key1".to_string()).is_none());
    }

    #[test]
    fn test_ttl_invalidate() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_secs(60));
        cache.insert("key1".to_string(), "value1".to_string());

        cache.invalidate(&"key1".to_string());

        assert!(cache.get(&"key1".to_string()).is_none());
    }

    #[test]
    fn test_ttl_cleanup() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_millis(50));
        cache.insert("key1".to_string(), "value1".to_string());
        cache.insert("key2".to_string(), "value2".to_string());

        sleep(Duration::from_millis(100));

        // Add a fresh entry
        cache.insert("key3".to_string(), "value3".to_string());

        cache.cleanup_expired();

        let stats = cache.stats();
        assert_eq!(stats.entry_count, 1); // Only key3 should remain
        assert_eq!(stats.total_entries, 1); // Expired entries should be cleaned
    }

    #[test]
    fn test_ttl_stats() {
        let cache: TtlCache<String, String> = TtlCache::new(Duration::from_secs(60));
        cache.insert("key1".to_string(), "value1".to_string());

        // One hit
        cache.get(&"key1".to_string());
        // One miss
        cache.get(&"nonexistent".to_string());

        let stats = cache.stats();
        assert_eq!(stats.hits, 1);
        assert_eq!(stats.misses, 1);
        assert_eq!(stats.hit_rate(), 50.0);
    }
}
