#!/usr/bin/env bash
# Create Matrix bot accounts from bots.yaml and store access tokens locally (never printed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

BOT_CONFIG="${BOT_CONFIG:-$ROOT/bots.yaml}"
BOT_TOKENS_FILE="${BOT_TOKENS_FILE:-$ROOT/data/bots/tokens.env}"
SYNAPSE_URL="${SYNAPSE_INTERNAL_URL:-http://127.0.0.1:${SYNAPSE_HTTP_PORT:-8008}}"

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

mkdir -p "$(dirname "$BOT_TOKENS_FILE")"
umask 077
touch "$BOT_TOKENS_FILE"
chmod 600 "$BOT_TOKENS_FILE"

{
  echo "# Matrix bot credentials — keep secret (chmod 600)"
  echo "# Homeserver: ${SYNAPSE_SERVER_NAME}"
  echo "# Config: ${BOT_CONFIG}"
  echo "# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
} > "$BOT_TOKENS_FILE"

localparts=()
created=0

for row in "${BOT_ROWS[@]}"; do
  username="${row%%$'\t'*}"
  display_name="${row#*$'\t'}"
  password="$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)"
  env_slug="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${username}'))")"

  if podman compose exec -T synapse register_new_matrix_user \
    -c /data/homeserver.yaml \
    -u "$username" \
    -p "$password" \
    --no-admin \
    "$SYNAPSE_URL" >/dev/null 2>&1; then
    :
  else
    echo "Failed to register @${username}:${SYNAPSE_SERVER_NAME} (already exists?)" >&2
    continue
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
echo "Registered ${created} bot account(s) from ${BOT_CONFIG} → ${BOT_TOKENS_FILE} (tokens not shown)."
