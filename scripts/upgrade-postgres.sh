#!/usr/bin/env bash
# Migrate Postgres data directories from the 16-era layout to Postgres 18.
#
# Uses logical dump/restore (pg_dump / psql). The old data directory is copied
# aside; nothing is deleted automatically.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

POSTGRES_16_IMAGE="${POSTGRES_16_IMAGE:-docker.io/library/postgres:16.15-bookworm}"
POSTGRES_LEGACY_MOUNT="/var/lib/postgresql/data"
PROBE_IMAGE="${PROBE_IMAGE:-docker.io/library/busybox:1.36.1}"
UPGRADE_MARKER_NAME=".postgres-upgraded-to-18"

usage() {
  cat <<'EOF'
Usage: upgrade-postgres.sh [--service synapse|telegram|all] [--dry-run]

Migrates postgres-synapse and/or postgres-telegram from Postgres 16 (legacy
PGDATA at the volume root) to Postgres 18 (PGDATA under 18/docker).

Prerequisites:
  - Updated compose.yaml with Postgres 18 image and /var/lib/postgresql mounts
  - .env with database passwords set
  - Stack stopped or only Postgres services affected

The script refuses to run twice on the same volume. Fresh empty volumes are
skipped (init happens on first compose up).
EOF
}

SERVICE_SCOPE="all"
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE_SCOPE="${2:?}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# shellcheck source=/dev/null
set -a
source .env
set +a
# shellcheck source=scripts/data_paths.sh
source "$ROOT/scripts/data_paths.sh"
DATA_ROOT="$(data_root "$ROOT")"

MIGRATION_ENV_FILE="${DATA_ROOT}/.env.postgres-migration"
grep -vE '^POSTGRES_(SYNAPSE|TELEGRAM)_(IMAGE|MOUNT)=' .env >"$MIGRATION_ENV_FILE"
{
  echo "POSTGRES_SYNAPSE_IMAGE=docker.io/library/postgres:18.6-bookworm"
  echo "POSTGRES_SYNAPSE_MOUNT=/var/lib/postgresql"
  echo "POSTGRES_TELEGRAM_IMAGE=docker.io/library/postgres:18.6-bookworm"
  echo "POSTGRES_TELEGRAM_MOUNT=/var/lib/postgresql"
} >>"$MIGRATION_ENV_FILE"

timestamp_utc() {
  date -u +"%Y%m%dT%H%M%SZ"
}

detect_volume_layout() {
  local volume_host="$1"
  if [[ ! -d "$volume_host" ]]; then
    echo "empty"
    return 0
  fi
  podman run --rm -v "${volume_host}:/v:ro,Z" "$PROBE_IMAGE" sh -c '
    if test -f /v/.postgres-upgraded-to-18; then
      echo upgraded_marker
    elif test -f /v/18/docker/PG_VERSION; then
      echo pg18
    elif test -f /v/PG_VERSION; then
      echo legacy_root
    elif test -z "$(ls -A /v 2>/dev/null || true)"; then
      echo empty
    else
      echo unknown
    fi
  '
}

legacy_needs_migration() {
  local volume_host="$1"
  local ver
  ver="$(podman run --rm -v "${volume_host}:/v:ro,Z" "$PROBE_IMAGE" cat /v/PG_VERSION 2>/dev/null || true)"
  if [[ "$ver" =~ ^[0-9]+$ ]] && [[ "$ver" -lt 18 ]]; then
    echo "yes"
  else
    echo "no"
  fi
}

backup_volume_name() {
  printf '%s.pg16-backup-%s' "$1" "$2"
}

write_upgrade_marker() {
  local compose_service="$1"
  local profiles="$2"
  local body="$3"
  compose_with_profiles "$profiles" exec -T "$compose_service" sh -c \
    "printf '%s\n' \"${body}\" > /var/lib/postgresql/${UPGRADE_MARKER_NAME}"
}

compose() {
  COMPOSE_ENV_FILE="$MIGRATION_ENV_FILE" "$ROOT/scripts/compose_stack.sh" "$@"
}

compose_with_profiles() {
  local profiles="$1"
  shift
  if [[ -n "$profiles" ]]; then
    COMPOSE_PROFILES="$profiles" compose "$@"
  else
    compose "$@"
  fi
}

stop_stack_for() {
  local compose_service="$1"
  echo "==> Stopping dependent containers (if running)..."
  if [[ "$compose_service" == "postgres-synapse" ]]; then
    compose stop synapse postgres-synapse 2>/dev/null || true
    compose rm -sf synapse postgres-synapse 2>/dev/null || true
  else
    COMPOSE_PROFILES=telegram compose stop mautrix-telegram postgres-telegram 2>/dev/null || true
    COMPOSE_PROFILES=telegram compose rm -sf mautrix-telegram postgres-telegram 2>/dev/null || true
  fi
}

dump_legacy_16() {
  local volume_host="$1"
  local pg_user="$2"
  local pg_password="$3"
  local pg_db="$4"
  local dump_file="$5"

  echo "==> Logical dump from Postgres 16 (temporary container)..."
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] podman run --rm -v ${volume_host}:${POSTGRES_LEGACY_MOUNT}:Z -e PGPASSWORD=*** ${POSTGRES_16_IMAGE} pg_dump -U ${pg_user} -d ${pg_db} --no-owner --no-acl"
    return 0
  fi

  local dump_container
  dump_container="pg16-dump-${volume_rel}-$(date +%s)"
  podman rm -f "$dump_container" 2>/dev/null || true
  podman run -d --name "$dump_container" \
    -e POSTGRES_USER="$pg_user" \
    -e POSTGRES_PASSWORD="$pg_password" \
    -e POSTGRES_DB="$pg_db" \
    -v "${volume_host}:${POSTGRES_LEGACY_MOUNT}:Z" \
    "$POSTGRES_16_IMAGE" >/dev/null

  for _ in $(seq 1 90); do
    if podman exec "$dump_container" pg_isready -U "$pg_user" -d "$pg_db" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  podman exec "$dump_container" pg_isready -U "$pg_user" -d "$pg_db" >/dev/null
  podman exec "$dump_container" pg_dump -U "$pg_user" -d "$pg_db" --no-owner --no-acl \
    >"$dump_file"
  podman rm -f "$dump_container" >/dev/null
}

restore_pg18() {
  local compose_service="$1"
  local pg_user="$2"
  local pg_db="$3"
  local dump_file="$4"
  local profiles="${5:-}"

  echo "==> Starting ${compose_service} on Postgres 18 (fresh volume)..."
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] compose up -d ${compose_service}"
    echo "[dry-run] compose exec ${compose_service} psql -U ${pg_user} ..."
    return 0
  fi

  compose rm -sf "$compose_service" 2>/dev/null || true
  podman rm -f "matrix-podman-stack_${compose_service}_1" 2>/dev/null || true
  if [[ -n "$profiles" ]]; then
    COMPOSE_PROFILES="$profiles" compose up -d --force-recreate "$compose_service"
  else
    compose up -d --force-recreate "$compose_service"
  fi

  for _ in $(seq 1 60); do
    if compose_with_profiles "$profiles" exec -T "$compose_service" pg_isready -U "$pg_user" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  echo "==> Restoring dump into ${compose_service}..."
  compose_with_profiles "$profiles" exec -T "$compose_service" pg_isready -U "$pg_user" -d "$pg_db" >/dev/null
  compose_with_profiles "$profiles" exec -T "$compose_service" psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_db" \
    -f - <"$dump_file"
}

migrate_one() {
  local compose_service="$1"
  local volume_rel="$2"
  local pg_user="$3"
  local pg_password="$4"
  local pg_db="$5"
  local profiles="${6:-}"

  local volume_host="${DATA_ROOT}/${volume_rel}"
  echo ""
  echo "######## ${compose_service} (${volume_rel}) ########"

  local layout
  layout="$(detect_volume_layout "$volume_host")"
  echo "Detected volume layout: ${layout}"

  case "$layout" in
    empty)
      echo "Volume is empty — no migration needed (Postgres 18 will init on compose up)."
      return 0
      ;;
    pg18 | upgraded_marker)
      echo "Already on Postgres 18 (or migration marker present). Skipping."
      return 0
      ;;
    unknown)
      echo "ERROR: Unrecognized contents under ${volume_host}. Resolve manually before migrating." >&2
      exit 1
      ;;
    legacy_root)
      if [[ -z "$pg_password" ]]; then
        echo "ERROR: database password is required to migrate ${compose_service}." >&2
        exit 1
      fi
      ;;
    *)
      echo "ERROR: Unexpected layout ${layout}" >&2
      exit 1
      ;;
  esac

  if [[ "$(legacy_needs_migration "$volume_host")" != "yes" ]]; then
    echo "Legacy PGDATA is not older than Postgres 18; refusing to migrate."
    exit 1
  fi

  local ts backup_name backup_host dump_file
  ts="$(timestamp_utc)"
  backup_name="$(backup_volume_name "$volume_rel" "$ts")"
  backup_host="${DATA_ROOT}/${backup_name}"
  dump_file="${DATA_ROOT}/${volume_rel}.pg16-dump-${ts}.sql"

  echo "Plan:"
  echo "  1. Stop ${compose_service} and dependents"
  echo "  2. pg_dump from ${POSTGRES_16_IMAGE} using legacy mount"
  echo "  3. Copy ${volume_rel} -> ${backup_name} (original kept until you remove it)"
  echo "  4. Create empty ${volume_rel} for Postgres 18 layout"
  echo "  5. compose up ${compose_service} (18.x) and psql restore"
  echo "  6. Write ${UPGRADE_MARKER_NAME} marker"

  stop_stack_for "$compose_service"
  dump_legacy_16 "$volume_host" "$pg_user" "$pg_password" "$pg_db" "$dump_file"

  if [[ "$DRY_RUN" == 1 ]]; then
    echo "[dry-run] cp -a ${volume_host} ${backup_host}"
    echo "[dry-run] mkdir empty ${volume_host}; restore; marker"
    return 0
  fi

  echo "==> Backing up data directory to ${backup_name}..."
  podman run --rm -v "${DATA_ROOT}:/data:Z" "$PROBE_IMAGE" sh -c \
    "cp -a /data/${volume_rel} /data/${backup_name}"

  echo "==> Preparing empty volume for Postgres 18..."
  podman run --rm -v "${volume_host}:/v:Z" "$PROBE_IMAGE" sh -c \
    'rm -rf /v/* /v/.[!.]* /v/..?* 2>/dev/null || true'

  restore_pg18 "$compose_service" "$pg_user" "$pg_db" "$dump_file" "$profiles"

  write_upgrade_marker "$compose_service" "$profiles" \
    "backup=${backup_name} dump=$(basename "$dump_file") at=${ts}"

  echo "==> Verifying database..."
  local major
  major="$(compose_with_profiles "$profiles" exec -T "$compose_service" psql -v ON_ERROR_STOP=1 -U "$pg_user" -d "$pg_db" \
    -tAc "SELECT current_setting('server_version_num')::int / 10000;")"
  major="${major//[[:space:]]/}"
  if [[ "$major" != "18" ]]; then
    echo "ERROR: expected Postgres major 18 after migration, got ${major} (is an old container still running?)" >&2
    exit 1
  fi
  echo "Postgres major_version=${major}"

  echo "OK: ${compose_service} migrated. Backup: ${backup_name}"
  echo "     Dump file: ${dump_file}"
}

migrate_synapse() {
  migrate_one \
    "postgres-synapse" \
    "postgres-synapse" \
    "${SYNAPSE_POSTGRES_USER:-synapse}" \
    "${SYNAPSE_POSTGRES_PASSWORD:-}" \
    "${SYNAPSE_POSTGRES_DB:-synapse}" \
    ""
}

migrate_telegram() {
  local volume_host="${DATA_ROOT}/postgres-telegram"
  local layout
  layout="$(detect_volume_layout "$volume_host")"
  if [[ "$layout" == "empty" ]]; then
    echo "postgres-telegram volume is empty; skipping telegram migration."
    return 0
  fi
  migrate_one \
    "postgres-telegram" \
    "postgres-telegram" \
    "${TELEGRAM_POSTGRES_USER:-mautrix_telegram}" \
    "${TELEGRAM_POSTGRES_PASSWORD:-}" \
    "${TELEGRAM_POSTGRES_DB:-mautrix_telegram}" \
    "telegram"
}

case "$SERVICE_SCOPE" in
  synapse)
    migrate_synapse
    ;;
  telegram)
    migrate_telegram
    ;;
  all)
    migrate_synapse
    migrate_telegram
    ;;
  *)
    echo "Invalid --service value: $SERVICE_SCOPE" >&2
    exit 2
    ;;
esac

echo ""
echo "Migration pass complete. Start the stack: podman compose up -d"
