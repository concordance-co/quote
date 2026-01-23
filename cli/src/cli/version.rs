use anyhow::Result;
use serde_json::json;

use crate::config::VersionsData;

pub fn handle(data: &VersionsData) -> Result<()> {
    let payload = json!({
        "cli_version": env!("CARGO_PKG_VERSION"),
        "versions": data.json.clone()
    });
    println!("{}", serde_json::to_string_pretty(&payload)?);
    Ok(())
}
