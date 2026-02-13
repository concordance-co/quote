#!/usr/bin/env bash
set -euo pipefail

# Create custom admin login keys for teammates on staging backend.
#
# Required env vars:
#   STAGING_BACKEND    e.g. https://concordance--thunder-backend-staging-thunder-server.modal.run
#   ROOT_ADMIN_KEY     Existing admin backend key (usually from bootstrap)
#   CUSTOM_ADMIN_KEYS  Comma-separated custom literal keys, e.g. "alice-admin,bob-admin"
#
# Optional env vars:
#   DESCRIPTION_PREFIX Description template prefix. Default: "staging teammate admin key"
#   FORCE_YES          "1" skips confirmation prompt

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl"
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Missing required command: jq"
  exit 1
fi

: "${STAGING_BACKEND:?STAGING_BACKEND is required}"
: "${ROOT_ADMIN_KEY:?ROOT_ADMIN_KEY is required}"
: "${CUSTOM_ADMIN_KEYS:?CUSTOM_ADMIN_KEYS is required}"

DESCRIPTION_PREFIX="${DESCRIPTION_PREFIX:-staging teammate admin key}"
FORCE_YES="${FORCE_YES:-0}"
STAGING_BACKEND="${STAGING_BACKEND%/}"

echo "Target backend: $STAGING_BACKEND"
echo "Will create admin login keys: $CUSTOM_ADMIN_KEYS"
echo

if [[ "$FORCE_YES" != "1" ]]; then
  read -r -p "Type CREATE to continue: " CONFIRM
  if [[ "$CONFIRM" != "CREATE" ]]; then
    echo "Cancelled."
    exit 1
  fi
fi

IFS=',' read -r -a RAW_KEYS <<< "$CUSTOM_ADMIN_KEYS"

created=0
for raw in "${RAW_KEYS[@]}"; do
  key="$(echo "$raw" | xargs)"
  if [[ -z "$key" ]]; then
    continue
  fi

  description="$DESCRIPTION_PREFIX ($key)"
  create_body="$(
    jq -nc \
      --arg name "$key" \
      --arg description "$description" \
      --arg allowed "$key" \
      '{name:$name, description:$description, allowed_api_key:$allowed, is_admin:true}'
  )"

  create_tmp="$(mktemp)"
  create_status="$(
    curl -sS \
      -o "$create_tmp" \
      -w "%{http_code}" \
      -X POST "$STAGING_BACKEND/auth/keys" \
      -H "Content-Type: application/json" \
      -H "X-API-Key: $ROOT_ADMIN_KEY" \
      -d "$create_body"
  )"

  if [[ "$create_status" != "200" ]]; then
    echo "Failed to create '$key' (HTTP $create_status):"
    cat "$create_tmp"
    rm -f "$create_tmp"
    exit 1
  fi
  rm -f "$create_tmp"

  validate_tmp="$(mktemp)"
  validate_status="$(
    curl -sS \
      -o "$validate_tmp" \
      -w "%{http_code}" \
      "$STAGING_BACKEND/auth/validate" \
      -H "X-API-Key: $key"
  )"

  if [[ "$validate_status" != "200" ]]; then
    echo "Created '$key' but validation failed (HTTP $validate_status):"
    cat "$validate_tmp"
    rm -f "$validate_tmp"
    exit 1
  fi

  is_admin="$(jq -r '.is_admin // false' "$validate_tmp")"
  rm -f "$validate_tmp"

  if [[ "$is_admin" != "true" ]]; then
    echo "Created '$key' but backend does not report admin=true."
    exit 1
  fi

  echo "  - OK: $key"
  created=$((created + 1))
done

echo
echo "Done. Created $created teammate admin key(s)."
