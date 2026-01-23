use clap::{Args, Subcommand};

use crate::config::VersionsData;

#[derive(Subcommand, Debug)]
pub enum ModCommand {
    Upload(UploadArgs),
}

#[derive(Args, Debug, Default)]
pub struct UploadArgs {
    #[arg(long)]
    url: Option<String>,
    /// User API key required by remote servers to authorize mod uploads
    #[arg(long = "user-api-key")]
    user_api_key: Option<String>,
    #[arg(long, conflicts_with = "dir")]
    file_name: Option<String>,
    #[arg(long, value_name = "PATH", conflicts_with = "file_name")]
    dir: Option<String>,
}

pub fn handle(command: ModCommand, versions: &VersionsData) -> Result<(), anyhow::Error> {
    match command {
        ModCommand::Upload(args) => handle_upload(args, versions),
    }
}

fn handle_upload(args: UploadArgs, _versions: &VersionsData) -> Result<(), anyhow::Error> {
    // Determine endpoint: default to local OpenAI-compatible server /v1/mods
    let base = args
        .url
        .unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
    let endpoint = if base.ends_with("/v1/mods") {
        base
    } else {
        let sep = if base.ends_with('/') { "" } else { "/" };
        format!("{base}{sep}v1/mods")
    };

    // Helper: extract @mod-decorated function names from a Python source string
    fn extract_mod_names(source: &str) -> Vec<String> {
        let mut names: Vec<String> = Vec::new();
        let mut pending_mod_decorator = false;
        for line in source.lines() {
            let trimmed = line.trim_start();
            if trimmed.starts_with('@') {
                if trimmed.starts_with("@mod") {
                    pending_mod_decorator = true;
                }
                continue;
            }
            if pending_mod_decorator && trimmed.starts_with("def ") {
                let rest = &trimmed["def ".len()..];
                let name: String = rest
                    .chars()
                    .take_while(|c| *c != '(' && !c.is_whitespace())
                    .collect();
                if !name.is_empty() {
                    names.push(name);
                }
                pending_mod_decorator = false;
                continue;
            }
            if trimmed.is_empty() {
                pending_mod_decorator = false;
            }
        }
        names
    }

    // Branch: directory mode vs single-file mode
    let (mod_names, mut payloads): (Vec<String>, Vec<serde_json::Value>) = if let Some(dir_str) =
        args.dir.as_ref()
    {
        // Directory mode: include all .py files and detect entrypoints in mod.py
        let dir_path = std::path::PathBuf::from(dir_str);
        if !dir_path.exists() || !dir_path.is_dir() {
            return Err(crate::error::CommandExit::with_message(
                2,
                format!(
                    "--dir does not exist or is not a directory: {}",
                    dir_path.display()
                ),
            )
            .into());
        }

        // Find mod.py within the directory (prefer root-level, otherwise unique recursive match)
        let mut mod_candidates: Vec<std::path::PathBuf> = Vec::new();
        let root_mod = dir_path.join("mod.py");
        if root_mod.exists() {
            mod_candidates.push(root_mod);
        } else {
            // Recurse to find all mod.py files
            // Use a manual stack-based DFS to avoid adding dependencies
            let mut stack = vec![dir_path.clone()];
            while let Some(p) = stack.pop() {
                let read_dir = match std::fs::read_dir(&p) {
                    Ok(rd) => rd,
                    Err(_) => continue,
                };
                for ent in read_dir.flatten() {
                    let path = ent.path();
                    if path.is_dir() {
                        stack.push(path);
                    } else if path.is_file() {
                        if let Some(name) = path.file_name().and_then(|s| s.to_str()) {
                            if name == "mod.py" {
                                mod_candidates.push(path);
                            }
                        }
                    }
                }
            }
        }

        if mod_candidates.is_empty() {
            return Err(crate::error::CommandExit::with_message(
                2,
                format!("No mod.py found under directory: {}", dir_path.display()),
            )
            .into());
        }
        if mod_candidates.len() > 1 {
            return Err(crate::error::CommandExit::with_message(
                2,
                format!(
                    "Multiple mod.py files found under directory (specify a narrower --dir):{}{}",
                    '\n',
                    mod_candidates
                        .iter()
                        .map(|p| format!("  - {}", p.display()))
                        .collect::<Vec<_>>()
                        .join("\n")
                ),
            )
            .into());
        }
        let mod_path = mod_candidates.remove(0);

        // Pick a base root for source-map keys to mirror import paths.
        // Heuristic: if an ancestor named "examples" exists, cut keys from its parent
        // so keys look like "examples/...". Otherwise, use the parent of --dir.
        fn find_named_ancestor(mut p: std::path::PathBuf, name: &str) -> Option<std::path::PathBuf> {
            loop {
                if let Some(fname) = p.file_name().and_then(|s| s.to_str()) {
                    if fname == name {
                        return Some(p);
                    }
                }
                if !p.pop() {
                    break;
                }
            }
            None
        }

        let base_root = if let Some(examples_dir) = find_named_ancestor(dir_path.clone(), "examples") {
            examples_dir.parent().map(|p| p.to_path_buf()).unwrap_or_else(|| examples_dir)
        } else {
            dir_path.parent().map(|p| p.to_path_buf()).unwrap_or_else(|| dir_path.clone())
        };

        // Compute module import path for the entry module based on path relative to base_root
        let rel_mod_path = mod_path
            .strip_prefix(&base_root)
            .unwrap_or(&mod_path)
            .to_path_buf();
        let module_name = {
            let mut s = rel_mod_path
                .with_extension("")
                .iter()
                .map(|c| c.to_string_lossy().to_string())
                .collect::<Vec<_>>()
                .join(".");
            if s.is_empty() {
                s = "mod".to_string();
            }
            s
        };

        // Gather all .py files under dir into a source map relative to the dir root
        let mut src_map: std::collections::BTreeMap<String, String> =
            std::collections::BTreeMap::new();
        let mut stack = vec![dir_path.clone()];
        while let Some(p) = stack.pop() {
            let read_dir = match std::fs::read_dir(&p) {
                Ok(rd) => rd,
                Err(_) => continue,
            };
            for ent in read_dir.flatten() {
                let path = ent.path();
                if path.is_dir() {
                    stack.push(path);
                } else if path.is_file() {
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if ext == "py" {
                            let rel = path.strip_prefix(&base_root).unwrap_or(&path).to_path_buf();
                            let key = rel
                                .components()
                                .map(|c| c.as_os_str().to_string_lossy())
                                .collect::<Vec<_>>()
                                .join("/");
                            match std::fs::read_to_string(&path) {
                                Ok(text) => {
                                    src_map.insert(key, text);
                                }
                                Err(e) => {
                                    return Err(crate::error::CommandExit::with_message(
                                        2,
                                        format!("Failed to read file {}: {}", path.display(), e),
                                    )
                                    .into());
                                }
                            }
                        }
                    }
                }
            }
        }

        // No need to remap mod.py to a package __init__.py.
        // The in-memory loader recognizes parent packages from module paths.

        // Read mod.py and detect entrypoints
        let mod_source = std::fs::read_to_string(&mod_path).map_err(|e| {
            crate::error::CommandExit::with_message(
                2,
                format!("Failed to read file {}: {}", mod_path.display(), e),
            )
        })?;
        let names = extract_mod_names(&mod_source);
        if names.is_empty() {
            return Err(crate::error::CommandExit::with_message(
                2,
                format!(
                    "No @mod-decorated functions found in {}",
                    mod_path.display()
                ),
            )
            .into());
        }

        // Build a payload for each detected entrypoint using multi-source bundle
        let payloads: Vec<serde_json::Value> = names
            .iter()
            .map(|name| {
                let src_value = serde_json::to_value(&src_map).unwrap_or(serde_json::Value::Null);
                serde_json::json!({
                    "name": name,
                    "language": "python",
                    "module": module_name,
                    "entrypoint": name,
                    "source": src_value,
                })
            })
            .collect();
        //
        (names, payloads)
    } else {
        // Single-file mode (legacy behavior)
        let file_name = match args.file_name.as_ref() {
            Some(s) => s.clone(),
            None => {
                return Err(crate::error::CommandExit::with_message(
                    2,
                    "Provide --file-name <file> or --dir <path>",
                )
                .into());
            }
        };

        // Resolve the mod file path
        let mods_dir = std::path::PathBuf::from("mods");
        let mut file_path = std::path::PathBuf::from(&file_name);
        if !file_path.exists() {
            // Try mods/<file_name>
            file_path = mods_dir.join(&file_name);
            if !file_path.exists() {
                // Try mods/<file_name>.py
                let mut fname = file_name.clone();
                if !fname.ends_with(".py") {
                    fname.push_str(".py");
                }
                let fallback = mods_dir.join(&fname);
                if fallback.exists() {
                    file_path = fallback;
                } else {
                    return Err(crate::error::CommandExit::with_message(
                        2,
                        format!(
                            "Mod file not found: {} (looked in current directory and mods/)",
                            file_name
                        ),
                    )
                    .into());
                }
            }
        }

        // Read the Python source
        let source_text = std::fs::read_to_string(&file_path).map_err(|e| {
            crate::error::CommandExit::with_message(
                2,
                format!("Failed to read file {}: {}", file_path.display(), e),
            )
        })?;

        // Extract all functions decorated with @mod
        let names = extract_mod_names(&source_text);
        if names.is_empty() {
            return Err(crate::error::CommandExit::with_message(
                2,
                format!(
                    "No @mod-decorated functions found in {}",
                    file_path.display()
                ),
            )
            .into());
        }

        // Build a payload for each detected entrypoint using single-source payload
        let payloads: Vec<serde_json::Value> = names
            .iter()
            .map(|name| {
                serde_json::json!({
                    "name": name,
                    "language": "python",
                    "module": "client_mod",
                    "entrypoint": name,
                    "source": source_text,
                })
            })
            .collect();
        (names, payloads)
    };

    // If user API key is provided, attach it to each payload (required by remote servers)
    if let Some(ref key) = args.user_api_key {
        for p in &mut payloads {
            if let Some(obj) = p.as_object_mut() {
                obj.insert("user_api_key".to_string(), serde_json::Value::String(key.clone()));
            }
        }
    } else {
        eprintln!(
            "Hint: remote servers require --user-api-key to authorize mod uploads."
        );
    }

    // POST each @mod entrypoint
    let client = reqwest::blocking::Client::new();
    let mut successes: Vec<String> = Vec::new();
    let mut failures: Vec<String> = Vec::new();

    for (i, name) in mod_names.iter().enumerate() {
        let payload = &payloads[i];
        let body_string = serde_json::to_string(payload).map_err(|e| {
            crate::error::CommandExit::with_message(
                2,
                format!("Failed to serialize payload for '{}': {}", name, e),
            )
        })?;

        let resp = match client
            .post(&endpoint)
            .header(reqwest::header::CONTENT_TYPE, "application/json")
            .body(body_string)
            .send()
        {
            Ok(r) => r,
            Err(e) => {
                failures.push(format!("{}: request failed: {}", name, e));
                continue;
            }
        };

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().unwrap_or_default();
            failures.push(format!("{}: server returned {}: {}", name, status, body));
        } else {
            successes.push(name.clone());
        }
    }

    if successes.is_empty() {
        let details = if failures.is_empty() {
            "No mods were uploaded".to_string()
        } else {
            format!(
                "No mods were uploaded.\nErrors:\n  - {}",
                failures.join("\n  - ")
            )
        };
        return Err(crate::error::CommandExit::with_message(2, details).into());
    }

    // Print summary and usage hints
    println!("Registered mods: {}", successes.join(", "));
    println!(
        "Enable a mod by appending '/<mod_name>' to your model string when calling /v1/chat/completions."
    );
    println!("If using a remote server, include your 'user_api_key' in requests.");
    println!("Example: your_model/{}", successes[0]);
    if !failures.is_empty() {
        eprintln!(
            "Some mods failed to register:\n  - {}",
            failures.join("\n  - ")
        );
    }

    Ok(())
}
