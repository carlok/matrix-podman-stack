#!/usr/bin/env bash
# Prepare local data dirs, render Element config, run Synapse one-shot bootstrap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and edit it first." >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
source .env
set +a

: "${SYNAPSE_SERVER_NAME:?SYNAPSE_SERVER_NAME required in .env}"
: "${PUBLIC_HOMESERVER_URL:?PUBLIC_HOMESERVER_URL required in .env}"
: "${PUBLIC_ELEMENT_URL:?PUBLIC_ELEMENT_URL required in .env}"

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
ensure_data_dirs "$DATA_ROOT"

python3 "$ROOT/scripts/render_element_config.py" \
  --homeserver-url "$PUBLIC_HOMESERVER_URL" \
  --server-name "$SYNAPSE_SERVER_NAME" \
  --output "$DATA_ROOT/element/config.json"

echo "Starting Postgres..."
"$ROOT/scripts/compose_stack.sh" up -d postgres-synapse
echo "Waiting for Postgres to become healthy..."
for _ in $(seq 1 60); do
  if "$ROOT/scripts/compose_stack.sh" exec -T postgres-synapse pg_isready -U "${SYNAPSE_POSTGRES_USER:-synapse}" -d "${SYNAPSE_POSTGRES_DB:-synapse}" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Running Synapse bootstrap (profile: bootstrap)..."
COMPOSE_PROFILES=bootstrap "$ROOT/scripts/compose_stack.sh" run --rm --no-deps synapse-bootstrap

echo "Bootstrap complete. Start the stack with: podman compose up -d"
