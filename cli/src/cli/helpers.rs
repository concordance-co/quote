use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus};

use anyhow::{Context, Result};

use crate::config::Versions;
use crate::error::CommandExit;

pub const ENGINE_HOME_SUFFIX: &str = "./.venv";
pub const DEFAULT_ENGINE_INDEXES: &[&str] = &["https://modular.gateway.scarf.sh/simple/"];

pub fn detect_engine_python(version: &str) -> Result<Option<PathBuf>> {
    let env_dir = engine_env_dir(version)?;
    if !env_dir.exists() {
        return Ok(None);
    }

    let python_path = if cfg!(windows) {
        env_dir.join("Scripts").join("python.exe")
    } else {
        env_dir.join("bin").join("python")
    };

    if python_path.exists() {
        Ok(Some(python_path))
    } else {
        Ok(None)
    }
}

pub fn create_engine_venv(version: &str) -> Result<PathBuf> {
    let env_dir = engine_env_dir(version)?;
    let uv = find_uv()?;

    std::fs::create_dir_all(&env_dir)
        .with_context(|| format!("Failed to create {}", env_dir.display()))?;

    println!(
        "Creating engine virtualenv with uv at {}",
        env_dir.display()
    );
    let status = std::process::Command::new(&uv)
        .args(["venv", env_dir.to_string_lossy().as_ref(), "--seed"])
        .status()
        .with_context(|| format!("Failed to spawn {}", uv.display()))?;
    if !status.success() {
        return Err(crate::error::CommandExit::with_message(
            status.code().unwrap_or(1),
            "Failed to create virtualenv with uv.",
        )
        .into());
    }

    detect_engine_python(version)?.ok_or_else(|| {
        crate::error::CommandExit::with_message(1, "Failed to locate python in engine virtualenv.")
            .into()
    })
}

pub fn install_python_package(
    uv: &Path,
    python_or_venv: &Path,
    spec: &str,
    extra_indexes: &[String],
) -> Result<()> {
    let mut cmd = Command::new(uv);
    cmd.arg("pip")
        .arg("install")
        .arg("--python")
        .arg(python_or_venv)
        .arg(spec);
    for idx in extra_indexes {
        cmd.arg("--extra-index-url").arg(idx);
    }

    println!(
        "$ {} pip install --python {} {}{}",
        uv.display(),
        python_or_venv.display(),
        spec,
        if extra_indexes.is_empty() {
            "".to_string()
        } else {
            format!(
                " --extra-index-url {}",
                extra_indexes.join(" --extra-index-url ")
            )
        }
    );

    let status = cmd
        .status()
        .with_context(|| "Failed to run uv pip install")?;

    if !status.success() {
        return Err(command_failure(
            &[format!(
                "uv pip install --python {} {}",
                python_or_venv.display(),
                spec
            )],
            status,
        ));
    }
    Ok(())
}

pub fn command_failure(cmd: &[String], status: ExitStatus) -> anyhow::Error {
    let code = status.code().unwrap_or(1);
    CommandExit::with_message(
        code,
        format!("Command `{}` failed with exit code {}", cmd.join(" "), code),
    )
    .into()
}

pub fn engine_env_dir(_version: &str) -> Result<PathBuf> {
    Ok(ENGINE_HOME_SUFFIX.into())
}

pub fn engine_extra_indexes(versions: &Versions) -> Vec<String> {
    if let Some(indexes) = &versions.engine.extra_indexes
        && !indexes.is_empty()
    {
        return indexes.clone();
    }

    DEFAULT_ENGINE_INDEXES
        .iter()
        .map(|value| value.to_string())
        .collect()
}

pub fn find_uv() -> anyhow::Result<std::path::PathBuf> {
    which::which("uv").map_err(|_| {
        crate::error::CommandExit::with_message(
            127,
            "uv was not found on PATH. Install it:\n  - macOS: brew install uv\n  - Linux/macOS: curl -LsSf https://astral.sh/uv/install.sh | sh\n  - Windows: winget install astral-sh.uv",
        ).into()
    })
}

pub fn load_env_file(path: &Path) -> Result<HashMap<String, String>> {
    let mut env_map = HashMap::new();
    if !path.exists() {
        return Ok(env_map);
    }

    let contents =
        fs::read_to_string(path).with_context(|| format!("Failed to read {}", path.display()))?;
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }

        if let Some((key, value)) = trimmed.split_once('=') {
            env_map.insert(
                key.trim().to_string(),
                value.trim().trim_matches('"').to_string(),
            );
        }
    }

    Ok(env_map)
}

pub fn engine_version(versions: &Versions) -> String {
    versions
        .engine
        .version
        .clone()
        .unwrap_or_else(|| "0.0.0".to_string())
}
