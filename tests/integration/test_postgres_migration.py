"""Postgres 16→18 migration with real Synapse and Telegram DB volumes."""

from __future__ import annotations

from pathlib import Path

import pytest

import matrix_testutil

from . import podman_stack

pytestmark = pytest.mark.integration

MATRIX_BASE = "http://127.0.0.1:8008"
SERVER_NAME = "ci.integration.test"


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
        assert "major_version=18" in proc_up.stdout
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


@pytest.mark.timeout(1800)
def test_synapse_pg16_matrix_data_survives_migration(integration_data_dir: Path):
    """Synapse ran on PG16 with users, room, and messages; data survives upgrade to PG18."""
    alice_pw = "alice-migrate-pw"
    bob_pw = "bob-migrate-pw"
    msg_alice = "pg16-alice-message"
    msg_bob = "pg16-bob-message"
    try:
        podman_stack.apply_compose_postgres_env(podman_stack.PG16_ENV)
        podman_stack.compose("up", "-d", "postgres-synapse", env=podman_stack.PG16_ENV)
        podman_stack.wait_pg_isready("postgres-synapse", "synapse", env=podman_stack.PG16_ENV)
        podman_stack.compose(
            "run",
            "--rm",
            "synapse-bootstrap",
            profiles="bootstrap",
            env=podman_stack.PG16_ENV,
        )
        podman_stack.compose("up", "-d", "synapse", env=podman_stack.PG16_ENV)
        podman_stack.wait_healthz(8008)

        podman_stack.register_user(alice_pw, user="alice", admin=True)
        podman_stack.register_user(bob_pw, user="bob", admin=False)

        bob_id = matrix_testutil.user_id(SERVER_NAME, "bob")
        alice_token = matrix_testutil.login(MATRIX_BASE, "alice", alice_pw)
        room_id = matrix_testutil.create_room(MATRIX_BASE, alice_token, invite=[bob_id])
        matrix_testutil.wait_member(MATRIX_BASE, alice_token, room_id, bob_id, timeout_s=90.0)

        bob_token = matrix_testutil.login(MATRIX_BASE, "bob", bob_pw)
        matrix_testutil.join_room(MATRIX_BASE, bob_token, room_id)
        matrix_testutil.wait_member(MATRIX_BASE, alice_token, room_id, bob_id, timeout_s=90.0)
        matrix_testutil.send_text(MATRIX_BASE, alice_token, room_id, msg_alice)
        matrix_testutil.send_text(MATRIX_BASE, bob_token, room_id, msg_bob)
        matrix_testutil.wait_for_message_bodies(
            MATRIX_BASE, alice_token, room_id, {msg_alice, msg_bob}, timeout_s=90.0
        )

        podman_stack.compose("stop", "synapse", "postgres-synapse", env=podman_stack.PG16_ENV)
        podman_stack.run(
            podman_stack.compose_cmd("rm", "-f", "synapse", "postgres-synapse"),
            env=podman_stack.PG16_ENV,
            check=False,
        )
        podman_stack.apply_compose_postgres_env(podman_stack.PG18_ENV)
        proc_up = podman_stack.run(["./scripts/upgrade-postgres.sh", "--service", "synapse"], timeout=1200)
        assert "OK:" in proc_up.stdout
        assert "major_version=18" in proc_up.stdout

        podman_stack.compose("up", "-d", "synapse", env=podman_stack.PG18_ENV)
        podman_stack.wait_healthz(8008)

        alice_token = matrix_testutil.login(MATRIX_BASE, "alice", alice_pw)
        bob_token = matrix_testutil.login(MATRIX_BASE, "bob", bob_pw)
        matrix_testutil.wait_for_message_bodies(
            MATRIX_BASE, alice_token, room_id, {msg_alice, msg_bob}, timeout_s=120.0
        )
        matrix_testutil.wait_member(MATRIX_BASE, bob_token, room_id, bob_id, timeout_s=30.0)
    except Exception:
        print(podman_stack.dump_compose_logs(["synapse", "postgres-synapse"]))
        raise
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
        podman_stack.wait_pg_isready(
            "postgres-telegram",
            "mautrix_telegram",
            env=podman_stack.PG16_ENV,
            profiles="telegram",
        )
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
    podman_stack.wait_pg_isready("postgres-synapse", "synapse", env=podman_stack.PG16_ENV)
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
