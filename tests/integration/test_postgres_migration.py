"""Postgres 16→18 migration with real Synapse and Telegram DB volumes."""

from __future__ import annotations

from pathlib import Path

import pytest

from . import podman_stack

pytestmark = pytest.mark.integration


@pytest.mark.timeout(600)
def test_synapse_pg16_schema_migration_probe(integration_data_dir: Path):
    """Bootstrap-only PG16 Synapse DB row survives upgrade (no Synapse container during dump)."""
    try:
        podman_stack.apply_compose_postgres_env(podman_stack.PG16_ENV)
        podman_stack.compose("up", "-d", "postgres-synapse", env=podman_stack.PG16_ENV)
        podman_stack.compose(
            "run",
            "--rm",
            "synapse-bootstrap",
            profiles="bootstrap",
            env=podman_stack.PG16_ENV,
        )
        podman_stack.compose(
            "exec",
            "-T",
            "postgres-synapse",
            "psql",
            "-U",
            "synapse",
            "-d",
            "synapse",
            "-c",
            "CREATE TABLE migration_probe (note text); INSERT INTO migration_probe VALUES ('synapse-pg16');",
            env=podman_stack.PG16_ENV,
        )
        podman_stack.compose("stop", "postgres-synapse", env=podman_stack.PG16_ENV)
        proc_up = podman_stack.run(["./scripts/upgrade-postgres.sh", "--service", "synapse"], timeout=1200)
        assert "OK:" in proc_up.stdout
        assert "18" in proc_up.stdout.split("major_version")[-1][:80]
        podman_stack.compose_down()
        podman_stack.apply_compose_postgres_env(podman_stack.PG18_ENV)
        podman_stack.compose("up", "-d", "postgres-synapse", env=podman_stack.PG18_ENV)
        proc = podman_stack.compose(
            "exec",
            "-T",
            "postgres-synapse",
            "psql",
            "-U",
            "synapse",
            "-d",
            "synapse",
            "-tAc",
            "SELECT note FROM migration_probe LIMIT 1;",
            env=podman_stack.PG18_ENV,
        )
        assert "synapse-pg16" in proc.stdout
    finally:
        podman_stack.compose_down()


@pytest.mark.timeout(1200)
def test_telegram_pg16_migration_row_survives(integration_data_dir: Path):
    try:
        podman_stack.apply_compose_postgres_env(podman_stack.PG16_ENV)
        podman_stack.compose(
            "up",
            "-d",
            "postgres-telegram",
            env=podman_stack.PG16_ENV,
            profiles="telegram",
        )
        for _ in range(60):
            proc = podman_stack.compose(
                "exec",
                "-T",
                "postgres-telegram",
                "pg_isready",
                "-U",
                "mautrix_telegram",
                env=podman_stack.PG16_ENV,
                profiles="telegram",
            )
            if proc.returncode == 0:
                break
            __import__("time").sleep(2)
        podman_stack.compose(
            "exec",
            "-T",
            "postgres-telegram",
            "psql",
            "-U",
            "mautrix_telegram",
            "-d",
            "mautrix_telegram",
            "-c",
            "CREATE TABLE migration_probe (id serial PRIMARY KEY, note text); "
            "INSERT INTO migration_probe (note) VALUES ('telegram-pg16');",
            profiles="telegram",
            env=podman_stack.PG16_ENV,
        )
        podman_stack.compose(
            "stop",
            "postgres-telegram",
            profiles="telegram",
            env=podman_stack.PG16_ENV,
        )
        podman_stack.apply_compose_postgres_env(podman_stack.PG18_ENV)
        proc_up = podman_stack.run(
            ["./scripts/upgrade-postgres.sh", "--service", "telegram"],
            timeout=900,
        )
        assert "OK:" in proc_up.stdout
        podman_stack.compose("up", "-d", "postgres-telegram", profiles="telegram", env=podman_stack.PG18_ENV)
        proc = podman_stack.compose(
            "exec",
            "-T",
            "postgres-telegram",
            "psql",
            "-U",
            "mautrix_telegram",
            "-d",
            "mautrix_telegram",
            "-tAc",
            "SELECT note FROM migration_probe LIMIT 1;",
            profiles="telegram",
            env=podman_stack.PG18_ENV,
        )
        assert "telegram-pg16" in proc.stdout
    except Exception:
        print(podman_stack.dump_compose_logs(["postgres-telegram"]))
        raise
    finally:
        podman_stack.compose_down(profiles="telegram")


@pytest.mark.timeout(300)
def test_upgrade_dry_run_leaves_pg16_volume(integration_data_dir: Path):
    vol = integration_data_dir / "postgres-synapse"
    podman_stack.apply_compose_postgres_env(podman_stack.PG16_ENV)
    podman_stack.compose(
        "up",
        "-d",
        "postgres-synapse",
        env=podman_stack.PG16_ENV,
    )
    for _ in range(60):
        proc = podman_stack.compose(
            "exec",
            "-T",
            "postgres-synapse",
            "pg_isready",
            "-U",
            "synapse",
            env=podman_stack.PG16_ENV,
        )
        if proc.returncode == 0:
            break
        __import__("time").sleep(2)
    podman_stack.compose("stop", "postgres-synapse", env=podman_stack.PG16_ENV)
    before = podman_stack.read_pg_version(vol)
    proc = podman_stack.run(
        ["./scripts/upgrade-postgres.sh", "--service", "synapse", "--dry-run"],
        env=podman_stack.PG16_ENV,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 0
    assert "[dry-run]" in proc.stdout
    after = podman_stack.read_pg_version(vol)
    assert before == after == "16"
    podman_stack.compose_down()
