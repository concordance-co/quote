use std::path::PathBuf;

use anyhow::Result;
use clap::{Args, Parser, Subcommand};

use crate::{
    cli::{engine::DEFAULT_ENV_FILE, mod_commands::ModCommand},
    config::load_versions_data,
};

mod engine;
mod helpers;
mod init;
mod mod_commands;
mod version;

// use engine::EngineCommand;
#[derive(Args, Debug)]
pub struct InitArgs {
    #[arg(long = "env-file", default_value = DEFAULT_ENV_FILE)]
    env_file: PathBuf,
    #[arg(long, short = 'F')]
    force: bool,
}

#[derive(Subcommand, Debug)]
pub enum EngineCommand {
    Install(EngineInstallArgs),
    Serve(EngineServeArgs),
}

#[derive(Args, Debug, Default)]
pub struct SDKInstallArgs {
    #[arg(long)]
    wheel: Option<String>,
}

#[derive(Args, Debug, Default)]
pub struct EngineInstallArgs {
    #[arg(long)]
    wheel: Option<String>,
}

#[derive(Args, Debug)]
pub struct EngineServeArgs {
    #[arg(long, default_value = "0.0.0.0")]
    host: String,
    #[arg(long, default_value_t = 8000)]
    port: u16,
    #[arg(long = "env-file", default_value = DEFAULT_ENV_FILE)]
    env_file: PathBuf,
    #[arg(long)]
    wheel: Option<String>,
    #[arg(long = "no-install")]
    no_install: bool,
}

#[derive(Parser, Debug)]
#[command(name = "concai")]
#[command(about = "Utilities for installing and running Concordance locally.")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    Version,
    Init(InitArgs),
    #[command(subcommand)]
    Engine(EngineCommand),
    #[command(subcommand)]
    Mod(ModCommand),
}

pub fn run() -> Result<()> {
    let cli = Cli::parse();
    let versions = load_versions_data()?;

    match cli.command {
        Commands::Version => version::handle(&versions),
        Commands::Init(args) => init::handle(args, &versions),
        Commands::Engine(cmd) => engine::handle(cmd, &versions),
        Commands::Mod(cmd) => mod_commands::handle(cmd, &versions),
    }
}
