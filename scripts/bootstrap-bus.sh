#!/usr/bin/env bash
# Render NATS / Valkey configs under DATA_DIR (run before COMPOSE_PROFILES=bus up).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env first." >&2
  exit 1
fi

# shellcheck source=/dev/null
set -a
source .env
set +a

: "${NATS_PASSWORD:?Set NATS_PASSWORD in .env}"
: "${VALKEY_PASSWORD:?Set VALKEY_PASSWORD in .env}"

# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"
ensure_data_dirs "$DATA_ROOT"

uid="${HOST_UID:-$(id -u)}"
gid="${HOST_GID:-$(id -g)}"
for conf in "$DATA_ROOT/nats/nats.conf" "$DATA_ROOT/valkey/valkey.conf"; do
  if [[ -e "$conf" ]] && [[ ! -w "$conf" ]]; then
    chown "$uid:$gid" "$conf" 2>/dev/null || sudo chown "$uid:$gid" "$conf"
  fi
done

python3 "$ROOT/scripts/render_bus_config.py" \
  --data-root "$DATA_ROOT" \
  --nats-user "${NATS_USER:-bots}" \
  --nats-password "$NATS_PASSWORD" \
  --valkey-password "$VALKEY_PASSWORD"

echo "Bus configs written under ${DATA_ROOT}/nats and ${DATA_ROOT}/valkey"
