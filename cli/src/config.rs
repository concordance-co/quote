use anyhow::{Context, Result};
use serde::Deserialize;
use serde_json::Value as JsonValue;

// VERSIONS -- Single source of truth copied into OUT_DIR via build.rs
const EMBEDDED_VERSIONS: &str = include_str!(concat!(env!("OUT_DIR"), "/versions.toml"));

#[derive(Debug, Clone, Deserialize)]
pub struct Versions {
    #[serde(default = "default_release_version")]
    pub release_version: String,
    #[serde(default)]
    pub engine: EngineConfig,
    #[serde(default)]
    pub sdk: SDKConfig,
    #[serde(default)]
    pub shared: SharedConfig,
}

fn default_release_version() -> String {
    "0.0.0".to_string()
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct SharedConfig {
    #[serde(default, rename = "package")]
    pub _package: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub wheel_url: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct SDKConfig {
    #[serde(default, rename = "package")]
    pub _package: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub wheel_url: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct EngineConfig {
    #[serde(default, rename = "package")]
    pub _package: Option<String>,
    #[serde(default)]
    pub version: Option<String>,
    #[serde(default)]
    pub wheel_url: Option<String>,
    #[serde(default)]
    pub extra_indexes: Option<Vec<String>>,
}

pub struct VersionsData {
    pub json: JsonValue,
    pub parsed: Versions,
}

pub fn load_versions_data() -> Result<VersionsData> {
    let text = EMBEDDED_VERSIONS.to_string();

    let toml_value: toml::Value =
        toml::from_str(&text).with_context(|| "Failed to parse versions.toml")?;
    let parsed: Versions = toml_value
        .clone()
        .try_into()
        .with_context(|| "Failed to deserialize versions manifest")?;
    let json =
        serde_json::to_value(toml_value).expect("versions manifest should serialize to JSON");

    Ok(VersionsData { json, parsed })
}
