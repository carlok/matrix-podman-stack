#!/usr/bin/env bash
# Generate mautrix-telegram config + appservice registration for Synapse.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

: "${SYNAPSE_SERVER_NAME:?}"
: "${TELEGRAM_API_ID:?Set TELEGRAM_API_ID from https://my.telegram.org}"
: "${TELEGRAM_API_HASH:?}"
: "${TELEGRAM_POSTGRES_PASSWORD:?}"

DATA_DIR="$ROOT/data/mautrix-telegram"
mkdir -p "$DATA_DIR"

if [[ ! -f "$DATA_DIR/config.yaml" ]]; then
  echo "Generating mautrix-telegram config..."
  podman run --rm \
    -v "$DATA_DIR:/data:Z" \
    dock.mau.dev/mautrix/telegram:v0.2610.0 \
    -g -c /data/config.yaml -r /data/registration.yaml
fi

python3 "$ROOT/scripts/patch_telegram_config.py" \
  --config "$DATA_DIR/config.yaml" \
  --homeserver "http://synapse:8008" \
  --server-name "$SYNAPSE_SERVER_NAME" \
  --db-host postgres-telegram \
  --db-user "${TELEGRAM_POSTGRES_USER:-mautrix_telegram}" \
  --db-password "$TELEGRAM_POSTGRES_PASSWORD" \
  --db-name "${TELEGRAM_POSTGRES_DB:-mautrix_telegram}" \
  --api-id "$TELEGRAM_API_ID" \
  --api-hash "$TELEGRAM_API_HASH"

cp -f "$DATA_DIR/registration.yaml" "$ROOT/data/synapse/telegram-registration.yaml"
chmod 600 "$ROOT/data/synapse/telegram-registration.yaml" 2>/dev/null || true

python3 "$ROOT/scripts/merge_telegram_appservice.py" \
  --homeserver "$ROOT/data/synapse/homeserver.yaml"

echo "Telegram bridge config ready. Start with:"
echo "  COMPOSE_PROFILES=telegram podman compose up -d"
echo "Then log in to Telegram from the bridge (see README)."
