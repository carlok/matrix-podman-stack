#!/usr/bin/env bash
# Verify NATS JetStream + Valkey auth and DATA_DIR persistence across down -v.
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

python3 -m pip install -q nats-py redis

./scripts/bootstrap-bus.sh
HOST_UID=$(id -u) HOST_GID=$(id -g) COMPOSE_PROFILES=bus podman compose up -d nats valkey

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:${NATS_MONITOR_PORT:-18222}/healthz" >/dev/null 2>&1 && break
  sleep 2
done

marker="bus-persist-$(date +%s)"
NATS_URL="nats://${NATS_USER:-bots}:${NATS_PASSWORD}@127.0.0.1:${NATS_CLIENT_PORT:-14222}"

python3 - <<PY "$marker" "$NATS_URL" "$VALKEY_PASSWORD" "${VALKEY_PORT:-16379}"
import asyncio, sys
import nats
import redis

marker, nats_url, valkey_pw, valkey_port = sys.argv[1:5]

async def nats_write():
    nc = await nats.connect(nats_url)
    js = nc.jetstream()
    try:
        await js.add_stream(name="BOT_TASKS", subjects=["bot.tasks.>"])
    except Exception:
        pass
    await js.publish("bot.tasks.demo", marker.encode())
    await nc.close()

asyncio.run(nats_write())

r = redis.Redis(host="127.0.0.1", port=int(valkey_port), password=valkey_pw, decode_responses=True)
r.set("matrix:bus:marker", marker)
assert r.get("matrix:bus:marker") == marker
print("OK: bus auth write", marker)
PY

js_files_before="$(find "$DATA_ROOT/nats/jetstream" -type f 2>/dev/null | wc -l)"

HOST_UID=$(id -u) HOST_GID=$(id -g) COMPOSE_PROFILES=bus podman compose down -v
./scripts/bootstrap-bus.sh
HOST_UID=$(id -u) HOST_GID=$(id -g) COMPOSE_PROFILES=bus podman compose up -d nats valkey

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:${NATS_MONITOR_PORT:-18222}/healthz" >/dev/null 2>&1 && break
  sleep 2
done

python3 - <<PY "$marker" "$NATS_URL" "$VALKEY_PASSWORD" "${VALKEY_PORT:-16379}"
import asyncio, sys
import nats
import redis

marker, nats_url, valkey_pw, valkey_port = sys.argv[1:5]

r = redis.Redis(host="127.0.0.1", port=int(valkey_port), password=valkey_pw, decode_responses=True)
if r.get("matrix:bus:marker") != marker:
    raise SystemExit("FAIL: Valkey marker missing after restart")

async def nats_auth():
    nc = await nats.connect(nats_url)
    js = nc.jetstream()
    info = await js.stream_info("BOT_TASKS")
    if info.state.messages < 1:
        raise SystemExit("FAIL: JetStream stream empty after restart")
    await nc.close()

asyncio.run(nats_auth())
print("OK: bus data survived compose down -v")
PY

js_files_after="$(find "$DATA_ROOT/nats/jetstream" -type f 2>/dev/null | wc -l)"
test "$js_files_after" -ge "$js_files_before"

echo "OK: JetStream files=$js_files_after Valkey under $DATA_ROOT"
