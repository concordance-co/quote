#!/usr/bin/env bash

# Lightweight build helper for the Concordance monorepo.
# The script provides three phases (build, test, publish) for the selected components
# and drops resulting artifacts under ./artifacts/<component>/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ARTIFACT_ROOT="${REPO_ROOT}/artifacts"

UV_BIN="${UV_BIN:-uv}"
CARGO_BIN="${CARGO_BIN:-cargo}"

DO_BUILD=true
DO_TEST=true
DO_PUBLISH=true
DRY_RUN=false

# Holds the list of components explicitly requested via CLI (in insertion order).
# Starts empty; parse_args populates it (defaults to ALL_COMPONENTS if none specified).
declare -a REQUESTED_COMPONENTS=()

ALL_COMPONENTS=(shared sdk engine cli)
ORDERED_COMPONENTS=(shared sdk engine cli)
NEEDS_UV=false
NEEDS_CARGO=false

usage() {
  cat <<'EOF'
Usage: scripts/build.sh [options]

Options:
  --component <name>   Component to process (shared|sdk|engine|cli). Repeatable.
  --all                Process every component (default when no component is given).
  --skip-build         Skip the build phase.
  --skip-test          Skip the test phase.
  --skip-publish       Skip the publish phase.
  --dry-run            Print commands without executing them.
  --help               Show this message.

Environment variables:
  UV_BIN               Override the uv executable (default: uv).
  CARGO_BIN            Override the cargo executable (default: cargo).
EOF
}

log() {
  printf '[build] %s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  local bin="$1"
  if ! command -v "$bin" >/dev/null 2>&1; then
    die "required command not found: ${bin}"
  fi
}

run_cmd() {
  local -a cmd=("$@")
  if $DRY_RUN; then
    printf '[dry-run] %s\n' "${cmd[*]}"
    return 0
  fi
  "${cmd[@]}"
}

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

normalize_component() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$raw" in
    shared) echo "shared" ;;
    sdk) echo "sdk" ;;
    engine | inference) echo "engine" ;;
    cli | concai) echo "cli" ;;
    *)
      die "unknown component: ${raw}"
      ;;
  esac
}

add_component() {
  local comp="$1"
  for existing in "${REQUESTED_COMPONENTS[@]:-}"; do
    if [[ "$existing" == "$comp" ]]; then
      return
    fi
  done
  REQUESTED_COMPONENTS+=("$comp")
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --component|-c)
        [[ $# -lt 2 ]] && die "--component requires a value"
        shift
        add_component "$(normalize_component "$1")"
        ;;
      --all)
        REQUESTED_COMPONENTS=("${ALL_COMPONENTS[@]}")
        ;;
      --skip-build)
        DO_BUILD=false
        ;;
      --skip-test)
        DO_TEST=false
        ;;
      --skip-publish)
        DO_PUBLISH=false
        ;;
      --dry-run)
        DRY_RUN=true
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

  if [[ ${#REQUESTED_COMPONENTS[@]} -eq 0 ]]; then
    REQUESTED_COMPONENTS=("${ALL_COMPONENTS[@]}")
  fi

  # Ensure shared builds when sdk or engine are selected.
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    if [[ "$comp" == "sdk" || "$comp" == "engine" ]]; then
      add_component "shared"
    fi
  done
}

calculate_tool_requirements() {
  NEEDS_UV=false
  NEEDS_CARGO=false
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    case "$comp" in
      shared|sdk|engine)
        NEEDS_UV=true
        ;;
      cli)
        NEEDS_CARGO=true
        ;;
    esac
  done
  if $NEEDS_UV; then
    require_cmd "$UV_BIN"
  fi
  if $NEEDS_CARGO; then
    require_cmd "$CARGO_BIN"
  fi
}

prepare_workspace() {
  mkdir -p "${ARTIFACT_ROOT}"
  if $DRY_RUN; then
    log "dry run enabled – commands will be printed only"
  fi
}

component_selected() {
  local target="$1"
  for comp in "${REQUESTED_COMPONENTS[@]}"; do
    if [[ "$comp" == "$target" ]]; then
      return 0
    fi
  done
  return 1
}

artifact_dir_for() {
  local comp="$1"
  printf '%s/%s' "$ARTIFACT_ROOT" "$comp"
}

# -----------------------
# Component: shared (Python library)
# -----------------------

build_shared() {
  local comp_dir="${REPO_ROOT}/engine/shared"
  local out_dir
  out_dir="$(artifact_dir_for shared)"
  mkdir -p "$out_dir"
  log "[shared] building wheel and sdist"
  run_in_dir "$comp_dir" "$UV_BIN" build --wheel --sdist --out-dir "$out_dir"
}

test_shared() {
  local comp_dir="${REPO_ROOT}/engine/shared"
  if [[ ! -d "${comp_dir}/tests" ]]; then
    log "[shared] skipping tests (no tests directory)"
    return
  fi
  log "[shared] running tests"
  run_in_dir "$comp_dir" "$UV_BIN" run pytest
}

publish_shared() {
  log "[shared] artifacts staged in $(artifact_dir_for shared)"
}

# -----------------------
# Component: sdk (Python package)
# -----------------------

build_sdk() {
  local comp_dir="${REPO_ROOT}/engine/sdk"
  local out_dir
  out_dir="$(artifact_dir_for sdk)"
  mkdir -p "$out_dir"
  log "[sdk] building wheel and sdist"
  # run_in_dir "$comp_dir" "$UV_BIN" build --wheel --sdist --out-dir "$out_dir"
  run_in_dir "$comp_dir" "$UV_BIN" build --out-dir "$out_dir"

}

test_sdk() {
  local comp_dir="${REPO_ROOT}/engine/sdk"
  local tests_path="${REPO_ROOT}/engine/tests/sdk"
  if [[ ! -d "${REPO_ROOT}/engine/tests/sdk" ]]; then
    log "[sdk] skipping tests (no engine/tests/sdk directory)"
    return
  fi
  log "[sdk] running pytest on ${tests_path}"
  run_in_dir "$comp_dir" "$UV_BIN" run pytest "$tests_path"
}

publish_sdk() {
  log "[sdk] artifacts staged in $(artifact_dir_for sdk)"
}

# -----------------------
# Component: engine (Python inference package)
# -----------------------

build_engine() {
  local comp_dir="${REPO_ROOT}/engine/inference"
  local out_dir
  out_dir="$(artifact_dir_for engine)"
  mkdir -p "$out_dir"
  log "[engine] building wheel and sdist"
  run_in_dir "$comp_dir" "$UV_BIN" build --wheel --sdist --out-dir "$out_dir"
}

test_engine() {
  local comp_dir="${REPO_ROOT}/engine/inference"
  local tests_path="${REPO_ROOT}/engine/tests/inference"
  if [[ ! -d "${REPO_ROOT}/engine/tests/inference" ]]; then
    log "[engine] skipping tests (no engine/tests/inference directory)"
    return
  fi
  log "[engine] running pytest on ${tests_path}"
  run_in_dir "$comp_dir" "$UV_BIN" run pytest "$tests_path"
}

publish_engine() {
  log "[engine] artifacts staged in $(artifact_dir_for engine)"
}

# -----------------------
# Component: cli (Rust crate)
# -----------------------

build_cli() {
  local comp_dir="${REPO_ROOT}/cli"
  log "[cli] building release binary"
  run_in_dir "$comp_dir" "$CARGO_BIN" build --release --locked
}

test_cli() {
  local comp_dir="${REPO_ROOT}/cli"
  log "[cli] running cargo test"
  run_in_dir "$comp_dir" "$CARGO_BIN" test --locked
}

publish_cli() {
  local comp_dir="${REPO_ROOT}/cli"
  local out_dir
  out_dir="$(artifact_dir_for cli)"
  mkdir -p "$out_dir"
  log "[cli] copying release binary to artifacts directory"
  if [[ -f "${comp_dir}/target/release/concai" ]]; then
    run_cmd cp -f "${comp_dir}/target/release/concai" "${out_dir}/concai"
  else
    log "[cli] warning: release binary not found (expected ${comp_dir}/target/release/concai)"
  fi

  local versions_src="${REPO_ROOT}/versions.toml"
  local versions_dest="${comp_dir}/versions.toml"
  if [[ ! -f "$versions_src" ]]; then
    log "[cli] error: source versions.toml not found at ${versions_src}"
    return 1
  fi
  if [[ ! -f "$versions_dest" ]]; then
    log "[cli] error: cli/versions.toml missing. Sync versions before building."
    return 1
  fi
  if ! cmp -s "$versions_src" "$versions_dest"; then
    log "[cli] error: versions.toml files differ. Sync root and cli copies before building."
    return 1
  fi

  log "[cli] packaging crate (without verification) for inspection"
  if $DRY_RUN; then
    run_in_dir "$comp_dir" "$CARGO_BIN" package --no-verify
    log "[cli] dry-run: skipping crate copy"
    return
  fi

  run_in_dir "$comp_dir" "$CARGO_BIN" package --no-verify
  local crate_path
  crate_path="$(find "${comp_dir}/target/package" -maxdepth 1 -name '*.crate' -print -quit)"
  if [[ -n "$crate_path" ]]; then
    run_cmd cp -f "$crate_path" "${out_dir}/"
  else
    log "[cli] warning: crate package not found after cargo package"
  fi
}

process_component() {
  local comp="$1"
  log "----- ${comp} -----"
  if $DO_BUILD; then
    "build_${comp}"
  else
    log "[${comp}] build skipped"
  fi
  if $DO_TEST; then
    "test_${comp}"
  else
    log "[${comp}] tests skipped"
  fi
  if $DO_PUBLISH; then
    "publish_${comp}"
  else
    log "[${comp}] publish skipped"
  fi
}

main() {
  parse_args "$@"
  calculate_tool_requirements
  prepare_workspace

  for comp in "${ORDERED_COMPONENTS[@]}"; do
    if component_selected "$comp"; then
      process_component "$comp"
    fi
  done

  log "build pipeline complete – artifacts available under ${ARTIFACT_ROOT}"
}

main "$@"
