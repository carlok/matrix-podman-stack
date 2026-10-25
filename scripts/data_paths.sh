#!/usr/bin/env bash
# Resolve host data paths from DATA_DIR (.env / environment).
set -euo pipefail

data_root() {
  local root="${1:-}"
  if [[ -z "$root" ]]; then
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
  local dir="${DATA_DIR:-./data}"
  if [[ "$dir" != /* ]]; then
    dir="$root/$dir"
  fi
  printf '%s' "$dir"
}

ensure_data_dirs() {
  local root
  root="$(data_root "${1:-}")"
  mkdir -p \
    "$root/postgres-synapse" \
    "$root/postgres-telegram" \
    "$root/synapse" \
    "$root/synapse/media_store" \
    "$root/synapse/uploads" \
    "$root/element" \
    "$root/mautrix-telegram" \
    "$root/prometheus" \
    "$root/grafana" \
    "$root/bots" \
    "$root/nats/jetstream" \
    "$root/valkey" \
    "$root/garage/meta" \
    "$root/garage/data" \
    "$root/qdrant/storage" \
    "$root/ollama"

  local uid="${HOST_UID:-$(id -u)}"
  local gid="${HOST_GID:-$(id -g)}"
  chown -R "${uid}:${gid}" \
    "$root/synapse" \
    "$root/prometheus" \
    "$root/bots" 2>/dev/null || true
}
