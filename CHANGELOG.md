# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-26

### Added

- Podman Compose stack for a private Matrix homeserver: Synapse, Postgres, and Element Web with localhost-only bindings and host nginx TLS termination documented in README.
- Optional Compose profiles: Telegram bridge (mautrix-telegram), NATS/Valkey bot bus, Prometheus/Grafana monitoring, Garage object storage, Qdrant vectors, and Ollama LLM.
- Bootstrap and operator scripts: Synapse/Element config generation, bot provisioning from `bots.yaml`, persistence verification, optional systemd unit installer, and resource stats helper.
- Example `matrix-nio` bot with duo mode, config-driven bot lists, and Python utilities (`load_bot_config`, `matrix_testutil`, render scripts).
- CI workflow: compose validation, shellcheck, ruff, pytest with branch coverage gate (`fail_under` in `pyproject.toml`), and bats tests for systemd installer.
- Contributor documentation: `AGENT.md`, `.env.example`, and `bots.example.yaml` templates without committed secrets.

[1.0.0]: https://github.com/carlok/matrix-podman-stack/tree/main
