#!/usr/bin/env bash
# Smoke test: create a room, invite the first configured bot, send a mention, expect a reply.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source .env
source "${BOT_TOKENS_FILE:-$ROOT/data/bots/tokens.env}"

SYNAPSE_URL="${SYNAPSE_INTERNAL_URL:-http://127.0.0.1:${SYNAPSE_HTTP_PORT:-8008}}"
ADMIN_USER="${TEST_ADMIN_USER:-admin}"
ADMIN_PASS="${TEST_ADMIN_PASSWORD:?Set TEST_ADMIN_PASSWORD for smoke test}"

first_localpart="${BOTS_LOCALPARTS%%,*}"
if [[ -z "$first_localpart" ]]; then
  echo "BOTS_LOCALPARTS missing in tokens file — run scripts/create-bots.sh" >&2
  exit 1
fi

env_slug="$(PYTHONPATH="$ROOT/scripts" python3 -c "from load_bot_config import env_key; print(env_key('${first_localpart}'))")"
token_var="${env_slug}_ACCESS_TOKEN"
user_var="${env_slug}_USER_ID"
display_var="${env_slug}_DISPLAY_NAME"
BOT_TOKEN="${!token_var:?missing bot token}"
BOT_ID="${!user_var:?missing bot user id}"
BOT_DISPLAY="${!display_var:-$first_localpart}"

admin_login="$(curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/login" \
  -H "Content-Type: application/json" \
  -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"${ADMIN_USER}\"},\"password\":\"${ADMIN_PASS}\"}")"
ADMIN_TOKEN="$(python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" <<<"$admin_login")"

room_id="$(curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"preset\":\"private_chat\",\"invite\":[\"${BOT_ID}\"],\"name\":\"bot-smoke-test\"}" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['room_id'])")"

python3 -m venv "$ROOT/.venv-bot-test"
"$ROOT/.venv-bot-test/bin/pip" install -q -r "$ROOT/bots/example_bot/requirements.txt"

export MATRIX_HOMESERVER_URL="$SYNAPSE_URL"
export MATRIX_USER_ID="$BOT_ID"
export MATRIX_ACCESS_TOKEN="$BOT_TOKEN"
export BOT_DISPLAY_NAME="$BOT_DISPLAY"
export SYNAPSE_SERVER_NAME="${SYNAPSE_SERVER_NAME:-}"

"$ROOT/.venv-bot-test/bin/python" "$ROOT/bots/example_bot/bot.py" &
BOT_PID=$!
sleep 5

curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/join" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" >/dev/null || true
sleep 3

curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/send/m.room.message/$(date +%s)" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"msgtype\":\"m.text\",\"body\":\"Hello @${first_localpart} ping\"}"

sleep 8
kill "$BOT_PID" 2>/dev/null || true

events="$(curl -fsS "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/messages?dir=b&limit=10" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}")"

python3 - <<'PY' "$events" "$BOT_ID"
import json, sys
events = json.loads(sys.argv[1])
bot = sys.argv[2]
for item in events.get("chunk", []):
    if item.get("type") != "m.room.message":
        continue
    if item.get("sender") == bot:
        print("OK: bot replied:", item.get("content", {}).get("body", "")[:120])
        raise SystemExit(0)
raise SystemExit("Bot did not reply in time")
PY
