#!/usr/bin/env bash
# Smoke test: Synapse homeserver against Postgres 18 (fresh or existing DATA_DIR).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and set secrets first." >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
source .env
set +a

: "${SYNAPSE_SERVER_NAME:?set SYNAPSE_SERVER_NAME in .env}"
: "${SYNAPSE_POSTGRES_PASSWORD:?set SYNAPSE_POSTGRES_PASSWORD in .env}"
: "${PUBLIC_HOMESERVER_URL:?set PUBLIC_HOMESERVER_URL in .env}"
: "${PUBLIC_ELEMENT_URL:?set PUBLIC_ELEMENT_URL in .env}"

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
SYNAPSE_CFG="${DATA_ROOT}/synapse/homeserver.yaml"
PORT="${SYNAPSE_HTTP_PORT:-8008}"

echo "==> Postgres + Synapse smoke (DATA_DIR=${DATA_ROOT})"

if [[ ! -f "$SYNAPSE_CFG" ]]; then
  echo "No homeserver.yaml — running ./scripts/bootstrap.sh ..."
  HOST_UID="${HOST_UID:-$(id -u)}" HOST_GID="${HOST_GID:-$(id -g)}" ./scripts/bootstrap.sh
else
  echo "Using existing homeserver.yaml"
  "$ROOT/scripts/compose_stack.sh" up -d postgres-synapse
  for _ in $(seq 1 60); do
    if "$ROOT/scripts/compose_stack.sh" exec -T postgres-synapse pg_isready -U "${SYNAPSE_POSTGRES_USER:-synapse}" \
      -d "${SYNAPSE_POSTGRES_DB:-synapse}" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
fi

echo "==> Starting Synapse..."
HOST_UID="${HOST_UID:-$(id -u)}" HOST_GID="${HOST_GID:-$(id -g)}" "$ROOT/scripts/compose_stack.sh" up -d synapse

for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

echo -n "Synapse /health: "
curl -fsS "http://127.0.0.1:${PORT}/health"
echo

pg_ver="$("$ROOT/scripts/compose_stack.sh" exec -T postgres-synapse psql -U "${SYNAPSE_POSTGRES_USER:-synapse}" \
  -d "${SYNAPSE_POSTGRES_DB:-synapse}" -tAc "SHOW server_version;")"
echo "Postgres: ${pg_ver}"
case "$pg_ver" in
  18.*) echo "OK: Synapse is up and Postgres major is 18." ;;
  *)
    echo "WARNING: expected Postgres 18.x, got: ${pg_ver}" >&2
    exit 1
    ;;
esac
