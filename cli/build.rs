use std::env;
use std::error::Error;
use std::fs;
use std::path::PathBuf;

fn main() -> Result<(), Box<dyn Error>> {
    let out_dir = PathBuf::from(env::var("OUT_DIR")?);
    let manifest_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR")?);

    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(custom) = env::var("CONCORD_VERSIONS_PATH") {
        candidates.push(PathBuf::from(custom));
    }

    candidates.push(manifest_dir.join("../versions.toml"));
    candidates.push(manifest_dir.join("versions.toml"));

    let source = candidates
        .iter()
        .find(|p| p.is_file())
        .cloned()
        .ok_or_else(|| {
            format!(
                "Unable to locate versions.toml. Looked in:\n{}",
                candidates
                    .iter()
                    .map(|p| format!(" - {}", p.display()))
                    .collect::<Vec<_>>()
                    .join("\n")
            )
        })?;

    fs::create_dir_all(&out_dir)?;
    let dest = out_dir.join("versions.toml");
    fs::copy(&source, &dest)?;

    println!("cargo:rerun-if-env-changed=CONCORD_VERSIONS_PATH");
    println!("cargo:rerun-if-changed={}", source.display());

    Ok(())
}
