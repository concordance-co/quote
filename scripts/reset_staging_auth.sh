#!/usr/bin/env bash
set -euo pipefail

# Reset staging backend auth keys and recreate custom admin login keys.
#
# Required env vars:
#   DEV_DSN             Postgres connection string for staging/dev Neon DB
#   STAGING_BACKEND     e.g. https://concordance--thunder-backend-staging-thunder-server.modal.run
#   BOOTSTRAP_SECRET    Must match backend BOOTSTRAP_SECRET
#
# Optional env vars:
#   CUSTOM_ADMIN_KEYS   Comma-separated custom login keys. Default: "marshall-admin"
#   ROOT_ADMIN_NAME     Name for bootstrap key. Default: "staging-root-admin"
#   REDEPLOY_STAGING    "1" to redeploy Modal staging backend first. Default: "0"
#   MODAL_APP_NAME      Default: "thunder-backend-staging"
#   MODAL_SECRET_NAME   Default: "thunder-db-staging"
#   FORCE_YES           "1" to skip interactive confirmation

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "Missing required command: psql"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Missing required command: jq"
  exit 1
fi

: "${DEV_DSN:?DEV_DSN is required}"
: "${STAGING_BACKEND:?STAGING_BACKEND is required}"
: "${BOOTSTRAP_SECRET:?BOOTSTRAP_SECRET is required}"

CUSTOM_ADMIN_KEYS="${CUSTOM_ADMIN_KEYS:-marshall-admin}"
ROOT_ADMIN_NAME="${ROOT_ADMIN_NAME:-staging-root-admin}"
REDEPLOY_STAGING="${REDEPLOY_STAGING:-0}"
MODAL_APP_NAME="${MODAL_APP_NAME:-thunder-backend-staging}"
MODAL_SECRET_NAME="${MODAL_SECRET_NAME:-thunder-db-staging}"
FORCE_YES="${FORCE_YES:-0}"

STAGING_BACKEND="${STAGING_BACKEND%/}"
SAFE_DSN="$(printf "%s" "$DEV_DSN" | sed -E 's#(postgres(ql)?://)[^@]+@#\1***@#')"

echo "About to:"
echo "1) TRUNCATE api_keys in: $SAFE_DSN"
echo "2) Bootstrap admin key on: $STAGING_BACKEND"
echo "3) Create custom admin login keys: $CUSTOM_ADMIN_KEYS"
echo

if [[ "$FORCE_YES" != "1" ]]; then
  read -r -p "Type RESET to continue: " CONFIRM
  if [[ "$CONFIRM" != "RESET" ]]; then
    echo "Cancelled."
    exit 1
  fi
fi

if [[ "$REDEPLOY_STAGING" == "1" ]]; then
  if ! command -v modal >/dev/null 2>&1; then
    echo "Missing required command for redeploy: modal"
    exit 1
  fi
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  BACKEND_DIR="$(cd "$SCRIPT_DIR/../backend" && pwd)"
  echo "Redeploying staging backend ($MODAL_APP_NAME / $MODAL_SECRET_NAME)..."
  (
    cd "$BACKEND_DIR"
    MODAL_APP_NAME="$MODAL_APP_NAME" MODAL_SECRET_NAME="$MODAL_SECRET_NAME" modal deploy deploy.py
  )
fi

echo "Truncating api_keys..."
psql "$DEV_DSN" -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE api_keys RESTART IDENTITY;"

echo "Bootstrapping root admin key..."
BOOTSTRAP_BODY="$(jq -nc --arg name "$ROOT_ADMIN_NAME" --arg secret "$BOOTSTRAP_SECRET" '{name:$name, secret:$secret}')"
BOOTSTRAP_TMP="$(mktemp)"
BOOTSTRAP_STATUS="$(
  curl -sS \
    -o "$BOOTSTRAP_TMP" \
    -w "%{http_code}" \
    -X POST "$STAGING_BACKEND/auth/bootstrap" \
    -H "Content-Type: application/json" \
    -d "$BOOTSTRAP_BODY"
)"

if [[ "$BOOTSTRAP_STATUS" != "200" ]]; then
  echo "Bootstrap failed (HTTP $BOOTSTRAP_STATUS):"
  cat "$BOOTSTRAP_TMP"
  rm -f "$BOOTSTRAP_TMP"
  exit 1
fi

ROOT_ADMIN_KEY="$(jq -r '.api_key // empty' "$BOOTSTRAP_TMP")"
rm -f "$BOOTSTRAP_TMP"

if [[ -z "$ROOT_ADMIN_KEY" ]]; then
  echo "Bootstrap succeeded but api_key was missing in response."
  exit 1
fi

echo "Creating custom admin login keys..."
IFS=',' read -r -a KEYS <<< "$CUSTOM_ADMIN_KEYS"

for RAW_KEY in "${KEYS[@]}"; do
  KEY="$(echo "$RAW_KEY" | xargs)"
  if [[ -z "$KEY" ]]; then
    continue
  fi

  CREATE_BODY="$(jq -nc --arg name "$KEY" --arg allowed "$KEY" \
    '{name:$name, description:"staging custom admin key", allowed_api_key:$allowed, is_admin:true}')"
  CREATE_TMP="$(mktemp)"
  CREATE_STATUS="$(
    curl -sS \
      -o "$CREATE_TMP" \
      -w "%{http_code}" \
      -X POST "$STAGING_BACKEND/auth/keys" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $ROOT_ADMIN_KEY" \
      -d "$CREATE_BODY"
  )"

  if [[ "$CREATE_STATUS" != "200" ]]; then
    echo "Failed to create key '$KEY' (HTTP $CREATE_STATUS):"
    cat "$CREATE_TMP"
    rm -f "$CREATE_TMP"
    exit 1
  fi
  rm -f "$CREATE_TMP"

  VALIDATE_TMP="$(mktemp)"
  VALIDATE_STATUS="$(
    curl -sS \
      -o "$VALIDATE_TMP" \
      -w "%{http_code}" \
      "$STAGING_BACKEND/auth/validate" \
      -H "X-API-Key: $KEY"
  )"
  if [[ "$VALIDATE_STATUS" != "200" ]]; then
    echo "Validation failed for custom key '$KEY' (HTTP $VALIDATE_STATUS):"
    cat "$VALIDATE_TMP"
    rm -f "$VALIDATE_TMP"
    exit 1
  fi
  rm -f "$VALIDATE_TMP"

  echo "  - OK: $KEY (admin login key)"
done

echo
echo "Done."
echo "Root admin key (save securely):"
echo "$ROOT_ADMIN_KEY"
echo
echo "Use your custom key(s) for FE login."
