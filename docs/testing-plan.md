# Integration and unit testing plan

This document maps **claimed stack behavior** (README, upgrade docs, optional profiles) to **automated tests**. It stays general: no host paths, secrets, or one-off manual steps.

## Principles

| Layer | Scope | Runner |
|-------|--------|--------|
| **Unit** | Python helpers, bot logic, parsing, env gates | `pytest` (default CI job; excludes `integration`) |
| **Integration** | Real Podman Compose services, isolated `DATA_DIR` | `pytest -m integration` (CI matrix per area) |
| **Shell contract** | Compose config, restart policies, script `--help` | Unit YAML tests + existing `shellcheck` / `bats` |

Coverage gate (`pyproject.toml`, `fail_under` 95) applies to listed Python modules; integration tests do not replace unit tests for the same logic.

## Gap inventory and test design

### 1. Postgres 16 → 18 migration (Synapse + Telegram)

**Claim:** `scripts/upgrade-postgres.sh` migrates legacy PG16 PGDATA, keeps backups, supports dry-run and idempotency, and Synapse data survives.

| Behavior | Test type | Location |
|----------|-----------|----------|
| Synapse DB bootstrap on PG16, custom row survives upgrade to PG18 | Integration | `tests/integration/test_postgres_migration.py` |
| Full Matrix room/message retention after Synapse ran on PG16 | Manual / follow-up | `scripts/verify-synapse-postgres.sh` + operator migration |
| Telegram volume PG16 → 18 (table row survives) | Integration | same (`--service telegram`) |
| `--dry-run` leaves volume unchanged | Integration | same |
| Second run skips (marker / PG18 layout) | Integration | same |
| Backup directory `postgres-*.pg16-backup-*` retained | Integration | same |
| Volume layout detection | Unit | `tests/test_postgres_upgrade_util.py` (existing) |

**Notes:** PG16 bring-up sets `POSTGRES_*_IMAGE` and `POSTGRES_*_MOUNT` env vars (legacy `/var/lib/postgresql/data`). Production defaults remain Postgres 18 at `/var/lib/postgresql`.

### 2. Garage in-place upgrade v2.4.1 → v2.5.0

**Claim:** Existing Garage meta/data directories work after image bump.

| Behavior | Test type | Location |
|----------|-----------|----------|
| Layout + bucket on **v2.4.1**, S3 put object | Integration | `tests/integration/test_garage_upgrade.py` |
| Same volume on **v2.5.0**, S3 get object | Integration | same |

Uses compose image override for the old version only.

### 3. Monitoring profile (Prometheus + Grafana 13)

**Claim:** Prometheus scrapes Synapse metrics; Grafana can query Prometheus.

| Behavior | Test type | Location |
|----------|-----------|----------|
| Prometheus target `synapse` state `up` | Integration | `tests/integration/test_monitoring.py` |
| Grafana 13 datasource query returns Synapse metric series | Integration | same |

### 4. NATS JetStream + Valkey (bus profile)

**Claim:** JetStream persistence, monitoring (`/jsz`), auth, Valkey KV; bot bus demo publishes (and can verify consume).

| Behavior | Test type | Location |
|----------|-----------|----------|
| Publish + **pull/consume** one message | Integration | `tests/integration/test_bus_jetstream.py` |
| `BUS_DEMO` + optional `BUS_DEMO_CONSUME` round-trip | Unit | `tests/test_bus_hooks.py` |
| NATS monitor `/jsz` responds | Integration | `tests/integration/test_bus_jetstream.py` |
| Reconnect after `podman compose restart nats` | Integration | same |
| Valkey set/get; survive restart | Integration | same |
| `connect_nats_with_retry` | Unit | `tests/test_bus_hooks.py` |

### 5. Optional profiles (smoke)

| Profile | Claim | Test type | Location |
|---------|--------|-----------|----------|
| **Element** | Serves UI; `config.json` homeserver URL | Integration | `tests/integration/test_optional_profiles.py` |
| **Telegram** | Bootstrap + appservice registration without live Telegram login | Integration | same (dummy API id/hash) |
| **Qdrant** | Health, collection create, upsert, search | Integration | same |
| **Ollama** | `/api/tags` up | Integration | same |

Existing shell smokes (`verify-optional-profiles.sh`, `verify-bus-persistence.sh`) remain for operators; CI uses pytest integration tests.

### 6. Bot safety and Compose reliability

| Behavior | Test type | Location |
|----------|-----------|----------|
| Anti-loop (`sender_is_ignored_bot`, duo guards) | Unit | `tests/test_bot.py`, `tests/test_duo*.py` (existing) |
| Long-running services `restart: unless-stopped` | Integration contract | `tests/integration/test_compose_contract.py` |
| Synapse `/health` on fresh PG18 | Integration (light) | `tests/integration/test_synapse_smoke.py` |

Podman **auto-restart after daemon reboot** is host-level (`podman-restart.service`); not exercised in GitHub Actions. Compose `restart` policy is asserted in CI.

### 7. Other README / doc claims

| Claim | Test type | Location |
|-------|-----------|----------|
| `podman compose config` valid with `.env.example` | CI lint job | `.github/workflows/ci.yml` |
| `load_bot_config.py` JSON output | CI | existing |
| Postgres upgrade script refuses unknown layout | Unit | `tests/test_postgres_upgrade_util.py` |
| Fresh install skips migration | Integration | `test_postgres_migration.py` (empty volume) |

## CI layout

- **Unit job:** `pytest -m "not integration"` + coverage ≥ 95%.
- **Integration workflow:** `.github/workflows/integration.yml`, `ubuntu-latest`, Podman, **matrix** per area (postgres, garage, monitoring, bus, optional-*), pinned action SHAs, timeouts, log dump on failure.
- **Triggers:** PRs touching `compose.yaml`, `scripts/`, `bots/`, `tests/integration/`, workflows; `workflow_dispatch`; weekly schedule.

## Not automated (and why)

| Item | Reason |
|------|--------|
| Host nginx TLS termination | Outside compose; manual / operator |
| Real Telegram login / bridge traffic | Requires live Telegram credentials |
| Ollama model pull / inference RAM | Too heavy for default CI; API up only |
| Federation, TURN, E2EE | Out of scope for this stack |
| `podman-restart.service` after host reboot | Needs systemd on operator host |

## Local commands

```bash
cp .env.example .env   # edit secrets for local runs only
pytest -m "not integration" --cov
pytest -m integration -v --timeout=1200   # requires Podman; long-running
```
