# PostgreSQL 18 upgrade (existing deployments)

Fresh installs use the Postgres **18.x** image in `compose.yaml` with the data volume mounted at `/var/lib/postgresql` (PGDATA under `18/docker` on the host).

Existing deployments created on Postgres **16** store PGDATA directly under `DATA_DIR/postgres-synapse/` (or `postgres-telegram/`). You cannot point Postgres 18 at that tree without a migration.

## Before you start

1. Read the [official Postgres 18 image notes](https://hub.docker.com/_/postgres) (PGDATA path change).
2. Back up `DATA_DIR` (see README **Backup and upgrades**).
3. Pull this repository version with Postgres 18 in `compose.yaml`.
4. Ensure `.env` has `SYNAPSE_POSTGRES_PASSWORD` (and `TELEGRAM_POSTGRES_PASSWORD` if you use the Telegram profile).

## Automated migration

From the repository root:

```bash
podman compose stop synapse   # and optional telegram bridge
./scripts/upgrade-postgres.sh --service synapse
# optional Telegram DB (skipped automatically if the volume is empty):
./scripts/upgrade-postgres.sh --service telegram
```

Or migrate both in one run (Telegram is skipped when its volume is empty):

```bash
./scripts/upgrade-postgres.sh --service all
```

Dry-run prints the plan without changing data:

```bash
./scripts/upgrade-postgres.sh --service synapse --dry-run
```

### What the script does

For each database service (`postgres-synapse`, `postgres-telegram`):

1. Detects legacy Postgres 16 PGDATA at the volume root.
2. Stops dependent containers.
3. Runs `pg_dump` from a temporary **Postgres 16** container (legacy mount path).
4. Copies the old directory to `postgres-<service>.pg16-backup-<timestamp>` on the host (original data is never deleted).
5. Creates an empty volume directory for Postgres 18.
6. Starts the compose Postgres **18** service and restores the dump with `psql`.
7. Writes a `.postgres-upgraded-to-18` marker so a second run is refused.

Skipped automatically: empty volumes (fresh install) and volumes already on Postgres 18.

### After migration

```bash
podman compose up -d
```

Confirm Synapse (and the Telegram bridge, if used) connect and health checks pass. Remove old backup directories only after you are satisfied.

Optional smoke test after migration or on a fresh install:

```bash
./scripts/verify-synapse-postgres.sh
```

This starts Postgres 18 and Synapse (running `bootstrap.sh` first if `homeserver.yaml` is missing) and checks `http://127.0.0.1:8008/health`.

## Manual alternative

You may use `pg_dump` / `pg_restore` or `pg_upgrade` yourself. The compose volume mount for Postgres 18 must be `${DATA_DIR}/postgres-<service>:/var/lib/postgresql`, with a new or migrated data tree under `18/docker` on the host.
