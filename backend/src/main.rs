use anyhow::Result;
use dotenvy::dotenv;

use thunder::{
    server,
    utils::{Config, telemetry},
};

#[tokio::main]
async fn main() -> Result<()> {
    dotenv().ok();
    telemetry::init_tracing();

    let config = Config::from_env()?;
    server::run(config).await?;

    Ok(())
}
