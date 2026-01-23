use std::{env, net::SocketAddr};

use anyhow::{Context, Result};

/// Default maximum cache size: 2.8 GB
const DEFAULT_CACHE_MAX_BYTES: u64 = 2_800_000_000;

#[derive(Debug, Clone)]
pub struct Config {
    pub bind_addr: SocketAddr,
    pub database_url: String,
    pub cache_max_bytes: u64,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let host = env::var("APP_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
        let port = env::var("APP_PORT").unwrap_or_else(|_| "6767".to_string());
        let database_url = env::var("DATABASE_URL").context("DATABASE_URL must be set")?;

        let cache_max_bytes = env::var("CACHE_MAX_BYTES")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_CACHE_MAX_BYTES);

        let port: u16 = port
            .parse()
            .with_context(|| format!("APP_PORT must be a valid u16, got {port}"))?;

        let bind_addr: SocketAddr = format!("{host}:{port}")
            .parse()
            .with_context(|| format!("failed to parse socket address from {host}:{port}"))?;

        Ok(Self {
            bind_addr,
            database_url,
            cache_max_bytes,
        })
    }
}
