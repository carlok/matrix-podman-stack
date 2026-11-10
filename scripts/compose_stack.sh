#!/usr/bin/env bash
# Invoke compose for this repo (podman-compose on CI; podman compose elsewhere).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

args=(-f "$ROOT/compose.yaml")
if [[ -n "${COMPOSE_ENV_FILE:-}" ]]; then
  args+=(--env-file "$COMPOSE_ENV_FILE")
fi

# podman-compose >= 1.1 drops profiled services unless --profile is set, and it
# ignores COMPOSE_PROFILES. 1.0.x has no profile filter and rejects --profile.
_append_podman_compose_profiles() {
  local bin="$1"
  local profile trimmed
  local -a profiles
  if [[ -z "${COMPOSE_PROFILES:-}" ]]; then
    return 0
  fi
  if ! "$bin" --help 2>&1 | grep -q -- '--profile'; then
    return 0
  fi
  IFS=',' read -r -a profiles <<< "${COMPOSE_PROFILES}"
  for profile in "${profiles[@]}"; do
    trimmed="${profile#"${profile%%[![:space:]]*}"}"
    trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
    if [[ -n "$trimmed" ]]; then
      args+=(--profile "$trimmed")
    fi
  done
}

if command -v podman-compose >/dev/null 2>&1; then
  _append_podman_compose_profiles podman-compose
  exec podman-compose "${args[@]}" "$@"
fi

exec podman compose "${args[@]}" "$@"
