# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **matrix-nio** `0.25.2` → `0.26.0` (vodozemac replaces python-olm for optional E2EE; the example bot does not enable encryption).
- **pytest** `8.3.4` → `9.1.1` and **pytest-asyncio** `0.24.0` → `1.4.0` (bumped together; existing `asyncio_mode` / fixture scope settings in `pyproject.toml` retained).
- **Valkey** image `8.1.2-alpine` → `9.1.2-alpine` (Redis-compatible; existing AOF/RDB under `DATA_DIR/valkey` upgrades in place).
- **Garage** image `v1.1.0` → `v2.4.1` (admin API v2, `garage layout apply` after assign, health check on `/health`, bootstrap uses `/garage` in the container).

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
