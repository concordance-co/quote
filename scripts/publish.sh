#!/usr/bin/env bash

# Publish release artifacts for the Concordance monorepo.
# - Uploads Python wheels/sdists and CLI binaries to a GitHub release.
# - Publishes the Rust CLI crate to crates.io.

# Fail fast and be strict:
# -e: exit on error
# -u: error on unset variables
# -o pipefail: pipeline fails if any command fails
set -euo pipefail

# Resolve important paths relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # directory containing this script
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"                # repo root (one level up from scripts/)
ARTIFACT_ROOT="${REPO_ROOT}/artifacts"                     # where build artifacts are expected

# Allow overriding tool executables via env vars; default to gh/cargo on PATH
GH_BIN="${GH_BIN:-gh}"
CARGO_BIN="${CARGO_BIN:-cargo}"

# Feature flags and configuration
DRY_RUN=false            # if true, print commands instead of executing
UPLOAD_TO_GH=true        # if true, upload artifacts to GitHub release
PUBLISH_CLI_CRATE=true   # if true, publish CLI crate to crates.io
GITHUB_TAG=""            # GitHub release tag to upload to (e.g., v1.2.3)

# Components explicitly requested by CLI flags
declare -a REQUESTED_COMPONENTS=()

# All supported components and the order they should be processed
ALL_COMPONENTS=(shared sdk engine cli)
ORDERED_COMPONENTS=(shared sdk engine cli)

# Derived requirements (set later based on flags/components)
NEEDS_GH=false
NEEDS_CARGO=false

# Print CLI usage/help text
usage() {
  cat <<'EOF'
Usage: scripts/publish.sh [options]

Options:
  --component <name>   Component to publish (shared|sdk|engine|cli). Repeatable.
  --all                Publish every component (default when no component is given).
  --tag <tag>          GitHub release tag (default: v<release_version> from versions.toml).
  --skip-gh            Skip uploading artifacts to GitHub.
  --skip-crates        Skip publishing the CLI crate to crates.io.
  --dry-run            Print commands without executing them.
  --help               Show this message.

Environment variables:
  GH_BIN               Override the gh executable (default: gh).
  CARGO_BIN            Override the cargo executable (default: cargo).
EOF
}

# Standard log helpers
log() {
  printf '[publish] %s\n' "$*"
}

warn() {
  printf '[publish][warn] %s\n' "$*" >&2
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

# Run a command, respecting DRY_RUN
run_cmd() {
  local -a cmd=("$@")
  if $DRY_RUN; then
    printf '[dry-run] %s\n' "${cmd[*]}"
    return 0
  fi
  "${cmd[@]}"
}

# Run a command in a specific directory, respecting DRY_RUN
run_in_dir() {
  local dir="$1"
  shift
  local -a cmd=("$@")
  if $DRY_RUN; then
    printf '[dry-run] (cd %s && %s)\n' "$dir" "${cmd[*]}"
    return 0
  fi
  (cd "$dir" && "${cmd[@]}")
}

# Normalize user-provided component aliases to canonical names
normalize_component() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"  # case-insensitive
  case "$raw" in
    shared) echo "shared" ;;
    sdk) echo "sdk" ;;
    engine | inference) echo "engine" ;;  # support alias "inference"
    cli | concai) echo "cli" ;;           # support alias "concai"
    *)
      die "unknown component: ${raw}"
      ;;
  esac
}

# Add a component to REQUESTED_COMPONENTS if not already present
add_component() {
  local comp="$1"
  for existing in "${REQUESTED_COMPONENTS[@]:-}"; do
    if [[ "$existing" == "$comp" ]]; then
      return  # avoid duplicates
    fi
  done
  REQUESTED_COMPONENTS+=("$comp")
}

# If no --tag provided, derive release tag from versions.toml (release_version)
derive_tag_from_versions() {
  local versions_file="${REPO_ROOT}/versions.toml"
  if [[ ! -f "$versions_file" ]]; then
    return 0
  fi
  local version_line
  # Find the line like: release_version = "1.2.3"
  version_line="$(grep -E '^release_version = ' "$versions_file" | head -n1 || true)"
  if [[ -z "$version_line" ]]; then
    return 0
  fi
  local version
  # Extract the quoted version portion
  version="$(echo "$version_line" | sed -E 's/[^"]*"([^"]+)".*/\1/' | xargs)"
  if [[ -n "$version" ]]; then
    GITHUB_TAG="v${version}"  # tag uses v-prefix convention
  fi
}

# Parse CLI flags and set up global state accordingly
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --component|-c)
        [[ $# -lt 2 ]] && die "--component requires a value"
        shift
        add_component "$(normalize_component "$1")"  # add normalized component
        ;;
      --all)
        REQUESTED_COMPONENTS=("${ALL_COMPONENTS[@]}")  # select everything
        ;;
      --tag)
        [[ $# -lt 2 ]] && die "--tag requires a value"
        shift
        GITHUB_TAG="$1"  # explicit GitHub release tag
        ;;
      --skip-gh)
        UPLOAD_TO_GH=false  # disable GitHub uploads
        ;;
      --skip-crates)
        PUBLISH_CLI_CRATE=false  # disable crates.io publish
        ;;
      --dry-run)
        DRY_RUN=true  # print commands only
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "unknown option: $1"
        ;;
    esac
    shift
  done

  # Default to all components if none were specified
  if [[ ${#REQUESTED_COMPONENTS[@]} -eq 0 ]]; then
    REQUESTED_COMPONENTS=("${ALL_COMPONENTS[@]}")
  fi

  # Ensure shared artifacts accompany sdk/engine uploads (dependency)
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    if [[ "$comp" == "sdk" || "$comp" == "engine" ]]; then
      add_component "shared"
    fi
  done

  # Attempt to infer a tag if none provided
  if [[ -z "$GITHUB_TAG" ]]; then
    derive_tag_from_versions
  fi

  # If we're uploading to GitHub, we must have a tag resolved by now
  if $UPLOAD_TO_GH && [[ -z "$GITHUB_TAG" ]]; then
    die "--tag is required (or ensure versions.toml has release_version)"
  fi
}

# Decide which external tools are needed and verify they exist
calculate_requirements() {
  NEEDS_GH=false
  NEEDS_CARGO=false
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    case "$comp" in
      shared|sdk|engine)
        if $UPLOAD_TO_GH; then
          NEEDS_GH=true
        fi
        ;;
      cli)
        if $UPLOAD_TO_GH; then
          NEEDS_GH=true
        fi
        if $PUBLISH_CLI_CRATE; then
          NEEDS_CARGO=true
        fi
        ;;
    esac
  done

  # Validate tool availability early for faster feedback
  if $NEEDS_GH; then
    if ! command -v "$GH_BIN" >/dev/null 2>&1; then
      die "required command not found: ${GH_BIN}"
    fi
  fi
  if $NEEDS_CARGO; then
    if ! command -v "$CARGO_BIN" >/dev/null 2>&1; then
      die "required command not found: ${CARGO_BIN}"
    fi
  fi
}

# Check if a component is in the selected set
component_selected() {
  local target="$1"
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    if [[ "$comp" == "$target" ]]; then
      return 0
    fi
  done
  return 1
}

# Compute the artifact directory path for a given component
artifact_dir_for() {
  local comp="$1"
  printf '%s/%s' "$ARTIFACT_ROOT" "$comp"
}

# Upload every file in a component's artifact directory to the GitHub release
gh_upload_dir() {
  local comp="$1"
  local dir
  dir="$(artifact_dir_for "$comp")"
  if [[ ! -d "$dir" ]]; then
    warn "[${comp}] artifact directory not found: ${dir}"
    return
  fi
  local found=false
  # Iterate all files (non-recursive) in the directory and upload each
  while IFS= read -r -d '' file; do
    found=true
    log "[${comp}] uploading $(basename "$file") to ${GITHUB_TAG}"
    run_cmd "$GH_BIN" release upload "$GITHUB_TAG" "$file" --clobber  # --clobber replaces existing assets
  done < <(find "$dir" -maxdepth 1 -type f -print0)
  if ! $found; then
    warn "[${comp}] no files found in ${dir}"
  fi
}

# Publisher for the "shared" component (typically common artifacts)
publish_shared() {
  if $UPLOAD_TO_GH; then
    gh_upload_dir "shared"
  else
    log "[shared] GitHub upload skipped"
  fi
}

# Publisher for the "sdk" component
publish_sdk() {
  if $UPLOAD_TO_GH; then
    gh_upload_dir "sdk"
  else
    log "[sdk] GitHub upload skipped"
  fi
}

# Publisher for the "engine" component
publish_engine() {
  if $UPLOAD_TO_GH; then
    gh_upload_dir "engine"
  else
    log "[engine] GitHub upload skipped"
  fi
}

# Publisher for the "cli" component (uploads binaries and optionally publishes crate)
publish_cli() {
  # Upload CLI binaries/assets to GitHub release
  if $UPLOAD_TO_GH; then
    gh_upload_dir "cli"
  fi

  # Optionally publish the Rust crate to crates.io
  if $PUBLISH_CLI_CRATE; then
    local comp_dir="${REPO_ROOT}/cli"
    local versions_src="${REPO_ROOT}/versions.toml"
    local versions_dest="${comp_dir}/versions.toml"

    # Ensure versions.toml exists and matches between root and cli/ (to keep versions in sync)
    if [[ ! -f "$versions_src" ]]; then
      log "[cli] error: source versions.toml not found at ${versions_src}"
      return 1
    fi
    if [[ ! -f "$versions_dest" ]]; then
      log "[cli] error: cli/versions.toml missing. Sync versions before publishing."
      return 1
    fi
    if ! cmp -s "$versions_src" "$versions_dest"; then
      log "[cli] error: versions.toml files differ. Sync root and cli copies before publishing."
      return 1
    fi

    log "[cli] publishing crate to crates.io"
    # Use cargo publish; in dry-run mode ask cargo to perform a dry publish
    if $DRY_RUN; then
      run_in_dir "$comp_dir" "$CARGO_BIN" publish --dry-run
    else
      run_in_dir "$comp_dir" "$CARGO_BIN" publish
    fi
  else
    log "[cli] crates.io publish skipped"
  fi
}

# Wrapper to call the appropriate publish_* function for a component
process_component() {
  local comp="$1"
  log "----- ${comp} -----"
  "publish_${comp}"
}

# Program entry point
main() {
  parse_args "$@"          # interpret CLI flags and populate globals
  calculate_requirements   # figure out which tools we need and validate them

  # Summarize the plan
  if $UPLOAD_TO_GH; then
    log "Uploading to GitHub release tag: ${GITHUB_TAG}"
  else
    log "GitHub uploads disabled (--skip-gh)"
  fi
  if $PUBLISH_CLI_CRATE; then
    log "CLI crate publish enabled"
  else
    log "CLI crate publish disabled (--skip-crates)"
  fi
  if $DRY_RUN; then
    log "dry run enabled – commands will be printed only"
  fi

  # Process components in a fixed, sensible order
  for comp in "${ORDERED_COMPONENTS[@]}"; do
    if component_selected "$comp"; then
      process_component "$comp"
    fi
  done

  log "publish pipeline complete"
}

# Kick things off, forwarding all CLI args
main "$@"
