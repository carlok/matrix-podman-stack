"""Tests for Postgres 16 → 18 volume layout helpers."""

from pathlib import Path

from postgres_upgrade_util import (
    UPGRADE_MARKER_NAME,
    VolumeLayout,
    backup_volume_name,
    classify_postgres_volume,
    needs_pg16_to_18_migration,
    pg18_pgdata_dir,
    read_pg_major,
)


def test_read_pg_major_missing() -> None:
    assert read_pg_major(Path("/nonexistent")) is None


def test_classify_empty(tmp_path: Path) -> None:
    vol = tmp_path / "postgres-synapse"
    vol.mkdir()
    assert classify_postgres_volume(vol) == VolumeLayout.EMPTY


def test_classify_legacy_16(tmp_path: Path) -> None:
    vol = tmp_path / "postgres-synapse"
    vol.mkdir()
    (vol / "PG_VERSION").write_text("16\n", encoding="utf-8")
    assert classify_postgres_volume(vol) == VolumeLayout.LEGACY_ROOT
    assert needs_pg16_to_18_migration(vol) is True


def test_classify_pg18_layout(tmp_path: Path) -> None:
    vol = tmp_path / "postgres-synapse"
    pgdata = pg18_pgdata_dir(vol, 18)
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("18\n", encoding="utf-8")
    assert classify_postgres_volume(vol) == VolumeLayout.PG18
    assert needs_pg16_to_18_migration(vol) is False


def test_classify_marker(tmp_path: Path) -> None:
    vol = tmp_path / "postgres-synapse"
    vol.mkdir()
    (vol / UPGRADE_MARKER_NAME).write_text("backup=foo\n", encoding="utf-8")
    assert classify_postgres_volume(vol) == VolumeLayout.UPGRADED_MARKER


def test_backup_volume_name() -> None:
    assert backup_volume_name("postgres-synapse", "20260101T000000Z").startswith(
        "postgres-synapse.pg16-backup-"
    )


def test_read_pg_major_invalid(tmp_path: Path) -> None:
    vol = tmp_path / "v"
    vol.mkdir()
    (vol / "PG_VERSION").write_text("bogus\n", encoding="utf-8")
    assert read_pg_major(vol) is None


def test_classify_unknown(tmp_path: Path) -> None:
    vol = tmp_path / "v"
    vol.mkdir()
    (vol / "lost+found").mkdir()
    assert classify_postgres_volume(vol) == VolumeLayout.UNKNOWN


def test_classify_wrong_pg18_major(tmp_path: Path) -> None:
    vol = tmp_path / "v"
    pgdata = pg18_pgdata_dir(vol, 18)
    pgdata.mkdir(parents=True)
    (pgdata / "PG_VERSION").write_text("17\n", encoding="utf-8")
    assert classify_postgres_volume(vol) == VolumeLayout.UNKNOWN
