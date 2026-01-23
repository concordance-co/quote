# Build & Publish Helpers

The scripts in this directory orchestrate builds/tests and publishing for the components we currently ship (shared libs, SDK, inference engine, Rust CLI).

## TLDR

1. Main should always be the current release and ready to rip.
2. Merge changes into main once confirmed good.
3. Update version numbers in every `versions.toml` and `pyproject.toml` file.
4. Create a new github release in concordance-artifacts if relevant -- if not updating full release (just individual components, probably don't have to do this).
5. `rm -rf artifacts/*` to clear all the old artifacts (they are saved in github releases, so this is safe).
6. Run the build script: `bash scripts/build.sh` (use flags to specify individual components or to skip tests).
7. Run the publish script: `GH_REPO=your-org/concordance-artifacts bash scripts/publish.sh --tag <tag>` (use flags to specify individual components as well).

Theoretically, this should be the whole flow for now.

## Notes -- Versioning

Make sure to check all tomls and version values/names and that they align before running scripts.

Make sure to clear the artifacts repo before building (they don't get overwritten).

Use this as the build process: `GH_REPO=your-org/concordance-artifacts bash scripts/publish.sh --tag v0.4.0`

## Prerequisites

- `uv` for building Python packages and running tests.
- `cargo` for the Rust CLI.
- `gh` (optional) for uploading GitHub release artifacts when using `publish.sh`.
- (Optional) set `UV_BIN`, `CARGO_BIN`, or `GH_BIN` to point at custom executables.

## Build (`build.sh`)

```bash
# run all components (default when no component flags are provided)
scripts/build.sh

# dry-run to inspect the commands that would execute
scripts/build.sh --dry-run
```

Artifacts land under `./artifacts/<component>/` in the repo root.

The CLI build will abort if `versions.toml` in the repo root and `cli/` differ, so keep them synced before running the script.

### Selecting Components

```bash
# only SDK and CLI
scripts/build.sh --component sdk --component cli

# shorthand for everything
scripts/build.sh --all
```

Choosing `sdk` or `engine` automatically includes `shared`, since the builds depend on it.

### Skipping Phases

```bash
scripts/build.sh --component engine --skip-test        # build + publish only
scripts/build.sh --component cli --skip-build --dry-run # print test/publish commands
```

If a phase is skipped, the script logs that fact and moves to the next one.

### Output

- Python packages: wheels and sdists copied to `artifacts/shared/`, `artifacts/sdk/`, `artifacts/engine/`.
- CLI: release binary plus the `.crate` tarball in `artifacts/cli/`.
- Logs identify each stage; dry runs are prefixed with `[dry-run]`.

## Publish (`publish.sh`)

`publish.sh` pushes built artifacts to their distribution targets:

```bash
# upload Python wheels/sdists to a GitHub release and publish the CLI crate
scripts/publish.sh --tag v0.3.0

# publish a subset
scripts/publish.sh --tag v0.3.0 --component sdk --component cli

# inspect without executing
scripts/publish.sh --tag v0.3.0 --dry-run
```

By default the script uploads the contents of `./artifacts/<component>/` to the specified GitHub release tag using the `gh` CLI. Publishing the CLI uses `cargo publish`. Set `--all` to publish every component, or combine `--skip-gh` / `--skip-crates` to turn off either destination.

### Publish prerequisites

- `build.sh` must have already populated `./artifacts`.
- `gh` CLI authenticated with permissions to upload release assets.
- `cargo` credentials configured for crates.io publishing.
