#!/usr/bin/env bash
# Install or remove a systemd user unit that runs podman compose for this stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_NAME="matrix-podman-stack.service"
USER_UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="${USER_UNIT_DIR}/${UNIT_NAME}"

usage() {
  cat <<EOF
Usage: $0 [--uninstall] [--profiles LIST]

Writes ${UNIT_PATH} to start/stop the stack at login (use with loginctl enable-linger).

  --uninstall     Remove the unit and run daemon-reload
  --profiles LIST COMPOSE_PROFILES value (default: read from .env if set)

After install:
  systemctl --user daemon-reload
  systemctl --user enable --now ${UNIT_NAME}

Rootless hosts also need:
  loginctl enable-linger "\$USER"

Simple alternative (all Podman containers with restart policy):
  systemctl --user enable --now podman-restart.service
  loginctl enable-linger "\$USER"
  # rootful: sudo systemctl enable --now podman-restart.service
EOF
}

UNINSTALL=false
PROFILES_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall) UNINSTALL=true ;;
    --profiles) PROFILES_OVERRIDE="${2:?}"; shift ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

if $UNINSTALL; then
  if [[ -f "$UNIT_PATH" ]]; then
    rm -f "$UNIT_PATH"
    systemctl --user daemon-reload 2>/dev/null || true
    echo "Removed ${UNIT_PATH}"
  else
    echo "No unit at ${UNIT_PATH}"
  fi
  exit 0
fi

COMPOSE_PROFILES="${PROFILES_OVERRIDE}"
if [[ -z "$COMPOSE_PROFILES" && -f "$ROOT/.env" ]]; then
  # shellcheck source=/dev/null
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi
COMPOSE_PROFILES="${COMPOSE_PROFILES:-}"

PODMAN_COMPOSE="$(command -v podman-compose || true)"
if [[ -z "$PODMAN_COMPOSE" ]]; then
  PODMAN_COMPOSE="podman compose"
fi

mkdir -p "$USER_UNIT_DIR"

cat >"$UNIT_PATH" <<UNIT
[Unit]
Description=Matrix Podman stack (compose)
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${ROOT}
Environment=HOST_UID=${HOST_UID:-1000}
Environment=HOST_GID=${HOST_GID:-1000}
Environment=COMPOSE_PROFILES=${COMPOSE_PROFILES}
EnvironmentFile=-${ROOT}/.env
ExecStart=/bin/bash -lc 'cd "${ROOT}" && export HOST_UID=\${HOST_UID:-$(id -u)} HOST_GID=\${HOST_GID:-$(id -g)} COMPOSE_PROFILES="${COMPOSE_PROFILES}" && ${PODMAN_COMPOSE} up -d'
ExecStop=/bin/bash -lc 'cd "${ROOT}" && export COMPOSE_PROFILES="${COMPOSE_PROFILES}" && ${PODMAN_COMPOSE} down'
TimeoutStartSec=300

[Install]
WantedBy=default.target
UNIT

chmod 644 "$UNIT_PATH"
echo "Wrote ${UNIT_PATH}"
echo "Run: systemctl --user daemon-reload && systemctl --user enable --now ${UNIT_NAME}"
echo "Rootless: loginctl enable-linger \$USER"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$UNIT_PATH" && echo "systemd-analyze verify: OK"
fi
