#!/usr/bin/env bash
# Render Garage config and initialize single-node layout (profile: object).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
set -a
source .env
set +a

: "${GARAGE_RPC_SECRET:?}"
: "${GARAGE_ADMIN_TOKEN:?}"

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"

python3 "$ROOT/scripts/render_object_config.py" \
  --data-root "$DATA_ROOT" \
  --rpc-secret "$GARAGE_RPC_SECRET" \
  --admin-token "$GARAGE_ADMIN_TOKEN" \
  --s3-region "${GARAGE_S3_REGION:-garage}"

COMPOSE_PROFILES=object podman compose up -d garage
for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:${GARAGE_ADMIN_PORT:-13903}/health" >/dev/null 2>&1 && break
  sleep 2
done

if COMPOSE_PROFILES=object podman compose exec -T garage /garage layout show 2>/dev/null \
  | grep -q "No nodes currently have a role"; then
  node_id="$(COMPOSE_PROFILES=object podman compose exec -T garage /garage node id -q 2>/dev/null \
    | tr -d '\r' | cut -d@ -f1)"
  COMPOSE_PROFILES=object podman compose exec -T garage /garage layout assign \
    -z local -c 1G "${node_id}" >/dev/null
  COMPOSE_PROFILES=object podman compose exec -T garage /garage layout apply --version 1 >/dev/null
  COMPOSE_PROFILES=object podman compose exec -T garage /garage bucket create "${GARAGE_BUCKET:-bot-artifacts}" >/dev/null 2>&1 || true
else
  echo "Garage layout already configured."
fi

echo "Garage ready (profile: object). S3 endpoint: http://127.0.0.1:${GARAGE_S3_PORT:-13900}"
