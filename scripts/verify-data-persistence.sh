#!/usr/bin/env bash
# Verify bind-mounted DATA_DIR survives `podman compose down -v`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
set -a
source .env
set +a

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
BOT_TOKENS_FILE="${BOT_TOKENS_FILE:-$DATA_ROOT/bots/tokens.env}"
SYNAPSE_URL="${SYNAPSE_INTERNAL_URL:-http://127.0.0.1:${SYNAPSE_HTTP_PORT:-8008}}"
ADMIN_USER="${TEST_ADMIN_USER:-admin}"
ADMIN_PASS="${TEST_ADMIN_PASSWORD:?Set TEST_ADMIN_PASSWORD}"

TOKENS_HASH="$(sha256sum "$BOT_TOKENS_FILE" | awk '{print $1}')"

for _ in $(seq 1 60); do
  curl -fsS "${SYNAPSE_URL}/health" >/dev/null 2>&1 && break
  sleep 2
done

admin_token=""
if [[ -f "$DATA_ROOT/bots/admin.token" ]]; then
  admin_token="$(tr -d '\n' < "$DATA_ROOT/bots/admin.token")"
fi
if [[ -z "$admin_token" ]]; then
  admin_token="$(python3 "$ROOT/scripts/synapse_admin.py" login \
    --url "$SYNAPSE_URL" --user "$ADMIN_USER" --password "$ADMIN_PASS")"
fi

room_id="$(curl -fsS -X POST "${SYNAPSE_URL}/_matrix/client/v3/createRoom" \
  -H "Authorization: Bearer ${admin_token}" \
  -H "Content-Type: application/json" \
  -d '{"preset":"private_chat","name":"persistence-test"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['room_id'])")"

msg_body="persistence-check-$(date +%s)"
curl -fsS -X PUT "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/send/m.room.message/persist1" \
  -H "Authorization: Bearer ${admin_token}" \
  -H "Content-Type: application/json" \
  -d "{\"msgtype\":\"m.text\",\"body\":\"${msg_body}\"}" >/dev/null

tmp_upload="$(mktemp)"
echo "matrix-persistence-test-$(date +%s)" > "$tmp_upload"
mxc="$(curl -fsS -X POST "${SYNAPSE_URL}/_matrix/media/v3/upload" \
  -H "Authorization: Bearer ${admin_token}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @"$tmp_upload" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['content_uri'])")"
rm -f "$tmp_upload"

media_files_before="$(find "$DATA_ROOT/synapse/media_store" -type f 2>/dev/null | wc -l)"

echo "room_id=$room_id msg=$msg_body mxc=$mxc tokens_sha=$TOKENS_HASH"

HOST_UID=$(id -u) HOST_GID=$(id -g) podman compose down -v
HOST_UID=$(id -u) HOST_GID=$(id -g) podman compose up -d postgres-synapse synapse

for _ in $(seq 1 60); do
  curl -fsS "${SYNAPSE_URL}/health" >/dev/null 2>&1 && break
  sleep 3
done

admin_token="$(python3 "$ROOT/scripts/synapse_admin.py" login \
  --url "$SYNAPSE_URL" --user "$ADMIN_USER" --password "$ADMIN_PASS")"

curl -fsS "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/state/m.room.name" \
  -H "Authorization: Bearer ${admin_token}" >/dev/null

events="$(curl -fsS "${SYNAPSE_URL}/_matrix/client/v3/rooms/${room_id}/messages?dir=b&limit=10" \
  -H "Authorization: Bearer ${admin_token}")"
python3 - <<PY "$events" "$msg_body"
import json, sys
events = json.loads(sys.argv[1])
want = sys.argv[2]
for item in events.get("chunk", []):
    if item.get("type") == "m.room.message" and item.get("content", {}).get("body") == want:
        print("OK: message persisted")
        raise SystemExit(0)
raise SystemExit("FAIL: message missing after compose down -v")
PY

test "$(sha256sum "$BOT_TOKENS_FILE" | awk '{print $1}')" = "$TOKENS_HASH"
media_files_after="$(find "$DATA_ROOT/synapse/media_store" -type f 2>/dev/null | wc -l)"
test "$media_files_after" -ge "$media_files_before"

echo "OK: DATA_DIR at $DATA_ROOT survived podman compose down -v (user/room/message/media/tokens)"
