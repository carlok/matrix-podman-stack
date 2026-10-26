#!/usr/bin/env bash
# One-shot Synapse data directory bootstrap (run via compose profile bootstrap).
set -euo pipefail

if [[ -f /data/homeserver.yaml ]]; then
  echo "homeserver.yaml already exists — skipping generation (delete it to regenerate)."
  exit 0
fi

echo "Generating Synapse configuration for ${SYNAPSE_SERVER_NAME}..."
python3 -m synapse.app.homeserver \
  --server-name "${SYNAPSE_SERVER_NAME}" \
  --config-path /data/homeserver.yaml \
  --generate-config \
  --report-stats=no

python3 <<'PY'
import os
import secrets
from pathlib import Path

import yaml

path = Path("/data/homeserver.yaml")
cfg = yaml.safe_load(path.read_text())

cfg["enable_registration"] = False
cfg["enable_registration_without_verification"] = False
cfg["registration_shared_secret"] = os.environ["REGISTRATION_SHARED_SECRET"]

cfg["macaroon_secret_key"] = os.environ["MATRIX_MACAROON_SECRET"]
cfg["form_secret"] = os.environ["MATRIX_FORM_SECRET"]

# Private server: no federation
cfg["send_federation"] = False
cfg["federation_domain_whitelist"] = []

# URL previews: SSRF hardening (private ranges + metadata endpoints)
cfg["url_preview_enabled"] = True
cfg["url_preview_ip_range_blacklist"] = [
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
]

# Metrics for optional Prometheus profile (dedicated listener; not on client :8008)
cfg["enable_metrics"] = True

# Relaxed defaults for small private servers (override in homeserver.yaml if needed)
cfg["rc_login"] = {
    "address": {"per_second": 50, "burst_count": 300},
    "account": {"per_second": 50, "burst_count": 300},
    "failed_attempts": {"per_second": 1, "burst_count": 50},
}
cfg["rc_message"] = {"per_second": 50, "burst_count": 500}

# Rootless-friendly paths (writable under /data volume)
cfg["media_store_path"] = "/data/media_store"
cfg["uploads_path"] = "/data/uploads"

cfg["database"] = {
    "name": "psycopg2",
    "args": {
        "user": os.environ["SYNAPSE_POSTGRES_USER"],
        "password": os.environ["SYNAPSE_POSTGRES_PASSWORD"],
        "database": os.environ["SYNAPSE_POSTGRES_DB"],
        "host": os.environ["POSTGRES_HOST"],
        "port": 5432,
        "cp_min": 5,
        "cp_max": 10,
    },
}

# Telegram appservice registration (created by scripts/bootstrap-telegram.sh)
telegram_reg = Path("/data/telegram-registration.yaml")
if telegram_reg.exists():
    files = cfg.get("app_service_config_files") or []
    reg_path = "/data/telegram-registration.yaml"
    if reg_path not in files:
        files.append(reg_path)
    cfg["app_service_config_files"] = files

path.write_text(yaml.safe_dump(cfg, sort_keys=False))

# Listen on all interfaces inside the container (port published on 127.0.0.1 on the host).
listeners = list(cfg.get("listeners") or [])
for listener in listeners:
    if listener.get("type") == "http" and listener.get("port") == 8008:
        listener["bind_addresses"] = ["0.0.0.0"]
        for resource in listener.get("resources", []):
            names = [n for n in (resource.get("names") or []) if n != "metrics"]
            resource["names"] = names

metrics_listener = {
    "port": 9000,
    "type": "http",
    "bind_addresses": ["0.0.0.0"],
    "resources": [{"names": ["metrics"], "compress": False}],
}
if not any(
    li.get("type") == "http" and li.get("port") == 9000 for li in listeners
):
    listeners.append(metrics_listener)
cfg["listeners"] = listeners

log_cfg_path = Path("/data") / f"{os.environ['SYNAPSE_SERVER_NAME']}.log.config"
if log_cfg_path.exists():
    log_cfg = yaml.safe_load(log_cfg_path.read_text())
    if log_cfg.get("handlers", {}).get("file"):
        log_cfg["handlers"]["file"]["filename"] = "/data/homeserver.log"
        log_cfg_path.write_text(yaml.safe_dump(log_cfg, sort_keys=False))

path.write_text(yaml.safe_dump(cfg, sort_keys=False))
print("Patched homeserver.yaml for Postgres, private mode, and metrics.")
PY

# Rootless Podman: ensure the host-mapped user can read keys (bootstrap may run as root).
if [[ -n "${SYNAPSE_UID:-}" && -n "${SYNAPSE_GID:-}" ]]; then
  chown -R "${SYNAPSE_UID}:${SYNAPSE_GID}" /data
fi
chmod 600 /data/*.signing.key 2>/dev/null || true
chmod 644 /data/homeserver.yaml /data/*.log.config 2>/dev/null || true
touch /data/homeserver.log 2>/dev/null || true
chmod 664 /data/homeserver.log 2>/dev/null || true
mkdir -p /data/media_store /data/uploads
if [[ -n "${SYNAPSE_UID:-}" && -n "${SYNAPSE_GID:-}" ]]; then
  chown -R "${SYNAPSE_UID}:${SYNAPSE_GID}" /data/media_store /data/uploads
fi
if [[ -n "${SYNAPSE_UID:-}" && -n "${SYNAPSE_GID:-}" ]]; then
  chown -R "${SYNAPSE_UID}:${SYNAPSE_GID}" /data
fi
