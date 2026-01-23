use anyhow::Context;
use sqlx::PgPool;
use tokio::net::TcpListener;
use tracing::info;

use crate::{
    handlers::logs::warm_cache,
    routes,
    utils::{AppState, Config},
};

pub async fn run(config: Config) -> anyhow::Result<()> {
    let pool = PgPool::connect(&config.database_url)
        .await
        .context("failed to connect to Postgres")?;

    // Migrations are now handled manually via run_migration.sh
    // This gives you control over when migrations are applied
    // sqlx::migrate!("./migrations")
    //     .run(&pool)
    //     .await
    //     .context("database migration failed")?;

    let state = AppState::with_cache_size(pool, config.cache_max_bytes);

    let cache_stats = state.log_cache.stats();
    info!(
        max_cache_mb = cache_stats.max_bytes / 1_000_000,
        "Initialized log cache"
    );

    // Warm cache with the latest 50 logs
    warm_cache(&state.db_pool, &state.log_cache, 50).await;

    let app = routes::build_router(state);

    let listener = TcpListener::bind(config.bind_addr)
        .await
        .with_context(|| format!("unable to bind to {}", config.bind_addr))?;

    info!(address = %config.bind_addr, "starting Thunder backend");

    axum::serve(listener, app)
        .await
        .context("server encountered an unrecoverable error")?;

    Ok(())
}
