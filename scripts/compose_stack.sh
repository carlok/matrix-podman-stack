#!/usr/bin/env bash
# Invoke compose for this repo (podman-compose on CI; podman compose elsewhere).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

args=(-f "$ROOT/compose.yaml")
if [[ -n "${COMPOSE_ENV_FILE:-}" ]]; then
  args+=(--env-file "$COMPOSE_ENV_FILE")
fi

if command -v podman-compose >/dev/null 2>&1; then
  exec podman-compose "${args[@]}" "$@"
fi

exec podman compose "${args[@]}" "$@"
