use std::process::Command;

use crate::cli::helpers::{
    create_engine_venv, detect_engine_python, engine_env_dir, engine_extra_indexes, engine_version,
    find_uv, install_python_package, load_env_file,
};
use crate::cli::{EngineCommand, EngineInstallArgs, EngineServeArgs};
use crate::config::VersionsData;
use crate::error::CommandExit;
use anyhow::{Context, Result};

pub const DEFAULT_ENV_FILE: &str = ".env";

pub fn handle(command: EngineCommand, versions: &VersionsData) -> Result<()> {
    match command {
        EngineCommand::Install(args) => handle_install(args, versions),
        EngineCommand::Serve(args) => handle_serve(args, versions),
    }
}

fn handle_install(args: EngineInstallArgs, versions: &VersionsData) -> Result<()> {
    let version = engine_version(&versions.parsed);

    let mut python_path = detect_engine_python(&version)?;
    if python_path.is_none() {
        python_path = Some(create_engine_venv(&version)?);
    }
    let python_path = python_path.expect("engine python path must exist after creation");
    let uv = find_uv()?;

    let wheel_spec = args
        .wheel
        .clone()
        .or_else(|| versions.parsed.engine.wheel_url.clone())
        .ok_or_else(|| {
            CommandExit::with_message(
                2,
                "No wheel specified and no wheel_url found in versions.toml",
            )
        })?;

    let extra_indexes = engine_extra_indexes(&versions.parsed);

    println!("Installing engine from {}", wheel_spec);
    install_python_package(uv.as_path(), &python_path, &wheel_spec, &extra_indexes)?;

    println!(
        "Engine installed at {}",
        engine_env_dir(&version)?.display()
    );
    Ok(())
}

fn handle_serve(args: EngineServeArgs, versions: &VersionsData) -> Result<()> {
    let version = engine_version(&versions.parsed);
    let python_path = detect_engine_python(&version)?;

    if python_path.is_none() {
        return Err(CommandExit::with_message(
            1,
            "Engine environment missing; please run `concai engine install` first.",
        )
        .into());
    }

    let python_path = python_path.expect("python path available after check");
    let mut env_vars = load_env_file(&args.env_file)?;

    let concai_model = env_vars.get("CONCAI_MODEL_ID").cloned().unwrap_or_default();
    env_vars
        .entry("MODEL_ID".to_string())
        .or_insert(concai_model);

    if !env_vars.contains_key("HF_TOKEN") {
        env_vars.insert("HF_TOKEN".to_string(), String::new());
    }

    if !env_vars.contains_key("PORT") {
        env_vars.insert("PORT".to_string(), args.port.to_string());
    }

    if env_vars.get("PORT").map(|v| v.is_empty()).unwrap_or(true) {
        env_vars.insert("PORT".to_string(), args.port.to_string());
    }

    let huggingface_empty = env_vars
        .get("HF_TOKEN")
        .map(|v| v.is_empty())
        .unwrap_or(true);

    if huggingface_empty {
        eprintln!("HF_TOKEN is empty; set it in .env to enable gated model downloads.");
    }

    let filtered_env: Vec<(String, String)> = env_vars
        .into_iter()
        .filter(|(_, value)| !value.is_empty())
        .collect();

    let uv = find_uv()?;
    let mut command = Command::new(&uv);
    command
        .arg("run")
        .arg("--python")
        .arg(&python_path)
        .arg("-m")
        .arg("quote.server.openai.local")
        .arg("--host")
        .arg(&args.host)
        .arg("--port")
        .arg(args.port.to_string());

    command.envs(filtered_env.iter().map(|(k, v)| (k, v)));

    let display_cmd = format!(
        "{} run --python {} -m quote.server.openai.local --host {} --port {}",
        uv.display(),
        python_path.display(),
        args.host,
        args.port
    );
    println!("$ {}", display_cmd);

    let status = command
        .status()
        .with_context(|| "Failed to start engine process")?;
    if !status.success() {
        return Err(CommandExit::with_message(
            status.code().unwrap_or(1),
            "Engine process exited with a non-zero status.",
        )
        .into());
    }

    Ok(())
}
