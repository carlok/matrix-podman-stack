#!/usr/bin/env bash
# Create Matrix bot accounts from bots.yaml and store access tokens locally (never printed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example" >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
source .env
set +a

BOT_CONFIG="${BOT_CONFIG:-$ROOT/bots.yaml}"
# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
ensure_data_dirs "$DATA_ROOT"
BOT_TOKENS_FILE="${BOT_TOKENS_FILE:-$DATA_ROOT/bots/tokens.env}"
SYNAPSE_URL="${SYNAPSE_INTERNAL_URL:-http://127.0.0.1:${SYNAPSE_HTTP_PORT:-8008}}"
ADMIN_USER="${SYNAPSE_ADMIN_USER:-${TEST_ADMIN_USER:-admin}}"
ADMIN_PASS="${SYNAPSE_ADMIN_PASSWORD:-${TEST_ADMIN_PASSWORD:-}}"

: "${SYNAPSE_SERVER_NAME:?}"

if [[ ! -f "$BOT_CONFIG" && -f "$ROOT/bots.example.yaml" ]]; then
  BOT_CONFIG="$ROOT/bots.example.yaml"
fi

if [[ ! -f "$BOT_CONFIG" ]]; then
  echo "No bot config at bots.yaml — copy bots.example.yaml to bots.yaml and edit." >&2
  exit 1
fi

mapfile -t BOT_ROWS < <(python3 "$ROOT/scripts/load_bot_config.py" --config "$BOT_CONFIG")
BOT_COUNT="${#BOT_ROWS[@]}"
if [[ "$BOT_COUNT" -lt 1 ]]; then
  echo "No bots defined in $BOT_CONFIG" >&2
  exit 1
fi

ADMIN_TOKEN=""
if [[ -n "$ADMIN_PASS" ]]; then
  ADMIN_TOKEN="$(python3 "$ROOT/scripts/synapse_admin.py" login \
    --url "$SYNAPSE_URL" --user "$ADMIN_USER" --password "$ADMIN_PASS")"
fi
if [[ -z "$ADMIN_TOKEN" && -f "$DATA_ROOT/bots/admin.token" ]]; then
  ADMIN_TOKEN="$(tr -d '\n' < "$DATA_ROOT/bots/admin.token")"
fi

apply_bot_rate_limit() {
  local user_id="$1"
  if [[ -z "$ADMIN_TOKEN" ]]; then
    return 0
  fi
  python3 "$ROOT/scripts/synapse_admin.py" rate-limit-override \
    --url "$SYNAPSE_URL" \
    --admin-token "$ADMIN_TOKEN" \
    --user-id "$user_id" \
    --mps "${BOT_RATELIMIT_MPS:-1000}" \
    --burst "${BOT_RATELIMIT_BURST:-1000}" >/dev/null
}

mkdir -p "$(dirname "$BOT_TOKENS_FILE")"
umask 077
OLD_TOKENS=""
if [[ -f "$BOT_TOKENS_FILE" ]]; then
  OLD_TOKENS="$(cat "$BOT_TOKENS_FILE")"
fi

{
  echo "# Matrix bot credentials — keep secret (chmod 600)"
  echo "# Homeserver: ${SYNAPSE_SERVER_NAME}"
  echo "# Config: ${BOT_CONFIG}"
  echo "# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
} > "$BOT_TOKENS_FILE"

localparts=()
created=0

if [[ -n "$ADMIN_TOKEN" ]]; then
  mkdir -p "$(dirname "$BOT_TOKENS_FILE")"
  printf '%s' "$ADMIN_TOKEN" > "$(dirname "$BOT_TOKENS_FILE")/admin.token"
  chmod 600 "$(dirname "$BOT_TOKENS_FILE")/admin.token"
  admin_id="@${ADMIN_USER}:${SYNAPSE_SERVER_NAME}"
  apply_bot_rate_limit "$admin_id" || true
fi

for row in "${BOT_ROWS[@]}"; do
  username="${row%%$'\t'*}"
  display_name="${row#*$'\t'}"
  user_id="@${username}:${SYNAPSE_SERVER_NAME}"
  password="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
  env_slug="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${username}'))")"

  registered=0
  if podman compose exec -T synapse register_new_matrix_user \
    -c /data/homeserver.yaml \
    -u "$username" \
    -p "$password" \
    --no-admin \
    "$SYNAPSE_URL" >/dev/null 2>&1; then
    registered=1
  else
    echo "Note: @${username}:${SYNAPSE_SERVER_NAME} already exists — skipping registration." >&2
  fi

  apply_bot_rate_limit "$user_id" || echo "Warning: rate-limit override failed for ${user_id}" >&2

  if [[ "$registered" -ne 1 ]]; then
    if [[ -n "$ADMIN_TOKEN" ]]; then
      python3 "$ROOT/scripts/synapse_admin.py" reset-password \
        --url "$SYNAPSE_URL" \
        --admin-token "$ADMIN_TOKEN" \
        --user-id "$user_id" \
        --password "$password" >/dev/null
      registered=1
    elif [[ -n "$OLD_TOKENS" ]] && grep -q "^${env_slug}_USER_ID=" <<<"$OLD_TOKENS"; then
      {
        echo ""
        grep "^${env_slug}_" <<<"$OLD_TOKENS" || true
      } >> "$BOT_TOKENS_FILE"
      localparts+=("$username")
      continue
    else
      echo "Cannot obtain token for existing ${user_id} without admin credentials." >&2
      continue
    fi
  fi

  response="$(curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/login" \
    -H "Content-Type: application/json" \
    -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"${username}\"},\"password\":\"${password}\"}")"

  token="$(python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" <<<"$response")"
  user_id="$(python3 -c "import json,sys; print(json.load(sys.stdin)['user_id'])" <<<"$response")"

  localparts+=("$username")
  {
    echo ""
    printf '%s=%q\n' "${env_slug}_USER_ID" "${user_id}"
    printf '%s=%q\n' "${env_slug}_ACCESS_TOKEN" "${token}"
    printf '%s=%q\n' "${env_slug}_DISPLAY_NAME" "${display_name}"
  } >> "$BOT_TOKENS_FILE"
  created=$((created + 1))
done

ignore_ids=""
for row in "${BOT_ROWS[@]}"; do
  username="${row%%$'\t'*}"
  ignore_ids+="@${username}:${SYNAPSE_SERVER_NAME},"
done
ignore_ids="${ignore_ids%,}"

{
  echo "BOTS_LOCALPARTS=$(IFS=,; echo "${localparts[*]}")"
  echo "BOT_IGNORE_MATRIX_IDS=${ignore_ids}"
} >> "$BOT_TOKENS_FILE"

chmod 600 "$BOT_TOKENS_FILE"
echo "Registered ${created} new bot account(s); rate-limit overrides applied when admin credentials are set."
