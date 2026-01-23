# concai

`concai` is the command-line companion for running Concordance locally. It bootstraps the Python SDK, installs the inference engine, and uploads mods to a running server.

## Installation

```bash
cargo install concai
```

This installs the `concai` binary into Cargo's `bin` directory. You can also run it from a checkout with `cargo run -- <command>`.

### Requirements

- [uv](https://docs.astral.sh/uv/) must be available on `PATH`. `concai` uses it to create the virtual environment and install Python wheels.
- macOS and Linux users can install `uv` with `brew install uv` or the official install script. Windows users can run `winget install astral-sh.uv`.

## Quickstart

1. **Bootstrap the project**

   ```bash
   concai init
   ```

   This installs the Concordance SDK into the managed virtualenv, writes a `.env` file (use `--env-file` to change the location), and creates a starter mod at `mods/hello_world.py`. Re-run with `--force` to overwrite existing files.

2. **Install the engine**

   ```bash
   concai engine install
   ```

   The engine is installed into `./.venv` using the wheel specified in the embedded `versions.toml`. Provide a different artifact with `concai engine install --wheel <path-or-url>`.

3. **Set up credentials**

   Update the generated `.env` with any required values (for example, set `HF_TOKEN` for gated Hugging Face downloads).

4. **Run the server**

   ```bash
   concai engine serve
   ```

   Runs the OpenAI-compatible server on `0.0.0.0:8000`. Change the host, port, or env file with `--host`, `--port`, and `--env-file`. The command exits early if the engine environment is missing; install it with the previous step.

5. **Upload mods**

   ```bash
   concai mod upload --file-name mods/hello_world.py
   # or bundle a directory
   concai mod upload --dir mods/my_project
   ```

   Entry points are detected automatically from `@mod`-decorated functions. Successful registrations are printed, along with instructions for enabling a mod via `/v1/chat/completions`.

## Command Overview

- `concai version` — prints a JSON blob containing the CLI version and the embedded release metadata.
- `concai init` — installs the SDK, scaffolds `.env`, and writes a sample mod.
- `concai engine install` — creates the engine virtualenv (if needed) and installs the engine wheel.
- `concai engine serve` — launches the local inference server using the managed virtualenv.
- `concai mod upload` — submits single-file or directory-based mods to a running server.

Use `concai <command> --help` for the complete list of flags. Advanced users can point the CLI at a different `versions.toml` by setting `CONCORD_VERSIONS_PATH` before building or running.
