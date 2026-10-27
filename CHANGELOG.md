# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Postgres** image `16.15-bookworm` → **`18.6-bookworm`** (`postgres-synapse`, `postgres-telegram`). Volume mount is now `/var/lib/postgresql` (PGDATA at `18/docker` on the host). New installs init automatically; existing 16 data requires `./scripts/upgrade-postgres.sh` (see `docs/postgres-upgrade.md`).
- **Grafana** image `11.5.2` → `13.2.4` (monitoring profile; env vars unchanged; SQLite data under `DATA_DIR/grafana` migrates on first start).
- Dependabot: ignore semver-major updates for `library/postgres` (patch/minor 18.x updates still proposed).

### Breaking

- **Postgres 16 → 18:** Do not pull Postgres 18 and restart on an existing `DATA_DIR` without running the migration script. Legacy PGDATA at the volume root is incompatible with the Postgres 18 image layout.

### Upgrade notes

- **Postgres 16 → 18:** Stop Synapse (and optional Telegram bridge), run `./scripts/upgrade-postgres.sh`, then `podman compose up -d`. Backups are kept as `postgres-*.pg16-backup-*` until you remove them.

### Security

- Harden `compose.yaml`: `cap_drop`/`cap_add`, `security_opt: no-new-privileges`, `pids_limit`, internal `matrix-db` network for Postgres, required secrets for Telegram Postgres and Grafana admin, rootless `userns_mode: keep-id` for volume-writing services.
- Synapse bootstrap: URL preview IP blacklist, dedicated metrics listener on port `9000` (not on client `:8008`); Prometheus scrapes `synapse:9000`.
- CI: least-privilege `permissions`, GitHub Actions pinned by commit SHA, Trivy config scan job.
- `load_bot_config.py`: treat empty `BOT_NAME_PREFIX` in `.env` as unset so pattern mode still works.

### Changed

- **matrix-nio** `0.25.2` → `0.26.0` (vodozemac replaces python-olm for optional E2EE; the example bot does not enable encryption).
- **pytest** `8.3.4` → `9.1.1` and **pytest-asyncio** `0.24.0` → `1.4.0` (bumped together; existing `asyncio_mode` / fixture scope settings in `pyproject.toml` retained).
- **Valkey** image `8.1.2-alpine` → `9.1.2-alpine` (Redis-compatible; existing AOF/RDB under `DATA_DIR/valkey` upgrades in place).
- **Garage** image `v1.1.0` → `v2.4.1` (admin API v2, `garage layout apply` after assign, health check on `/health`, bootstrap uses `/garage` in the container).
- **Migration (existing deployments):** patch `data/synapse/homeserver.yaml` to move `metrics` off the `:8008` listener and add a `:9000` metrics listener (see `docs/SECURITY-AUDIT.md`), or re-bootstrap on a fresh data dir. Ensure nginx blocks `/_synapse/admin` and `/_synapse/metrics` on public vhosts.

### Upgrade notes

- **Garage v1 → v2:** Back up `DATA_DIR/garage/` first. Ensure `garage.toml` uses `replication_factor` (not legacy `replication_mode`). Stop all Garage nodes, switch the image tag, and start them together. Follow the [official Garage 1.x → 2.x migration guide](https://garagehq.deuxfleurs.fr/documentation/working-documents/migration-2/). Admin HTTP calls should use `/v2/…` (for example `GetClusterStatus`) instead of most `/v1/…` endpoints.
- **Valkey 8 → 9:** Stop Valkey, pull the new image, start again; auth and persistence settings in generated `valkey.conf` are unchanged.

## [1.0.0] - 2026-10-26

### Added

- Podman Compose stack for a private Matrix homeserver: Synapse, Postgres, and Element Web with localhost-only bindings and host nginx TLS termination documented in README.
- Optional Compose profiles: Telegram bridge (mautrix-telegram), NATS/Valkey bot bus, Prometheus/Grafana monitoring, Garage object storage, Qdrant vectors, and Ollama LLM.
- Bootstrap and operator scripts: Synapse/Element config generation, bot provisioning from `bots.yaml`, persistence verification, optional systemd unit installer, and resource stats helper.
- Example `matrix-nio` bot with duo mode, config-driven bot lists, and Python utilities (`load_bot_config`, `matrix_testutil`, render scripts).
- CI workflow: compose validation, shellcheck, ruff, pytest with branch coverage gate (`fail_under` in `pyproject.toml`), and bats tests for systemd installer.
- Contributor documentation: `AGENT.md`, `.env.example`, and `bots.example.yaml` templates without committed secrets.

[1.0.0]: https://github.com/carlok/matrix-podman-stack/tree/main
