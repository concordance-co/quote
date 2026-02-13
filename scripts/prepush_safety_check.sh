#!/usr/bin/env bash
set -euo pipefail

# Pre-push safety checks for staging workflow.
#
# Optional overrides:
#   EXPECTED_BRANCH
#   EXPECTED_UPSTREAM
#   EXPECTED_DEV_DB_HOST
#   EXPECTED_STAGING_BACKEND
#   REQUIRE_LOCAL_FRONTEND_ENV (1/0)
#   REQUIRE_LOCAL_ENGINE_INGEST (1/0)
#
# Example:
#   EXPECTED_DEV_DB_HOST=ep-xxx.us-east-1.aws.neon.tech ./scripts/prepush_safety_check.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

EXPECTED_BRANCH="${EXPECTED_BRANCH:-staging}"
EXPECTED_UPSTREAM="${EXPECTED_UPSTREAM:-origin/staging}"
EXPECTED_DEV_DB_HOST="${EXPECTED_DEV_DB_HOST:-ep-steep-sky-adlihvy9-pooler.c-2.us-east-1.aws.neon.tech}"
EXPECTED_STAGING_BACKEND="${EXPECTED_STAGING_BACKEND:-https://concordance--thunder-backend-staging-thunder-server.modal.run}"
REQUIRE_LOCAL_FRONTEND_ENV="${REQUIRE_LOCAL_FRONTEND_ENV:-1}"
REQUIRE_LOCAL_ENGINE_INGEST="${REQUIRE_LOCAL_ENGINE_INGEST:-1}"

BACKEND_ENV="$ROOT_DIR/backend/.env"
FRONTEND_ENV="$ROOT_DIR/frontend/.env"
ENGINE_ENV="$ROOT_DIR/engine/inference/.env"
VERCEL_JSON="$ROOT_DIR/frontend/vercel.json"

fail() {
  echo "FAIL: $1"
  exit 1
}

warn() {
  echo "WARN: $1"
}

pass() {
  echo "PASS: $1"
}

echo "Running staging pre-push safety checks..."

branch="$(git -C "$ROOT_DIR" branch --show-current)"
[[ "$branch" == "$EXPECTED_BRANCH" ]] || fail "Current branch is '$branch' (expected '$EXPECTED_BRANCH')."
pass "Branch is $branch"

upstream="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
[[ "$upstream" == "$EXPECTED_UPSTREAM" ]] || fail "Upstream is '$upstream' (expected '$EXPECTED_UPSTREAM')."
pass "Upstream is $upstream"

tracked_env="$(
  git -C "$ROOT_DIR" ls-files \
    | rg '(^|/)\.env($|\.local$|\.development\.local$|\.test\.local$|\.production\.local$)' \
    || true
)"
if [[ -n "$tracked_env" ]]; then
  fail ".env files are tracked by git:\n$tracked_env"
fi
pass "No tracked .env files"

[[ -f "$BACKEND_ENV" ]] || fail "Missing $BACKEND_ENV"
db_url="$(grep -E '^DATABASE_URL=' "$BACKEND_ENV" | sed 's/^DATABASE_URL=//' || true)"
[[ -n "$db_url" ]] || fail "DATABASE_URL missing in backend/.env"
db_host="$(printf "%s" "$db_url" | sed -E 's#^postgres(ql)?://[^@]+@([^/:?]+).*#\2#')"
[[ "$db_host" == "$EXPECTED_DEV_DB_HOST" ]] || fail "backend/.env DB host is '$db_host' (expected '$EXPECTED_DEV_DB_HOST')."
pass "backend/.env DATABASE_URL host matches expected dev DB"

bootstrap_secret="$(grep -E '^BOOTSTRAP_SECRET=' "$BACKEND_ENV" | sed 's/^BOOTSTRAP_SECRET=//' || true)"
[[ -n "$bootstrap_secret" ]] || warn "BOOTSTRAP_SECRET is empty in backend/.env (fine if using Modal secrets only)."

[[ -f "$VERCEL_JSON" ]] || fail "Missing $VERCEL_JSON"
api_dest="$(jq -r '.rewrites[] | select(.source=="/api/:path*") | .destination' "$VERCEL_JSON" 2>/dev/null || true)"
[[ "$api_dest" == "$EXPECTED_STAGING_BACKEND/:path*" ]] || fail "frontend/vercel.json /api rewrite is '$api_dest' (expected '$EXPECTED_STAGING_BACKEND/:path*')."
pass "frontend/vercel.json /api rewrite points at staging backend"

if rg -n "concordance--thunder-backend-thunder-server\\.modal\\.run" "$VERCEL_JSON" >/dev/null 2>&1; then
  fail "frontend/vercel.json still contains prod backend hostname."
fi
pass "frontend/vercel.json has no prod backend hostname"

if [[ "$REQUIRE_LOCAL_FRONTEND_ENV" == "1" ]]; then
  [[ -f "$FRONTEND_ENV" ]] || fail "Missing $FRONTEND_ENV"
  fe_api="$(grep -E '^VITE_API_URL=' "$FRONTEND_ENV" | sed 's/^VITE_API_URL=//' || true)"
  fe_ws="$(grep -E '^VITE_WS_URL=' "$FRONTEND_ENV" | sed 's/^VITE_WS_URL=//' || true)"
  [[ "$fe_api" == "http://localhost:6767" ]] || fail "frontend/.env VITE_API_URL is '$fe_api' (expected http://localhost:6767)."
  [[ "$fe_ws" == "ws://localhost:6767" ]] || fail "frontend/.env VITE_WS_URL is '$fe_ws' (expected ws://localhost:6767)."
  pass "frontend/.env points to local backend for local dev"
fi

if [[ "$REQUIRE_LOCAL_ENGINE_INGEST" == "1" ]]; then
  [[ -f "$ENGINE_ENV" ]] || fail "Missing $ENGINE_ENV"
  ingest_url="$(grep -E '^QUOTE_LOG_INGEST_URL=' "$ENGINE_ENV" | sed 's/^QUOTE_LOG_INGEST_URL=//' || true)"
  [[ "$ingest_url" == "http://localhost:6767/v1/ingest" ]] || fail "engine/inference/.env QUOTE_LOG_INGEST_URL is '$ingest_url' (expected http://localhost:6767/v1/ingest)."
  pass "engine/inference/.env ingest URL points to local backend"
fi

echo
echo "All safety checks passed."
