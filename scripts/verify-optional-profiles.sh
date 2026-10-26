#!/usr/bin/env bash
# Smoke optional profiles: start, auth, down -v, data survives.
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

python3 -m pip install -q httpx redis nats-py 2>/dev/null || true

echo "=== bus ==="
./scripts/verify-bus-persistence.sh

echo "=== object (Garage) ==="
./scripts/bootstrap-object.sh
marker="obj-$(date +%s)"
echo "$marker" > "$DATA_ROOT/garage/persist-marker.txt"
COMPOSE_PROFILES=object podman compose down -v
./scripts/bootstrap-object.sh
test "$(cat "$DATA_ROOT/garage/persist-marker.txt")" = "$marker"
curl -fsS -H "Authorization: Bearer ${GARAGE_ADMIN_TOKEN}" \
  "http://127.0.0.1:${GARAGE_ADMIN_PORT:-13903}/v1/status" >/dev/null
echo "OK: Garage persisted"

echo "=== vectors (Qdrant) ==="
./scripts/bootstrap-vectors.sh
for _ in $(seq 1 30); do
  curl -fsS -H "api-key: ${QDRANT_API_KEY}" \
    "http://127.0.0.1:${QDRANT_HTTP_PORT:-16333}/collections" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS -X PUT -H "api-key: ${QDRANT_API_KEY}" -H "Content-Type: application/json" \
  "http://127.0.0.1:${QDRANT_HTTP_PORT:-16333}/collections/bot_memory" \
  -d '{"vectors":{"size":4,"distance":"Cosine"}}' >/dev/null || true
echo "vec-marker" > "$DATA_ROOT/qdrant/persist-marker.txt"
COMPOSE_PROFILES=vectors podman compose down -v
./scripts/bootstrap-vectors.sh
test "$(cat "$DATA_ROOT/qdrant/persist-marker.txt")" = "vec-marker"
curl -fsS -H "api-key: ${QDRANT_API_KEY}" \
  "http://127.0.0.1:${QDRANT_HTTP_PORT:-16333}/collections" | grep -q bot_memory
echo "OK: Qdrant persisted"

echo "=== llm (Ollama) ==="
mkdir -p "$DATA_ROOT/ollama"
echo "llm-marker" > "$DATA_ROOT/ollama/persist-marker.txt"
COMPOSE_PROFILES=llm podman compose up -d ollama
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${OLLAMA_PORT:-11434}/api/tags" >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS "http://127.0.0.1:${OLLAMA_PORT:-11434}/api/tags" >/dev/null
COMPOSE_PROFILES=llm podman compose down -v
COMPOSE_PROFILES=llm podman compose up -d ollama
for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:${OLLAMA_PORT:-11434}/api/tags" >/dev/null 2>&1 && break
  sleep 2
done
test "$(cat "$DATA_ROOT/ollama/persist-marker.txt")" = "llm-marker"
echo "OK: Ollama volume persisted"

echo "All optional profile checks passed."
